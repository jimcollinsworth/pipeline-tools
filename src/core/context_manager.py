"""
Context Manager
===============
Handles reading, writing, and templating for table-level context memory files ({domain}_{table}_context.md).
Maintains preset context system prompts and exports clean entity cross-reference indexes.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

CONTEXTS_DIR = Path("contexts")
EXPORTS_DIR = Path("exports")

CONTEXT_PRESETS: Dict[str, Dict[str, str]] = {
    "EBA Corporate Minutes & Historical Bylaws": {
        "description": "Cross-reference co-op/HOA board decisions, officers, voting outcomes, and contractor bids with bidirectional document citations.",
        "prompt": (
            "You are maintaining the evolving knowledge context for the EBA building and HOA archive.\n"
            "Your goal is to cross-reference decisions, officers, financial commitments, and contractor history across decades of records.\n"
            "- Entity Canonicalization: Normalize names to canonical forms (e.g., 'J. R. Oppenheimer', 'Bob Oppenheimer' -> 'J. Robert Oppenheimer').\n"
            "- Bidirectional Citations: Always record file citations with markdown links [Document Title](filepath) for every entity mention.\n"
            "- Conflict Tracking: If two records disagree on a date, dollar figure, or vote outcome, document both and flag with [CONFLICT].\n"
            "- Action Tracking: Record board resolutions, voting outcomes, and expenditures explicitly."
        )
    },
    "Personal Lifelog & Multimodal Inbox": {
        "description": "Continuous personal memory and second brain from daily multimodal captures (voice memos, photos, notes).",
        "prompt": (
            "You are compiling a continuous personal memory and second brain from daily multimodal captures.\n"
            "- Extract and categorize: People, Places, Recurring Themes, and High-priority Markers:\n"
            "  - !ideas! for novel concepts\n"
            "  - ?questions? for research follow-ups\n"
            "  - *todos* for actionable tasks\n"
            "- Maintain links to raw audio recordings, photos, and notes."
        )
    },
    "Contractor Proposals & Financial Auditing": {
        "description": "Audit vendor bids, invoices, scope of work, and budget lines with line-item document cross-referencing.",
        "prompt": (
            "You are auditing vendor contracts, proposals, invoices, and budget lines.\n"
            "- Track contractor names, project scopes, bid amounts, approved expenditures, and payment dates.\n"
            "- Normalize company names and point-of-contact individuals.\n"
            "- Cross-reference line items to original PDF proposals and invoices."
        )
    },
    "General Document Knowledge Synthesis": {
        "description": "Standard knowledge base compilation: entity normalization, alias mapping, and thematic synthesis.",
        "prompt": (
            "You are maintaining a cumulative domain wiki compiled from ingested documents and tabular datasets.\n"
            "- Normalize entities (People, Organizations, Locations, Concepts).\n"
            "- Maintain deduplicated alias mappings and source citations [Source](filepath).\n"
            "- Record operational observations and data transformation notes in Lessons Learned."
        )
    }
}

class ContextManager:
    """Manages reading, writing, and templating for table-level context files."""

    @staticmethod
    def get_context_file_path(domain: str, table: str) -> Path:
        """Resolve the standard path for a domain/table context file."""
        clean_domain = re.sub(r'[^a-zA-Z0-9_]', '_', domain.strip().lower()) if domain else "default"
        clean_table = re.sub(r'[^a-zA-Z0-9_]', '_', table.strip().lower()) if table else "data"
        CONTEXTS_DIR.mkdir(parents=True, exist_ok=True)
        return CONTEXTS_DIR / f"{clean_domain}_{clean_table}_context.md"

    @classmethod
    def generate_default_template(cls, domain: str, table: str, preset_name: str = "General Document Knowledge Synthesis") -> str:
        """Create a structured starter template for a new context file."""
        preset = CONTEXT_PRESETS.get(preset_name, CONTEXT_PRESETS["General Document Knowledge Synthesis"])
        prompt_text = preset["prompt"]

        return f"""# Context & Memory: {domain}.{table}

> **Table**: `{domain}.{table}`  
> **Status**: Active Knowledge Context  
> **Git Tracked**: Yes &bull; **Editable by User**: Yes  

---

## 1. Context System Prompt & Governance
{prompt_text}

---

## 2. Active Skills & Tool Directives
*No specialized skills loaded. Directives from `.agents/skills/` will appear here.*

---

## 3. Canonical Entity Register

### People
| Canonical Name | Aliases | Referencing Documents | Notes |
|---|---|---|---|
| *Example Person* | *Alias 1, Alias 2* | *[Sample Doc](file:///path/to/doc.pdf)* | *Role / Affiliation* |

### Organizations
| Canonical Name | Aliases | Referencing Documents | Notes |
|---|---|---|---|
| *Example Org* | *Org Acronym* | *[Sample Doc](file:///path/to/doc.pdf)* | *Type / Industry* |

### Locations
| Canonical Name | Aliases | Referencing Documents | Notes |
|---|---|---|---|
| *Example Location* | *Loc Shortcode* | *[Sample Doc](file:///path/to/doc.pdf)* | *City / State / Room* |

### Topics & Things
| Canonical Term | Category | Referencing Documents | Summary |
|---|---|---|---|
| *Example Topic* | *Finance / Legal* | *[Sample Doc](file:///path/to/doc.pdf)* | *Brief explanation* |

---

## 4. Thematic Dataset Summary & Timeline
*Overview of accumulated records, major recurring themes, and timeline milestones.*

---

## 5. Execution History & Lessons Learned
- Initialized context memory file for `{domain}.{table}`.
"""

    @classmethod
    def load_context(cls, domain: str, table: str, default_preset: str = "General Document Knowledge Synthesis") -> str:
        """Load context markdown from disk. If file does not exist, generate and save the starter template."""
        if not domain or not table:
            return ""

        file_path = cls.get_context_file_path(domain, table)
        if file_path.exists():
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"# Error reading {file_path.name}\n\n```\n{e}\n```"

        # Also check root directory for backward compatibility
        root_path = Path(f"{domain}_{table}_context.md")
        if root_path.exists():
            try:
                content = root_path.read_text(encoding="utf-8")
                # Migrate to contexts/ directory
                cls.save_context(domain, table, content)
                return content
            except Exception:
                pass

        # Generate starter template and persist
        starter = cls.generate_default_template(domain, table, preset_name=default_preset)
        cls.save_context(domain, table, starter)
        return starter

    @classmethod
    def save_context(cls, domain: str, table: str, content: str) -> Path:
        """Persist context markdown string to disk."""
        file_path = cls.get_context_file_path(domain, table)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    @classmethod
    def apply_preset(cls, preset_name: str, current_content: str) -> str:
        """Update or inject the Context System Prompt & Governance section with a preset."""
        preset = CONTEXT_PRESETS.get(preset_name)
        if not preset:
            return current_content

        new_prompt = preset["prompt"]
        pattern = r"(## 1\. Context System Prompt & Governance\s*\n)(.*?)(?=\n---|\n## 2|\Z)"
        
        if re.search(pattern, current_content, flags=re.DOTALL):
            return re.sub(
                pattern,
                rf"\g<1>{new_prompt}\n",
                current_content,
                flags=re.DOTALL
            )
        else:
            # Section not found; prepend governance section
            return f"## 1. Context System Prompt & Governance\n{new_prompt}\n\n---\n\n" + current_content

    @classmethod
    def export_clean_index(cls, domain: str, table: str, content: str) -> Path:
        """Extract the Entity Register and export a clean index document."""
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        clean_domain = re.sub(r'[^a-zA-Z0-9_]', '_', domain.strip().lower()) if domain else "default"
        clean_table = re.sub(r'[^a-zA-Z0-9_]', '_', table.strip().lower()) if table else "data"
        export_path = EXPORTS_DIR / f"{clean_domain}_{clean_table}_index.md"

        # Look for Section 3 (Entity Register)
        match = re.search(r"(## 3\. Canonical Entity Register.*?)(?=\n## 4|\Z)", content, flags=re.DOTALL)
        if match:
            register_text = match.group(1).strip()
        else:
            register_text = content

        index_doc = f"""# Cross-Reference Index: {domain}.{table}

> **Source**: `{clean_domain}_{clean_table}_context.md`  
> **Exported For**: Entity Cross-Referencing & Archive Navigation  

---

{register_text}
"""
        export_path.write_text(index_doc, encoding="utf-8")
        return export_path
