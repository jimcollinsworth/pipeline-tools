# Pipeline Tools v1.1: Multimodal Ingestion, Prompt Workbench & Export Engine

A multimodal ETL and prompt-engineering workbench powered by **Pixeltable** and **Gradio**. Ingest directories of documents, images, audio, and video; test and iterate on LLM extraction/summarization prompts on sample rows; execute scalable batch runs with automatic dependency caching; and export enriched metadata to per-row sidecars (`_meta.md`), CSVs, and synthesized Markdown reports.

---

## 💡 Why Pipeline Tools? (Philosophy)

Many modern "all-in-one" RAG frameworks, monolithic chat apps, and autonomous agent harnesses attempt to do too much implicitly—hiding chunking decisions, opaque vector lookups, prompt mutations, and silent failures behind heavy abstractions.

**Pipeline Tools is built on a different philosophy: small, transparent, and controllable steps.**
- **Take Any Directory**: Point the scanner at any local folder containing an ad-hoc mix of text documents, PDFs, photos, audio memos, or video clips.
- **Inspect & Control**: Inspect every file in the Media Drawer, test extraction and synthesis prompts across 1–2 sample rows first, and verify what the LLM actually sees before committing to batch operations.
- **Generate Reusable Markdown Sidecars**: Execute prompts per row to generate structured Markdown sidecar files (`_meta.md`) with clean YAML frontmatter and standard media links.
- **Compounding LLM Wiki vs. Ephemeral RAG**: Instead of rediscovering facts from scratch on every query, the workbench maintains an evolving Markdown wiki (`{domain}_{table}_context.md`) per domain and table. Discoveries, canonical entities, aliases, and source citations compound over time.
- **Feed Downstream Engines**: Rather than locking your data inside a proprietary vector store, the enriched Markdown sidecars and compiled wikis become portable assets ready to power external RAG pipelines, Obsidian knowledge vaults, or autonomous coding/research agents.
- **Powered by Pixeltable**: Declarative computed columns, zero-memory database streaming, versioned table lineage, and automatic incremental caching make Pixeltable the ideal multimodal foundation for this workflow.

---

## 🎯 Real-World Use Cases

### 🏢 Use Case 1: Building Co-op & HOA Document Intelligence (EBA Building)
* **Goal**: Index, cross-reference, and research decades of building co-op and HOA meeting notes, financial proposals, vendor bids, bylaws, and maintenance logs without getting lost in deep folder hierarchies.
* **Pipeline Tools Workflow**:
  1. **Ingest Archive**: Point the directory scanner at the building's historical records folder (`PDFs`, meeting minutes, budget spreadsheets, contractor proposals) and ingest them into domain `coop_hoa`, table `documents`.
  2. **Extract & Structure (Data Enhancement)**: Use the prompt workbench on 2 sample rows with Gemini or Ollama to extract voting outcomes, monetary figures, contractor names, maintenance deadlines, and action items into clean JSON keys (`meeting_date`, `vote_passed`, `expenditure_usd`, `contractor`, `action_items`). The ⚡ Auto-Split engine turns these into queryable database columns.
  3. **Inspect & Triage (View & Export)**: Use the Media Inspector drawer to preview scans and PDFs side-by-side with extracted metadata.
  4. **Export Knowledge Sidecars**: Run the **Per-Row Sidecars** exporter to generate `{file_stem}_meta.md` dossiers with YAML frontmatter, or run **Single Synthesis** to generate a comprehensive 5-year building maintenance timeline for board review. These Markdown files directly feed into local RAG engines or personal search tools.

---

### 🧠 Use Case 2: Personal Daily Multimodal Pipeline (Life OS & Second Brain)
* **Goal**: Ingest an ongoing daily stream of ad-hoc captures—phone photos, quick voice memos, whiteboard sketches, starred email exports, chat messages, and video snippets. Automatically categorize, rank, transcribe audio, identify visual objects, and surface high-priority thoughts (`!ideas!`, `?questions?`, `*todos*`).
* **Pipeline Tools Workflow**:
  1. **Continuous Ingestion**: Point the scanner at the daily inbox capture folder (e.g. `captures/2026-09-03/`) and append to the `daily_journal` table.
  2. **Enrich & Classify**:
     - Voice memos and audio recordings are transcribed and summarized.
     - Images and video frames have key subjects/objects identified (e.g., *car, bus, violin, sax, Beethoven's 8th, Netflix action comedy*).
     - Prompts parse text notes to extract and categorize key markers: `!ideas!`, `?questions?`, and `*todos*`.
  3. **Verify in Workbench**: Review newly ingested daily entries with lightweight previews and instant media playback in the interactive inspector.
  4. **Redistribute & Action**: Generate per-row sidecars (`{file_name}_meta.md`) linking back to the source media (local paths, Google Drive, Google Photos). Exported Markdown files automatically sync into **Obsidian** vaults, **Google Drive**, or trigger autonomous **Antigravity coding & research agents** for scheduled follow-ups and action items.

---

## 🛠 Features

- **Multimodal Directory Ingestion & Scanner**:
  - Recursively scans local project folders, classifying files into modalities (*Docs*, *Images*, *Audio*, *Video*, *Code*).
  - One-file-to-one-row ingestion with native text extraction (Markdown, TXT) and PDF page extraction via Pixeltable's bundled `pypdfium2` engine into the `content` column.
  - Intelligent filterable type-ahead dropdowns for directories, domains, and tables with automatic discovery.
- **Sample-First Prompt Playground & Telemetry Engine (Data Enhancement)**:
  - Dry-run and iterate on system/user prompts with `{column}` placeholders across 1–N sample rows before running full-scale batch jobs.
  - **⏱️ Live Performance & Throughput Telemetry**: Real-time measurement and display of execution speed (`tokens/sec`), prompt ingest time, eval duration, and token counts for every model invocation.
  - **🖼️ Multimodal Vision Guard**: Gated via an explicit `Multimodal Vision` toggle. Prevents accidental 10–15s vision model inference and heavy base64 image uploads during pure text/metadata operations, delivering <1.0s response times.
  - **⚡ JSON Auto-Split Engine**: Extract structured JSON payloads from model output and dynamically create native Pixeltable schema columns (`pxt.String`, `pxt.Int`, `pxt.Float`, `pxt.Json`, `pxt.Bool`) in one pass.
- **Pixeltable Declarative Compute & In-Engine Caching**:
  - Eliminates sequential imperative Python loops by leveraging Pixeltable's declarative `@pxt.udf` compute engine.
  - **Automatic PostgreSQL Caching**: Computations are cached at the database cell level; existing rows are served in 0.001s without redundant LLM calls.
  - **Zero-Cost JSON Unpacking**: Unpacks JSON dictionary keys directly into individual computed columns via native database projections without making additional LLM calls.
  - **Incremental Execution**: Inserting new records into an enriched table automatically triggers the computed column pipeline *only* for the newly added rows.
- **Declarative Data Management & Media Inspector**:
  - Fast **⚡ Lightweight Mode** (skips binary deserialization, reducing Python RAM by >95%) and **🔍 Full Media Mode** with inline HTML thumbnails (`<img>`), audio players (`<audio>`), video players (`<video>`), and PDF badges.
  - **Zero-Memory Database Streaming**: Large text columns (`content`) are sliced directly inside the database engine (`table.content.slice(0, 500)`), avoiding loading multi-megabyte strings into Python RAM. All table cells are safely truncated to 250 characters, keeping Gradio WebSocket payloads under 50 KB.
  - Ingestion safeguards cap text extraction from giant files (CSVs, server logs) at 1 MB to prevent memory bloat.
  - Interactive **🔬 Selected Record Media Inspector** drawer opens on row selection for on-demand inspection of full-resolution images, audio playback, video playback, and extracted text.
- **1-Click Lineage Undo & Safe Database Management**:
  - **↩️ 1-Click Undo**: Instantly drops newly added LLM columns (including auto-split columns) and rolls back table schema without touching raw ingested assets.
  - **🗑️ Safe Deletion**: 2-step confirmation drawers for dropping individual tables or entire domains with on-screen summary cards and logging.
- **Dual Export Strategies & Live Streaming Previews (View & Export)**:
  - **📄 Single Document Synthesis**: Aggregates multi-row dataset context into one structured Markdown briefing, intelligence dossier, or media catalog (`exports/{domain}_{table}_report_{timestamp}.md`).
  - **🗂️ Per-Row Sidecars (`_meta.md`)**: Executes one LLM call per row to produce rich, standalone sidecar documents (`exports/{source_stem}_meta.md`) with clean YAML frontmatter, automatic row-specific image embedding (`![photo](file_path)`), and continuous real-time preview updates in the browser.
  - **Fast Markdown Constraints & Media Safety**: Exports pass pure text metadata and local path strings to LLMs—never uploading raw binary media. Prompts strictly enforce clean GitHub-flavored Markdown and forbid heavy raw HTML/SVG code, keeping row generation fast (1–2 seconds) and preventing 30+ second latency spikes.
  - **Task-Oriented Presets**: *📰 Newspaper Story & Embedded Photo*, *Entity & Keyword Intelligence*, *Visual & Scene Breakdown*, *Thematic Summary & Patterns*, and *Structured Media Catalog*.
  - Live in-browser Markdown preview and instant 1-click file download from `exports/`.
- **Decoupled Controller Layer**:
  - Strict separation of concerns between Gradio UI tab views (`src/ui/`) and pure business logic controllers (`src/controllers/`): `IngestController`, `PlaygroundController`, and `TablesController`.
  - Enables direct, isolated unit testing of database operations, file scans, prompt execution, and exports without browser server overhead.
- **Multi-Provider AI Engine**:
  - **Local Ollama**: Fast, zero-cost local LLMs (`llama3.2`, `mistral`, `qwen2.5-coder`, `deepseek-r1`).
  - **Google Gemini API**: Native cloud model discovery prioritizing the **Gemini 3.7** and **Gemini 3.0** model families with structured output.

---

## 🚀 Environment & Toolchain

### Prerequisites
- Python 3.10+ (Python 3.11+ recommended)
- `uv` (recommended) or standard Python `venv` / `pip`

### Installation & Setup

1. **Clone the repository and initialize virtual environment:**
   ```bash
   cd pipeline-tools

   # Create virtual environment with uv:
   uv venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```bash
   # Using uv:
   uv pip install -e .
   ```

3. **Configure API Keys:**
   Create a `.env` file or export your environment keys:
   ```bash
   GEMINI_API_KEY=your_gemini_key
   # OLLAMA_HOST=http://localhost:11434  # optional, defaults to localhost
   ```

---

## 💻 Usage & Workflows

### Testing & Verification
Run the automated test suite with formatted execution metrics:
```bash
uv run python -m tests
```

### 1. Launch the Gradio Workbench
```bash
# Recommended during active development (auto-reloads on file save):
uv run gradio app.py

# Or standard execution:
uv run python app.py
```
Open your browser at `http://127.0.0.1:7860`.

### 2. Available Tabs & Workflow

1. **📂 Ingestion & Scanner**:
   - Provide any local folder path and click **Scan Directory**.
   - Review files, sizes, and modality breakdown.
   - Select your target **Domain / Directory** (e.g. `default` or `project_alpha`) and **Table Name** (e.g. `raw_assets`).
   - Click **⚡ Ingest Scanned Files into Pixeltable** (ingests 1 file per row, extracting raw text and metadata).

2. **🧪 Data Enhancement**:
   - Choose your target domain, table, and AI provider (**Ollama** or **Gemini**).
   - Write system prompts and user prompt templates using variable placeholders like `{file_name}`, `{content}`, `{rel_path}`, `{modality}`.
   - Click **🚀 Run Test on Sample Rows** (tests on 1–N rows with side-by-side prompt and output inspection).
   - Enter a target column name (e.g. `llm_summary`, `entities`) and select **replace** or **append** mode (with optional **⚡ Auto-Split** for multi-key JSON outputs).
   - Click **💾 Execute on Table & Save Column** to apply the prompt across table rows.
   - Use **↩️ Undo Last Operation** to revert newly added columns if needed.

3. **📊 View & Export**:
   - Inspect stored data, column values, and newly added LLM output columns.
   - Toggle **⚡ Lightweight Preview** off to view embedded HTML image thumbnails, audio players, and video widgets.
   - Click any row to open the **🔬 Selected Record Media Inspector** drawer for full-resolution preview.
   - Select export strategy: **📄 Single Document Synthesis** (aggregates all records) or **🗂️ Per-Row Sidecars (_meta.md)** (1 LLM call per row with auto-embedded media and live streaming preview).
   - Choose from 5 presets (*Newspaper Story*, *Entity Intelligence*, *Visual Breakdown*, *Thematic Summary*, *Structured Catalog*) or compose custom prompts.
   - Save directly to `exports/` with live UI preview and instant download.
   - Safely delete tables or entire domains using the confirmation drawers.

4. **⚙️ Settings & Models**:
   - Check Ollama / Gemini server connection, inspect installed models table, and save default configurations.

---

## 🗺 Roadmap

- [x] **Phase 1: Core Document Ingestion & Prompt Playground**
  - Pixeltable unified schema definition and identifier sanitization.
  - Multi-modal directory scanner and text extraction.
  - Gradio UI with dry-run sample testing & batch execution.
- [x] **Phase 2: Test Hardening, Media Inspection & Export Engine**
  - Test suite isolation with automated teardown hooks.
  - In-table HTML media thumbnails, audio/video players, and interactive Media Inspector drawer.
  - 1-Click Lineage Undo and safe table/domain deletion workflows.
  - Unified AI Markdown report export engine with `{table_context}` interpolation.
- [x] **Phase 3: Controller Decoupling & Dual Export Strategies (v1.1)**
  - Decoupled Gradio UI event handlers into testable pure controllers (`src/controllers/`).
  - Dual Export Strategies: Single Synthesis vs. Per-Row Sidecars (`{source_stem}_meta.md`) with continuous live preview streaming.
  - Binary media validation safeguards preventing table insertion errors on missing files.
  - Expanded automated test suite to 38 tests (`38 Passed, 0 Failed, 0 Errors`).
- [ ] **Phase 4: Multimodal Vision & Entity Classification Engines**
  - GLiNER zero-shot Named Entity Recognition (`urchade/gliner`) for fast, hallucination-free entity extraction.
  - Hugging Face model hub & Ultralytics YOLO vision classification engines (e.g. WikiArt 27-movement classifier).
  - Mobile / tablet responsive UI design (`@media (max-width: 768px)`).
- [ ] **Phase 5: Dynamic Ingestion Context, Compounding LLM Wiki & Document Reader**
  - Compounding LLM Wiki per domain/table (`{domain}_{table}_context.md`) maintaining canonical entities, aliases, and source citations (`[doc](filepath)`).
  - Dynamic cross-row context accumulation across multi-row ingestion, enhancement, and export.
  - EBA cross-reference index generation (`index.md`) for organizational dossiers.
  - Project skills integration with in-prompt `/` slash command discovery from `.agents/skills/`.
  - Single-record rich Markdown Document Reader with collapsible sections, theme selectors, and embedded Mermaid diagrams.
  - Touch-friendly visual column pill toggles and LLM-assisted prompt chip insertion.

---

## 📄 Authorized Documentation

This project strictly adheres to a 3-document architecture:

- **[README.md](README.md)** — What the tool is, capabilities, toolchain, and how to use.
- **[planning.md](planning.md)** — Steps to build, system architecture, engineering design, tasks, and research items.
- **[journal.md](journal.md)** — Chronological record of developer directives, mentoring notes, and key architectural decisions.
