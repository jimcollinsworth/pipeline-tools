# Pipeline Tools Planning & Tracking

Project: Multimodal Asset Processing, Prompt Workbench & Export Engine  
Primary Technologies: **Pixeltable**, **Gradio**, **PyMuPDF / Document Parsers**, **LLM APIs (OpenAI, Anthropic, Gemini, Ollama)**

---

## 1. Project Overview & Architecture

An interactive multimodal workbench and ETL engine designed to:
1. Scan and ingest local directory trees containing multimodal files (PDFs, Markdown, text, images, audio, video).
2. Store documents, metadata, extracted chunks, and lineage in **Pixeltable** unified tables and views.
3. Provide an interactive **Gradio Workbench** to design, test, and iterate on LLM prompts (entity extraction, summarization, metadata generation) on a single row or sample subset before running against full datasets.
4. Export enriched metadata into sidecars (.meta.yaml, .json), tabular datasets (CSV/Parquet), Markdown summaries, and optional YAML frontmatter.

`mermaid
flowchart TD
    A[Source Directories: PDF, MD, TXT, IMG, AV] --> B[Ingest & Chunking Engine]
    B --> C[(Pixeltable Unified DB)]
    C --> D[Gradio UI Workbench]
    
    subgraph D [Gradio Workbench]
        D1[Directory Ingestion & Stats]
        D2[Prompt Playground: 1-5 Row Dry-Run]
        D3[Pixeltable Computed Columns & Batch Engine]
        D4[DataTable Viewer with Embedded Media & Text]
    end
    
    C --> E[Export Engine]
    E --> F1[Sidecar Files: .meta.yaml / .json]
    E --> F2[Consolidated CSV / Parquet]
    E --> F3[Synthesized Markdown Reports]
`

---

## 2. Implementation Roadmap & Task Lists

### Phase 1: Core Foundation & Prompt Playground (Completed & Tested)
- [x] **Environment & Core Config Setup**
  - Dependency setup & config module (`config.json` with Ollama, default models, directories).
  - Minimal automated test suite in `tests/test_app.py` verifying settings, scanner, Pixeltable table creation, and Gradio app loading.
- [x] **Pixeltable Schema & Ingestion Core**
  - Unified table definition (`file_name`, `file_path`, `rel_path`, `modality`, `file_type`, `file_size`, `content`, `doc`, `image`, `audio`, `video`, `metadata`, `created_at`).
  - Domain / directory and table name selection in UI.
  - Ingestion handler: One file $\rightarrow$ One row, with native text/markdown extraction and direct PDF page text extraction via Pixeltable's bundled `pypdfium2` engine into the `content` column.

- [x] **Prompt Iteration Workbench (Gradio UI)**
  - UI Tab: **Ingestion & Data Inspector** (directory selector, file filter, scan summary, and Pixeltable ingestion trigger).
  - UI Tab: **Prompt Playground** (select Ollama model, enter system/user prompts with `{column}` placeholders, test on 1–N sample rows with side-by-side preview).
  - Column commit workflow: Apply tested prompt across table rows with **Replace** or **Append** modes to new or existing columns.
  - UI Tab: **Lineage & DataTables** (view table contents and columns in an interactive data viewer).
  - UI Tab: **Settings & Models** (Ollama server health test and installed model browser).


### Phase 2: Usability Improvements, Export Engine & Live Monitoring (In Progress)
- [x] **UI Usability & Persistent Inputs**
  - Added dynamic select dropdowns for Domain/Directory and Table names in Prompt Playground with automatic auto-refresh when domain changes.
  - Added Live Table Data Preview & Row Count display in Prompt Playground (updates automatically on table/domain selection and after batch execution).
  - Fixed table path resolution for preview loading (handles both bare table names `raw_files_test` and domain-prefixed names `eba/raw_files_test` without creating duplicate prefixes).
  - Automatic error formatting and name sanitization (protects against leading digits, dashes, and invalid characters in table/domain names).
  - Saved dialog box last entries (persists last-used domain, table name, model, prompt templates, system prompts, and source directory to `config.json` automatically).
- [ ] **Export Manager**

  - Safe sidecar generation: `.meta.yaml`, `.json`, and Markdown summary files next to source files or in an export mirror tree.
  - CSV/Parquet export of structured tables (entities, tags, summaries, chunk lineage).
  - In-place optional YAML frontmatter updates for Markdown files.
- [ ] **Live Progress & Execution Monitor**
  - Background task worker for full directory batch runs.
  - Live log streaming and step progress bar inside Gradio.

### Phase 3: Pixeltable Lineage, Undo & Multimodal Extensions (Planned)
- [ ] **Lineage & Snapshots UI**
  - Visualizing Pixeltable version history and tag snapshots.
  - Rollback / undo capabilities for computed columns and schema edits.
  - Image handling (Vision LLM descriptions, OCR, object detection).
  - Audio/Video transcription via Whisper / Gemini Multimodal API with time-coded chunking.

---

## 3. Issues & Research Items

| ID | Topic | Status | Description / Decision |
|---|---|---|---|
| RES-01 | Pixeltable Chunking vs Table Structure | Complete | Use unified table with text/media columns, chunk views for document-level splitting, and computed columns for LLM calls. |
| RES-02 | Multimodal API Abstraction | In Progress | Support OpenAI, Anthropic, Google Gemini (via pixeltable.functions), and local Ollama via unified prompt wrapper. |
| RES-03 | Large PDF Chunking Strategies | Open | Evaluate page-based vs semantic chunking with PyMuPDF / Pixeltable document splitters. |
| RES-04 | Safe Sidecar Export Architecture | Open | Ensure sidecars support hash/mtime validation so re-exports avoid duplicating untouched assets. |
