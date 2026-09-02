# Pipeline Tools: Multimodal Ingestion, Prompt Workbench & Export Engine

A multimodal ETL and prompt-engineering workbench powered by **Pixeltable** and **Gradio**. Ingest directories of documents, images, audio, and video; test and iterate on LLM extraction/summarization prompts on sample rows; execute scalable batch runs with automatic dependency caching; and export enriched metadata to sidecars (.meta.yaml), CSVs, and Markdown reports.

---

## 🛠 Features

- **Multimodal Directory Ingestion & Scanner**:
  - Recursively scans local project folders, classifying files into modalities (*Docs*, *Images*, *Audio*, *Video*, *Code*).
  - One-file-to-one-row ingestion with native text extraction (Markdown, TXT) and PDF page extraction via Pixeltable's bundled `pypdfium2` engine into the `content` column.
  - Intelligent filterable type-ahead dropdowns for directories, domains, and tables with automatic discovery.
- **Sample-First Prompt Playground (Data Enhancement)**:
  - Dry-run and iterate on system/user prompts with `{column}` placeholders across 1–N sample rows before running full-scale batch jobs.
  - **⚡ JSON Auto-Split Engine**: Extract structured JSON payloads from model output and dynamically create native Pixeltable schema columns (`pxt.String`, `pxt.Int`, `pxt.Float`, `pxt.Json`, `pxt.Bool`) in one pass.
- **Incremental & Cached Execution**:
  - Leverages Pixeltable declarative computed columns to ensure LLM operations are cached, incremental, and version-controlled.
  - Minimizes redundant LLM calls per row, and accepts structured typed output inserted/appended into table columns.
- **Embedded Multimodal Media & Interactive Inspector**:
  - Fast **⚡ Lightweight Mode** (skips binary deserialization, reducing Python RAM by >95%) and **🔍 Full Media Mode** with inline HTML thumbnails (`<img>`), audio players (`<audio>`), video players (`<video>`), and PDF badges.
  - Interactive **🔬 Selected Record Media Inspector** drawer opens on row selection for deep inspection of full-resolution images, audio playback, video playback, and extracted text.
- **1-Click Lineage Undo & Safe Database Management**:
  - **↩️ 1-Click Undo**: Instantly drops newly added LLM columns (including auto-split columns) and rolls back table schema without touching raw ingested assets.
  - **🗑️ Safe Deletion**: 2-step confirmation drawers for dropping individual tables or entire domains with on-screen summary cards and logging.
- **Unified AI-Driven Markdown Report Generation (View & Export)**:
  - Synthesize multi-row table data into cohesive Markdown documents using Ollama or Gemini with full `{table_context}` interpolation.
  - 4 Task-oriented presets: *Entity & Keyword Intelligence*, *Visual & Scene Breakdown*, *Thematic Summary & Patterns*, and *Structured Media Catalog*.
  - Live in-browser Markdown preview and instant 1-click file download from `exports/`.
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
   - Configure prompt-driven Markdown exports (*Entity Intelligence*, *Visual Breakdown*, *Thematic Summary*, *Structured Catalog*).
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
- [ ] **Phase 3: Lineage, Controller Decoupling & Multimodal Extensions**
  - Decouple UI event handlers into testable pure controllers (`src/controllers/`).
  - Hugging Face model hub & Ultralytics YOLO vision classification engines (e.g. WikiArt 27-movement painting classifier) with dynamic table auto-split columns.
  - Mobile / tablet responsive UI design (`@media (max-width: 768px)`).
  - Multi-branch version history and table revision timeline.
- [ ] **Phase 4: Dynamic Ingestion Context, Skills Integration & Document Reader**
  - Stateful dynamic context accumulation across multi-row ingestion for entity deduplication and learned dataset intelligence (`domain-table-ingestion-context.md`).
  - Project skills integration with in-prompt `/` slash command discovery from `.agents/skills/`.
  - Single-record rich Markdown Document Reader with collapsible sections, theme selectors, and embedded Mermaid diagrams.
  - Touch-friendly visual column pill toggles and LLM-assisted prompt chip insertion.

---

## 📄 Authorized Documentation

This project strictly adheres to a 3-document architecture:

- **[README.md](README.md)** — What the tool is, capabilities, toolchain, and how to use.
- **[planning.md](planning.md)** — Steps to build, system architecture, engineering design, tasks, and research items.
- **[journal.md](journal.md)** — Chronological record of developer directives, mentoring notes, and key architectural decisions.
