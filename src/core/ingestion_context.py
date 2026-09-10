"""
Dynamic Ingestion Context & State Accumulation Engine (RES-12)
=============================================================
Maintains stateful cross-row context across multi-row batch ingestion and prompt
pipelines. Allows Pipeline Tools to 'learn' continuously across records, providing:
1. Dynamic Cross-Row Memory: Injects accumulated knowledge into batch pipelines.
2. Deduplication & Entity Normalization: Canonicalizes entity spellings, aliases,
   and relationships across records to prevent duplication.
3. Taxonomies & Discovered Themes: Tracks modalities, extensions, tags, and topics.
4. Learned Knowledge Export: Synthesizes final knowledge register to
   `exports/{domain}-{table}-ingestion-context.md` with structured YAML frontmatter
   and JSON-LD schema metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("pipeline_tools.ingestion_context")


@dataclass
class IngestionContext:
    domain: str = "default"
    table: str = "raw_assets"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Maps lowercase or alias spelling -> canonical entity name
    entity_aliases: Dict[str, str] = field(default_factory=dict)
    taxonomies: Dict[str, List[str]] = field(default_factory=dict)
    row_summaries: List[Dict[str, Any]] = field(default_factory=list)
    global_themes: List[str] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    KNOWN_ALIASES = {
        "postgres": "PostgreSQL",
        "pxt": "Pixeltable",
        "gemini-pro": "Gemini",
        "pymupdf": "PyMuPDF",
        "fitz": "PyMuPDF",
    }

    def normalize_entity(self, raw_name: str, category: str = "general") -> str:
        """
        Normalize an entity against known aliases and canonical spellings.
        Handles casing variations, hyphens, pluralization, and known technical aliases.
        """
        clean = raw_name.strip()
        if not clean:
            return ""
        key = clean.lower()

        # Check known common aliases (e.g. postgres -> PostgreSQL)
        if key in self.KNOWN_ALIASES:
            canonical_target = self.KNOWN_ALIASES[key]
            if canonical_target in self.entities:
                self.entities[canonical_target]["mentions"] = self.entities[canonical_target].get("mentions", 0) + 1
                self.entity_aliases[key] = canonical_target
                return canonical_target

        # Check existing alias map
        if key in self.entity_aliases:
            canonical = self.entity_aliases[key]
            self.entities[canonical]["mentions"] = self.entities[canonical].get("mentions", 0) + 1
            return canonical

        # Check case-insensitive, punctuation, and pluralization against existing entities
        for existing in list(self.entities.keys()):
            exist_lower = existing.lower()
            if (
                exist_lower == key or 
                exist_lower.replace("-", " ") == key.replace("-", " ") or
                exist_lower.replace("_", " ") == key.replace("_", " ") or
                exist_lower + "s" == key or
                key + "s" == exist_lower or
                exist_lower + "es" == key or
                key + "es" == exist_lower
            ):
                self.entity_aliases[key] = existing
                self.entities[existing]["mentions"] = self.entities[existing].get("mentions", 0) + 1
                return existing

        # If clean matches known alias target, register with canonical casing
        canonical_name = self.KNOWN_ALIASES.get(key, clean)
        self.entities[canonical_name] = {
            "canonical": canonical_name,
            "category": category,
            "mentions": 1,
            "first_seen": datetime.now().isoformat()
        }
        self.entity_aliases[key] = canonical_name
        return canonical_name

    def record_row(
        self,
        file_name: str,
        modality: str = "other",
        file_type: str = "",
        content_snippet: str = "",
        extracted_entities: Optional[List[str]] = None,
        extracted_tags: Optional[List[str]] = None,
        summary: str = "",
        row_id: Optional[str] = None
    ) -> None:
        """Accumulate cross-row intelligence from a processed row."""
        row_idx = len(self.row_summaries) + 1

        # Track modalities in taxonomies
        if "modalities" not in self.taxonomies:
            self.taxonomies["modalities"] = []
        if modality and modality not in self.taxonomies["modalities"]:
            self.taxonomies["modalities"].append(modality)

        if "extensions" not in self.taxonomies:
            self.taxonomies["extensions"] = []
        if file_type and file_type not in self.taxonomies["extensions"]:
            self.taxonomies["extensions"].append(file_type)

        # Normalize and record entities
        norm_entities = []
        if extracted_entities:
            for ent in extracted_entities:
                if ent and isinstance(ent, str):
                    canonical = self.normalize_entity(ent)
                    norm_entities.append(canonical)

        # Track tags / themes
        if extracted_tags:
            if "tags" not in self.taxonomies:
                self.taxonomies["tags"] = []
            for t in extracted_tags:
                if t and t not in self.taxonomies["tags"]:
                    self.taxonomies["tags"].append(t)
                    if t not in self.global_themes:
                        self.global_themes.append(t)

        # Record row summary
        clean_sum = summary.strip()
        if not clean_sum and content_snippet:
            clean_sum = content_snippet[:150].replace("\n", " ").strip()
            if len(content_snippet) > 150:
                clean_sum += "..."

        self.row_summaries.append({
            "row_idx": row_idx,
            "file_name": file_name,
            "modality": modality,
            "entities": norm_entities,
            "summary": clean_sum,
            "row_id": str(row_id) if row_id else None
        })

    def format_context_prompt_fragment(self, max_items: int = 5) -> str:
        """
        Format a concise accumulated context block to inject into prompt pipelines.
        Enables LLM prompts to reference accumulated knowledge.
        """
        lines = []
        lines.append("### Accumulated Ingestion Context (Learned Across Rows):")
        if self.entities:
            top_entities = sorted(self.entities.items(), key=lambda x: x[1].get("mentions", 0), reverse=True)[:max_items]
            ents_str = ", ".join(f"{name} ({info.get('mentions', 1)}x)" for name, info in top_entities)
            lines.append(f"- **Known Entities & Standard Naming**: {ents_str}")
        if self.taxonomies.get("modalities"):
            lines.append(f"- **Active Modalities**: {', '.join(self.taxonomies['modalities'])}")
        if self.global_themes:
            lines.append(f"- **Discovered Themes & Tags**: {', '.join(self.global_themes[:max_items])}")
        if self.row_summaries:
            recent = self.row_summaries[-min(3, len(self.row_summaries)):]
            recent_str = "; ".join(f"{r['file_name']}: {r['summary'][:60]}" for r in recent)
            lines.append(f"- **Recent Prior Records**: {recent_str}")
        return "\n".join(lines)

    def export_to_markdown(self, export_dir: str = "exports") -> Path:
        """
        Export accumulated dataset context to exports/{domain}-{table}-ingestion-context.md
        with YAML frontmatter and JSON-LD structured metadata.
        """
        out_dir = Path(export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{self.domain}-{self.table}-ingestion-context.md"

        frontmatter = {
            "title": f"Ingestion Context: {self.domain}.{self.table}",
            "domain": self.domain,
            "table": self.table,
            "generated_at": datetime.now().isoformat(),
            "total_records": len(self.row_summaries),
            "entity_count": len(self.entities),
            "modalities": self.taxonomies.get("modalities", []),
            "schema_version": "1.0"
        }

        # Format markdown body with frontmatter
        md_lines = ["---"]
        for k, v in frontmatter.items():
            if isinstance(v, list):
                md_lines.append(f"{k}: {json.dumps(v)}")
            elif isinstance(v, (int, float, bool)):
                md_lines.append(f"{k}: {v}")
            else:
                md_lines.append(f"{k}: \"{v}\"")
        md_lines.append("---\n")

        md_lines.append(f"# Ingestion Context Knowledge Register: `{self.domain}.{self.table}`\n")
        md_lines.append(f"> Auto-generated by Pipeline Tools dynamic ingestion state accumulator on **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**.\n")
        md_lines.append(f"- **Dataset Path**: `{self.domain}.{self.table}`")
        md_lines.append(f"- **Total Rows Ingested/Processed**: {len(self.row_summaries)}")
        md_lines.append(f"- **Unique Normalized Entities**: {len(self.entities)}")
        md_lines.append(f"- **Modalities Identified**: {', '.join(self.taxonomies.get('modalities', ['none']))}\n")

        md_lines.append("## 1. Discovered Entity Register & Canonical Spellings\n")
        if self.entities:
            md_lines.append("| Canonical Entity | Category | Mentions | First Seen |")
            md_lines.append("|---|---|---|---|")
            for ent_name, info in sorted(self.entities.items(), key=lambda x: x[1].get("mentions", 0), reverse=True):
                md_lines.append(f"| **{ent_name}** | `{info.get('category', 'general')}` | {info.get('mentions', 1)} | {info.get('first_seen', 'N/A')[:19]} |")
        else:
            md_lines.append("*No explicit entities extracted during this batch run.*")
        md_lines.append("\n")

        md_lines.append("## 2. Taxonomies & Themes\n")
        for tax_k, tax_vals in self.taxonomies.items():
            md_lines.append(f"- **{tax_k.capitalize()}**: {', '.join(tax_vals)}")
        if self.global_themes:
            md_lines.append(f"- **Global Themes**: {', '.join(self.global_themes)}")
        md_lines.append("\n")

        md_lines.append("## 3. Record-by-Record Ingestion Summaries\n")
        if self.row_summaries:
            for r in self.row_summaries:
                md_lines.append(f"### Record {r['row_idx']}: `{r['file_name']}` ({r['modality']})")
                if r.get("summary"):
                    md_lines.append(f"{r['summary']}\n")
                if r.get("entities"):
                    md_lines.append(f"*Normalized Entities*: {', '.join(f'`{e}`' for e in r['entities'])}\n")
        else:
            md_lines.append("*No row summaries recorded.*")

        md_lines.append("\n## 4. Structured Schema (JSON-LD)\n")
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": f"{self.domain}.{self.table}",
            "description": f"Dynamic ingestion knowledge state for table {self.table} under {self.domain}",
            "temporalCoverage": datetime.now().isoformat(),
            "variableMeasured": list(self.taxonomies.keys()),
            "keywords": list(self.entities.keys())[:20]
        }
        md_lines.append("```json")
        md_lines.append(json.dumps(json_ld, indent=2))
        md_lines.append("```\n")

        content = "\n".join(md_lines)
        file_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved ingestion context knowledge register to {file_path}")
        return file_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "table": self.table,
            "created_at": self.created_at,
            "entities": self.entities,
            "entity_aliases": self.entity_aliases,
            "taxonomies": self.taxonomies,
            "row_summaries": self.row_summaries,
            "global_themes": self.global_themes,
            "relationships": self.relationships,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IngestionContext":
        return cls(
            domain=data.get("domain", "default"),
            table=data.get("table", "raw_assets"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            entities=data.get("entities", {}),
            entity_aliases=data.get("entity_aliases", {}),
            taxonomies=data.get("taxonomies", {}),
            row_summaries=data.get("row_summaries", []),
            global_themes=data.get("global_themes", []),
            relationships=data.get("relationships", []),
            metadata=data.get("metadata", {})
        )
