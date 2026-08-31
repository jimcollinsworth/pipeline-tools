# Pipeline Tools: Multimodal Ingestion, Prompt Workbench & Export Engine

A multimodal ETL and prompt-engineering workbench powered by **Pixeltable** and **Gradio**. Ingest directories of documents, images, audio, and video; test and iterate on LLM extraction/summarization prompts on sample rows; execute scalable batch runs with automatic dependency caching; and export enriched metadata to sidecars (.meta.yaml), CSVs, and Markdown reports.

---

## 🛠 Features

- **Multimodal Directory Ingestion**: Recursively scans and ingests PDF, Markdown, text, images, audio, and video files into a unified Pixeltable store with automatic metadata tracking. Easy selection/type ahead boxes for directory, domain, table, field and other selections.
- **Sample-First Prompt Playground for data enhancement**: 
  - Test entity extraction, summarization, or structured tagging on 1–5 sample rows before running full-scale batch jobs.
  - Support Python function calling for audio/video/image analysis (e.g., beats per minute, spectrograms, object recognition) to feed into table columns without additional LLM calls.
- **Incremental & Cached Execution**: 
  - Uses Pixeltable computed columns to ensure LLM operations are cached, incremental, and version-controlled.
  - Minimize LLM calls per row, support multiple field/column input/templating into the LLM, and accept structured typed output inserted/appended into table columns.
- **Rich Interactive DataTable**: Inspect multimodal content, embedded media, chunks, and LLM extraction results directly in Gradio.
- **Chunking and Combining**:
  - Chunk videos by time/frame, editing breaks (storing frame signatures for before and after the edit), and recognized objects.
  - Manage chunked data relationships with parent/child hierarchies.
- **Rich Search and Filtering**:
  - Select records based on multiple fields using semantic and/or exact text search.
  - Export query results across modalities (video, audio, images, text, markdown) to single or multiple documents.
- **Flexible Export Engine (Integrated in DataTables)**:
  - **LLM-Synthesized Markdown Reports**: Aggregate entire tables or selected rows into cohesive Markdown reports using customizable prompts and selectable columns.
  - **Direct Formatted Document Export**: Generate structured Markdown documents directly from table data without additional LLM calls.
  - Automatic saving to `exports/` with live preview and one-click download.
- **Lineage & Undo**: Full tracking of dataset versions, snapshot tags, and rollback support via Pixeltable.
- **AI Model Support**:
  - Track model and token usage alongside ingestion and enhancement tasks.
  - Built-in support for Ollama and Gemini, including model metadata for selection decisions and connection testing.
- **Skills Support**:
  - Load reusable skills for tasks like entity analysis, domain-specific tasks (e.g., municipal meetings), and model routing.

---

## 🚀 Environment & Toolchain

### Prerequisites
- Python 3.10+ (Python 3.11+ recommended)
- `uv` or standard Python `venv` / `pip`

### Installation & Setup

1. **Clone the repository and initialize virtual environment:**
   ```bash
   cd pipeline-tools

   # Create and activate virtual environment with uv:
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
Run the automated test suite to see detailed test names and status:
```bash
uv run python tests/test_app.py
```

### 1. Launch the Gradio Workbench
```bash
# Recommended during active development (auto-reloads on file save):
uv run gradio app.py

# Or standard execution:
uv run python app.py
```
Open your browser at `http://localhost:7860`.

### 2. Available Tabs & Workflow

1. **📂 Ingestion & Scanner**:
   - Provide any local folder path and click **Scan Directory**.
   - Review files, sizes, and modality breakdown.
   - Enter your Pixeltable target **Domain / Directory** (e.g. `default` or `project_alpha`) and **Table Name** (e.g. `raw_assets`).
   - Click **⚡ Ingest Scanned Files into Pixeltable** (ingests 1 file per row, extracting raw text and metadata).

2. **🧪 Data Enhancement**:
   - Choose your target domain, table, and AI provider (**Ollama** or **Gemini**).
   - Write system prompts and user prompt templates using variable placeholders like `{file_name}`, `{content}`, `{rel_path}`, `{modality}`.
   - Click **🚀 Run Test on Sample Rows** (tests on 1–N rows with side-by-side prompt and output inspection).
   - Enter a target column name (e.g. `llm_summary`, `entities`) and select **replace** or **append** mode (with optional **⚡ Auto-Split** for multi-key JSON outputs).
   - Click **💾 Execute on Table & Save Column** to apply the prompt across table rows.

3. **📊 View & Export**:
   - Inspect stored data, column values, and newly added LLM output columns.
   - Configure prompt-driven Markdown exports (*Entity & Keyword Intelligence*, *Visual & Scene Breakdown*, *Thematic Summary*, *Direct Catalog*).
   - Save directly to `exports/` with live UI preview and instant download.

4. **⚙️ Settings & Models**:
   - Check Ollama server connection, inspect installed models table, and save default configurations.


---

## 🗺 Roadmap

- [x] **Phase 1: Core Document Ingestion & Prompt Playground**
  - Pixeltable unified schema definition.
  - PyMuPDF / Markdown / Text chunkers.
  - Gradio UI with dry-run sample testing & batch execution.
- [ ] **Phase 2: Live Progress & Export Engine**
  - Background task worker with live log streaming.
  - Sidecar .meta.yaml, CSV, and Markdown report generators.
- [ ] **Phase 3: Lineage & Multimodal Expansion**
  - Snapshot explorer and rollback UI.
  - Image OCR/Vision LLM and Audio/Video transcription (Whisper/Gemini).

---

## 📄 Documentation

- [planning.md](planning.md) — Comprehensive task tracking, issues, and research notes.
