# Feature: Document UX & Editorial Newspaper Layouts

- **Feature ID**: `document-ux`
- **Status**: Partially Complete (Dual Exports Live) / Planned Interactive UX (Phase 5)
- **Primary Vision**: Rich single-record living document viewer and editorial newspaper feed layouts.

---

## 1. Overview & Vision

Tabular spreadsheet grids are ideal for structured data analysis, but multimodal archives (long articles, scanned documents, photo collections) demand rich, narrative layouts.

**Document UX** provides two complementary presentation modes:
1. **Single-Record Living Document Viewer**: Displays one record at a time with collapsible accordion sections, styled headers, embedded media, and Next/Previous hotkey navigation.
2. **Editorial Newspaper Feed Layout**: Formats dataset rows into interactive story cards with hero images, editorial headlines, and thematic badges.

---

## 2. Core Capabilities & Status

### 2.1 Dual Export Pipelines (Completed)
- **Single Document Synthesis**: Aggregates all dataset rows into one comprehensive briefing (`exports/{domain}_{table}_report_{timestamp}.md`).
- **Per-Row Sidecars (`_meta.md`)**: Generates individual Markdown files (`exports/{source_stem}_meta.md`) with YAML frontmatter and automatic image linking (`![photo](filepath)`).
- **Standardized YAML Frontmatter**: Every exported document includes clean YAML metadata (title, domain, table, timestamp, model, prompts).

### 2.2 Table Grid vs. Single Document View Toggle (Option 1)
- **Unified Display Toggle**: Segmented toggle `[ 📊 Table Grid ]`  `[ 📄 Single Document ]` positioned directly above dataset views.
- **Table Grid Mode**: Full-width multi-row DataFrame grid for dataset scanning, filtering, and row selection.
- **Single Document Mode**: Focused, full-width single-record reader for the currently active row:
  - **Paging Toolbar**: File name, modality badge, row counter (`Record 3 of 42`), and `◀ Previous` / `Next ▶` buttons.
  - **Full Uncut Text & Entities**: Displays entire extracted content without cell truncation, with color-coded entity badges (`gr.HighlightedText`).
  - **Media Players**: Native full-resolution image viewer, audio player, or video player.
  - **Visible Attributes**: Clean key-value card rendering only the columns toggled active.
- **Simplicity First (Preview vs. Export)**: In-app preview uses clean, native Gradio components (`gr.Markdown`, `gr.HighlightedText`, media elements) without fragile custom HTML/CSS; rich editorial layouts remain reserved for final document export.

### 2.3 Interactive Column Visibility Pill Bar
- Horizontal bar of clickable column pills directly above the data view (`[✓ file_name]  [✓ content]  [✓ summary]  [✗ file_size]`).
- Toggling a pill instantly filters columns in both the Table Grid and the Single Document view.
- Provides 1-click **Select All** and **Deselect All** helpers.

### 2.4 Editorial Newspaper / Magazine Feed (Planned)
- Multi-column editorial card feed for narrative dataset browsing.
- Dynamic theme selection (*Modern Editorial*, *Technical Dossier*, *Clean Minimal*, *Dark Terminal*).

---

## 3. Implementation Plan & Checklist

- [x] **Phase 1: Dual Export Engine & Sidecar Generation**
  - [x] Implement single report aggregation and per-row `_meta.md` export.
  - [x] Add standardized YAML frontmatter generation.
  - [x] Live row-by-row streaming preview in UI.
- [ ] **Phase 2: Table Grid vs. Single Document View Toggle & Column Visibility (Option 1)**
  - [ ] Add View Mode toggle (`📊 Table Grid` / `📄 Single Document`).
  - [ ] Add `◀ Previous` / `Next ▶` record navigation with row index bounds checking.
  - [ ] Render full uncut document text with `gr.HighlightedText` entity spans and native media players.
  - [ ] Add interactive Column Visibility Pill Bar (`gr.CheckboxGroup`) to hide/show columns in both views.
  - [ ] Unit tests for column filtering, row paging, and document view formatting.
- [ ] **Phase 3: Editorial Newspaper Feed View**
  - [ ] Implement multi-column CSS grid rendering story cards.
  - [ ] Add theme selector with custom CSS variables.
