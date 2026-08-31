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

```mermaid
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
```

---

## 2. Implementation Roadmap & Task Lists

### Phase 1: Core Foundation & Prompt Playground (Completed & Tested)
- [x] **Environment & Core Config Setup**
  - Dependency setup & config module (`config.json` with Ollama, default models, directories).
  - Minimal automated test suite in `tests/test_app.py` verifying settings, scanner, Pixeltable table creation, and Gradio app loading.
- [x] **Pixeltable Schema & Ingestion Core**
  - Unified table definition (`file_name`, `file_path`, `rel_path`, `modality`, `file_type`, `file_size`, `content`, `doc`, `image`, `audio`, `video`, `metadata`, `created_at`).
  - Domain / directory and table name selection in UI.
  - Ingestion handler: One file → One row, with native text/markdown extraction and direct PDF page text extraction via Pixeltable's bundled `pypdfium2` engine into the `content` column.

- [x] **Prompt Iteration Workbench (Gradio UI)**
  - UI Tab: **Ingestion & Scanner** (directory selector, file filter, scan summary, and Pixeltable ingestion trigger).
  - UI Tab: **Data Enhancement** (select Ollama / Gemini model, enter system/user prompts with `{column}` placeholders, test on 1–N sample rows with side-by-side preview).
  - Column commit workflow: Apply tested prompt across table rows with **Replace** or **Append** modes (and auto-split multi-column JSON outputs).
  - UI Tab: **View & Export** (view table contents, inspect columns, and export prompt-driven Markdown documents).
  - UI Tab: **Settings & Models** (Ollama / Gemini server health test and installed model browser).


### Phase 2: Usability Improvements, Export Engine & Live Monitoring (In Progress)
- [x] **UI Usability & Persistent Inputs**
  - Added dynamic select dropdowns for Domain/Directory and Table names in Data Enhancement tab with automatic auto-refresh when domain changes.
  - Added Live Table Data Preview & Row Count display in Data Enhancement tab (updates automatically on table/domain selection and after batch execution).
  - Fixed table path resolution for preview loading (handles both bare table names `raw_files_test` and domain-prefixed names `eba/raw_files_test` without creating duplicate prefixes).
  - Automatic error formatting and name sanitization (protects against leading digits, dashes, and invalid characters in table/domain names).
  - Saved dialog box last entries (persists last-used domain, table name, model, prompt templates, system prompts, and source directory to `config.json` automatically).
- [x] **Prompt-Driven Markdown Document Export (View & Export Tab)**
  - Integrated export drawer inside the **View & Export** tab with dual mode support:
    1. **LLM Synthesis Report**: Multi-row aggregation via custom prompt template referencing table columns (`{file_name}`, `{visual_summary}`, `{object_tags}`) processed by Ollama or Gemini.
    2. **Direct Template Document**: Formatted Markdown document generated directly from row columns without LLM inference.
  - 4 Task-oriented presets: *Entity & Keyword Intelligence*, *Visual & Scene Breakdown*, *Thematic Summary & Patterns*, and *Direct Structured Catalog*.
  - Visible System Prompt input for clear transparency and instant tuning.
  - Helper pills/tags showing active table columns for easy inclusion in prompts.
  - Automatic file saving to `exports/{domain}_{table}_{timestamp}.md` with real-time UI preview and instant download component.
- [x] **Test Suite Hardening, Isolation & Teardown**
  - Implement isolated test namespaces (`test_suite_isolated`) with reliable `setUpClass`/`tearDownClass` table cleanup.
  - Ensure Windows embedded Postgres locks (`postmaster.pid`) and orphaned sockets are cleanly released on `Ctrl+C` interrupt and normal completion.
  - Add comprehensive edge-case tests (empty directories, unreadable files, corrupt images, missing tables).
- [x] **Embedded Multimodal Media & Interactive Media Inspector**
  - Toggle between fast text-only **⚡ Lightweight Mode** and **🔍 Full Media Mode** across View & Export and Data Enhancement tabs.
  - In Full Mode, table cells render inline HTML thumbnails (`<img>`), audio players (`<audio>`), video players (`<video>`), and document badges (`[PDF]`).
  - Selecting any row in the table opens the **🔬 Selected Record Media Inspector** drawer below the table with full-size image, audio, video, extracted text, and metadata.
- [ ] **Decouple UI Event Handlers into Testable Controllers**
  - Refactor inner closure handlers in `src/ui/` into pure controller functions (`src/controllers/` or module-level helpers).
  - Enable 100% unit test coverage of UI workflows without requiring Gradio web server initialization.
- [ ] **Reassess Playwright for Automated Headless Browser Testing**
  - Re-evaluate introducing `playwright` (`pytest-playwright`) for automated headless browser E2E testing against `http://127.0.0.1:7860`.
  - Compare speed, CI automation, and maintenance overhead against Chrome DevTools MCP and pure Python controller tests.
  - Key criteria: Execution speed (~1-2s headless script vs ~30-90s subagent), zero-dependency constraints, and rich JavaScript DOM/cascade testing.

### Phase 3: Pixeltable Lineage, Undo & Multimodal Extensions (Planned)
- [ ] **Lineage & Snapshots UI**
  - Visualizing Pixeltable version history and tag snapshots.
  - Rollback / undo capabilities for computed columns and schema edits.
  - Audio/Video transcription via Whisper / Gemini Multimodal API with time-coded chunking.
- [ ] **Hugging Face & YOLO Vision Classification Engines**
  - Integrate Ultralytics YOLO classifiers (e.g., `keremberke/yolov8m-painting-classification`) and Hugging Face vision models alongside Ollama/Gemini.
  - Full 27-class art taxonomy classification:
    `['Abstract_Expressionism', 'Action_painting', 'Analytical_Cubism', 'Art_Nouveau_Modern', 'Baroque', 'Color_Field_Painting', 'Contemporary_Realism', 'Cubism', 'Early_Renaissance', 'Expressionism', 'Fauvism', 'High_Renaissance', 'Impressionism', 'Mannerism_Late_Renaissance', 'Minimalism', 'Naive_Art_Primitivism', 'New_Realism', 'Northern_Renaissance', 'Pointillism', 'Pop_Art', 'Post_Impressionism', 'Realism', 'Rococo', 'Romanticism', 'Symbolism', 'Synthetic_Cubism', 'Ukiyo_e']`
  - Output structured JSON predictions (`painting_style`, `confidence`, `style_probabilities`) with automatic column creation via the Auto-Split engine.
  - Selectable as an AI / Vision engine in Data Enhancement with dry-run sample testing and batch table execution.
- [ ] **Mobile & Tablet App Support & Cloud Serving**
  - Architecture options for remote mobile/tablet client access to Pipeline Tools.
  - Mitigate embedded PostgreSQL mobile limitation by deploying the Gradio + Pixeltable server to cloud/container hosts with persistent volumes (or remote managed Postgres) while serving a progressive web UI to mobile clients.
  - Cloud deployment options: Hugging Face Spaces with persistent storage, Docker container on AWS/GCP/Fly.io, or desktop LAN host with secure tunnel.
- [ ] **Responsive Mobile & Tablet UI Design**
  - Implement mobile-friendly viewport breakpoints (`@media (max-width: 768px)`).
  - Single-column stacked layouts, touch-friendly tap targets ($\ge 44\text{px}$), and adaptive table views (horizontal scroll cards / compact summary cards) for phone and tablet screens.

---

## 3. Issues & Research Items

| ID | Topic | Status | Description / Decision |
|---|---|---|---|
| RES-01 | Pixeltable Chunking vs Table Structure | Complete | Use unified table with text/media columns, chunk views for document-level splitting, and computed columns for LLM calls. |
| RES-02 | Windows PostgreSQL Locking & Concurrency | Complete | Muted noisy logs; registered SIGINT/atexit hooks to clean up sockets and prevent orphaned postmaster.pid lock contention. |
| RES-03 | Model Discovery Timeout | Complete | Reduced Ollama timeout to 2s; added Gemini client for cloud model discovery and multi-provider routing. |
| RES-04 | JSON Auto-Splitting in Table Insertion | Complete | Extract JSON payloads across markdown fences/raw brackets and dynamically create Pixeltable columns via infer_pixeltable_type. |
| RES-05 | UI Layout & CSS Stability | Complete | Enforced max-width 95% and tabitem full-width rules to prevent Gradio tab shifting; updated launch config to Gradio 6.0 standards. |
| RES-06 | Tool Calling & MCP Integration | Open | Single LLM call per row with tool calling support for vision and audio functions. Evaluate MCP integration for efficiency. |
| RES-07 | Playwright vs. Chrome DevTools Testing | Open | Evaluated interactive Chrome DevTools MCP vs headless Playwright for web E2E testing. Deferred Playwright until automated browser regression suite is needed. |
| RES-08 | Hugging Face & YOLO Vision Model Architecture | Open | Planned integration of Hugging Face Hub / Ultralytics vision classifiers (e.g. WikiArt 27-movement classifier) with output auto-splitting into Pixeltable table columns. |
| RES-09 | Mobile / Tablet Architecture & Cloud Serving | Open | Overcome embedded PostgreSQL mobile restriction by hosting Gradio + Pixeltable on cloud containers / remote server with persistent volume, serving responsive PWA to mobile devices. |
| RES-10 | Responsive Mobile / Tablet Design | Open | Adapt Gradio layout with mobile CSS breakpoints, stacked columns, touch-friendly button targets (>=44px), and compact card table views. |
