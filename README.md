# Pipeline Tools: Multimodal Ingestion, Prompt Workbench & Export Engine

A multimodal ETL and prompt-engineering workbench powered by **Pixeltable** and **Gradio**. Ingest directories of documents, images, audio, and video; test and iterate on LLM extraction/summarization prompts on sample rows; execute scalable batch runs with automatic dependency caching; and export enriched metadata to sidecars (.meta.yaml), CSVs, and Markdown reports.

---

## 🛠 Features

- **Multimodal Directory Ingestion**: Recursively scans and ingests PDF, Markdown, text, images, audio, and video files into a unified Pixeltable store with automatic metadata tracking.
- **Sample-First Prompt Playground**: Test entity extraction, summarization, or structured tagging on 1–5 sample rows before running full-scale batch jobs.
- **Incremental & Cached Execution**: Uses Pixeltable computed columns to ensure LLM operations are cached, incremental, and version-controlled.
- **Rich Interactive DataTable**: Inspect multimodal content, embedded media, chunks, and LLM extraction results directly in Gradio.
- **Flexible Export Engine**:
  - Sidecar metadata files (.meta.yaml / .json) co-located or mirrored in an output directory.
  - Tabular exports (CSV / Parquet) for downstream pipeline stages.
  - Markdown summary reports and optional frontmatter injection.
- **Lineage & Undo**: Full tracking of dataset versions, snapshot tags, and rollback support via Pixeltable.

---

## 🚀 Environment & Toolchain

### Prerequisites
- Python 3.10+ (Python 3.11+ recommended)
- `uv` or standard Python `venv` / `pip`

### Installation & Setup

1. **Clone the repository and initialize virtual environment:**
   ```bash
   cd d:\projects\pipeline-tools

   # Create and activate virtual environment with uv:
   uv venv
   .\.venv\Scripts\Activate.ps1

   # Or using standard venv:
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```bash
   # Using uv:
   uv pip install -e .

   # Or using standard pip:
   pip install -e .
   ```

3. **Configure API Keys:**
   Create a `.env` file or export your environment keys:
   ```bash
   OPENAI_API_KEY=your_openai_key
   ANTHROPIC_API_KEY=your_anthropic_key
   GEMINI_API_KEY=your_gemini_key
   ```

---

## 💻 Usage & DevOps Commands

### Testing & Verification
Run the automated test suite to see detailed test names and status:
```bash
uv run python tests/test_app.py
```

---

## 💻 Usage & Workflows

### 1. Launch the Gradio Workbench
```bash
.\.venv\Scripts\python.exe app.py
```
Open your browser at `http://localhost:7860`.

### 2. Available Tabs & Workflow

1. **📂 Ingestion & Scanner**:
   - Provide any local folder path and click **Scan Directory**.
   - Review files, sizes, and modality breakdown.
   - Enter your Pixeltable target **Domain / Directory** (e.g. `default` or `project_alpha`) and **Table Name** (e.g. `raw_assets`).
   - Click **⚡ Ingest Scanned Files into Pixeltable** (ingests 1 file per row, extracting raw text and metadata).

2. **🧪 Prompt Playground**:
   - Choose your target domain, table, and local **Ollama model**.
   - Write system prompt and user prompt template using variable placeholders like `{file_name}`, `{content}`, `{rel_path}`.
   - Click **🚀 Run Test on Sample Rows** (tests on 1–N rows with side-by-side prompt and output inspection).
   - Enter a target column name (e.g. `llm_summary`, `entities`) and select **replace** or **append** mode.
   - Click **💾 Execute on Table & Save Column** to apply the prompt to table rows.

3. **📊 Lineage & DataTables**:
   - Enter Domain and Table name to inspect stored data, column values, and newly added LLM output columns.

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
