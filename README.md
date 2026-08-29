# Pipeline Tools: Multimodal Ingestion, Prompt Workbench & Export Engine

A multimodal ETL and prompt-engineering workbench powered by **Pixeltable** and **Gradio**. Ingest directories of documents, images, audio, and video; test and iterate on LLM extraction/summarization prompts on sample rows; execute scalable batch runs with automatic dependency caching; and export enriched metadata to sidecars (.meta.yaml), CSVs, and Markdown reports.

---

## 🛠 Features

- **Multimodal Directory Ingestion**: Recursively scans and ingests PDF, Markdown, text, images, audio, and video files into a unified Pixeltable store with automatic metadata tracking. Easy selection/type ahead boxes for directory, domain, table, field and other selections.
- **Sample-First Prompt Playground for data enhancement**: 
  - Test entity extraction, summarization, or structured tagging on 1–5 sample rows before running full-scale batch jobs.
  - Tool running for audio/video/image analysis, ie; beats per min, spectrogram, object recognition. Not sure if we want full MCP support, more important is fast calls to CV, audio and other functions, maybe just support python function calling. Initally lets put in a couple useful audio and video data enhancement functions, the outputs would be fed into new/existing columns. We do NOT want extra LLM calls here, but want to take advantage of tool calling if possible.
- **Incremental & Cached Execution**: 
  - Uses Pixeltable computed columns to ensure LLM operations are cached, incremental, and version-controlled.
  - Minimize LLM calls per row, support multiple field/column input/templating into the LLM, and accept multiple field output of the LLM, inserted/appended into table columns. consider a well supported typed data interface with the LLM 
- **Rich Interactive DataTable**: Inspect multimodal content, embedded media, chunks, and LLM extraction results directly in Gradio.
- **Chunking and combining**
  - chunk videos by time/frame, editing breaks (store both the frame signiture for before and after the edit), recognized object (find segments with ? in the video)
  - ?how does pixeltable store chunked data relationships is there a parent/child UUID
- **Rich search/filtering**
  - select based on one or more fields, using semantic and/or exact text
  - can feed everything into a tool/llm, and output video, audio, images, text, markdown, one document or many (10's not hundreds or more)
- **Flexible Export Engine**:
  - Sidecar metadata files (.meta.yaml) co-located or mirrored in an output directory.
  - Tabular exports (CSV) for downstream pipeline stages.
  - Markdown summary reports and optional frontmatter injection.
- **Lineage & Undo**: Full tracking of dataset versions, snapshot tags, and rollback support via Pixeltable.
- **AI model support**
  - track model, token usage along with ingestion, enhancement and other tasks
  - ollama and gemini support - query models show meta data useful for model selection decisions, test connection button.  
- **Skills support**
  - want to load in skills for entity analysis, or municipal meeting, or best LLM models to use
  - 

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

\\TODO remove 'standard venv, we are just using uv
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
