---
name: report-generation
description: Use when synthesizing multimodal records into structured executive summaries, dossiers, or newspaper-style Markdown reports
---

# Report Generation & Multi-Record Synthesis

## Overview
Directives for producing clear, publication-ready Markdown reports, executive dossiers, and structured catalogs from database records. Designed for the View & Export engine.

## When to Use
- Generating synthesized briefings or executive summaries from multi-row datasets.
- Creating formatted newspaper or magazine style dossier articles with embedded images.
- Structuring tabular catalogs from document and media archives.

## Prompt Directives & Operational Rules
When `/report-generation` is invoked in a prompt, the model must adhere to these guidelines:

1. **Document Structure**:
   - **Title & Lead**: Clear top-level headline (`# Title`) and a concise executive lead paragraph summarizing the core theme of the dataset or record.
   - **Key Metrics / Properties Table**: Markdown table highlighting essential attributes (records analyzed, dates, domains, primary categories).
   - **Analytical Body**: High-density prose grouped with clean subheadings (`## Thematic Breakdown`, `## Key Discoveries`).
   - **Cross-Record Patterns**: Explicitly note relationships, commonalities, or notable outliers across the collection.

2. **Media & Image Embedding**:
   - If media paths are present, embed images using standard Markdown syntax: `![Caption](file_path)`.
   - Never generate base64 strings or raw HTML `<img>` tags.

3. **Styling & Token Efficiency**:
   - Use clean, GitHub-flavored Markdown only.
   - Strictly forbid raw HTML (`<table>`, `<div>`, `<!DOCTYPE html>`) and inline `<svg>` graphics.
   - Format lists with crisp bullet points and bold leading terms.

4. **Example Template**:
```markdown
# Executive Synthesis Dossier: Collection Overview

> A high-level briefing of records synthesized from the repository.

| Metric | Summary Value |
|---|---|
| Focus Area | Multimodal Archival Processing |
| Primary Entities | 14 Unique Organizations, 8 Regions |

## Key Findings
- **Dominant Themes**: Analysis reveals high convergence on automated processing.
- **Notable Outliers**: Specific records highlight edge-case handling.
```
