# AGENTS.md - Repository Guidelines & Agent Instructions

This document defines core conventions, toolchain rules, architecture patterns, UI standards, and behavioral coding guidelines for the **Pipeline Tools** codebase.

---

## 🛠 1. Toolchain & Environment Rules

- **Python & Package Manager**:
  - Exclusively use **`uv`** (or standard `pip` inside the virtual environment).
  - **NEVER** use `conda` or suggest Conda commands.
  - Dependencies must always be declared in `pyproject.toml`.
- **Primary Commands**:
  - Launch with live auto-reload (recommended during development): `uv run gradio app.py`
  - Launch standard: `uv run python app.py`
  - Run test suite: `uv run python -m tests` (or `uv run python tests/test_app.py`)
  - Install dependencies: `uv pip install -e .`

---

## 🔒 2. Secrets Management & Credentials Safety

- **Never Commit Secrets or API Keys**:
  - API keys (`GEMINI_API_KEY`, etc.), tokens, and passwords must **never** be committed to version control.
  - Always keep `config.json`, `.env`, and local database/cache directories (`.pixeltable_data/`, `exports/`) in `.gitignore`.
  - Provide sanitized template files (`config.example.json`, `.env.example`) containing only empty/null placeholders.
  - When persisting settings locally to `config.json`, ensure `config.json` is untracked and ignored by Git.
  - Prefer reading sensitive credentials from environment variables (`os.environ.get("GEMINI_API_KEY")`) or `.env` files.

---

## 🏛 3. Architecture & Core Technologies

- **Pixeltable (`src/db/manager.py`)**:
  - Multimodal declarative database layer for document/media ingestion, computed columns, and lineage.
  - Tables are grouped under directories/domains (e.g. `default`, `project_alpha`).
  - Sanitize all SQL/Pixeltable table and column identifiers with `sanitize_identifier()`.
  - **Mandatory Declarative Invariant (Strict Prohibition of Imperative Loops)**:
    - Imperative loops (`for row in ...:`, `table.update()`) calling AI models or updating table rows sequentially are **strictly forbidden**.
    - All table transformations, prompt evaluations, entity extractions, and model enrichments must use `@pxt.udf` and native declarative computed columns (`table.add_computed_column`).
    - **Exception Policy**: Any exception to declarative computed columns requires explicit developer authorization and documented justification in `journal.md`.
  - **High-Scale Ingestion Memory Invariant (Supporting 10,000+ Rows)**:
    - Ingestion of files into Pixeltable must use **chunked batch streaming** (batch size $\le 200$, default 100) to bound memory usage to $O(1)$.
    - Never accumulate all scanned files or raw text strings in a monolithic in-memory list before calling `table.insert()`.
  - **Dual Ingestion Mode Architecture**:
    - **Mode 1 (Directory Multi-Asset Scanner)**: Ingests unstructured folders of media (*Docs*, *Images*, *Audio*, *Video*) mapping 1 file $\rightarrow$ 1 Pixeltable row.
    - **Mode 2 (Single Row-Oriented File / CSV)**: Targets a single CSV/TSV without recursive traversal, ingesting **each row as an individual document record** into Pixeltable (`file_name="{file.csv} #Row {idx}"`, `content=primary_text_col or formatted summary`, `metadata=full_row_dict`, `modality="docs"`).
    - Prompt templates support direct `{column}` placeholders from CSV metadata via automatic fallback to `row["metadata"]`.
  - **Embedded PostgreSQL Process Safety Invariant**:
    - Embedded lock self-healing (`DBManager.heal_postgres_locks`) must strictly protect the active Python process and its descendant PIDs (`protected_pids = {os.getpid()} | children`).
    - Never terminate active database servers mid-lifecycle or between test cases. Pre-flight self-healing should run only once at process startup or test suite initialization with `force_purge_orphans=False`.
- **Local LLM Engine (`src/core/ollama_client.py` & `src/prompts/executor.py`)**:
  - Ollama REST API for local model discovery, health checks, and batched prompt execution.
- **Configuration & Persistence (`src/core/config.py`)**:
  - Application settings are managed via Pydantic `Settings`.
  - User selections (recent directories, selected domain/table, prompt templates, models) must be persisted to `config.json` via `update_last_entry()`.

---

## 🔒 3. Framework & Dependency Stability

- **No Unauthorized Framework Switches or Upgrades**:
  - Updating, upgrading, or switching framework components is **never allowed** during normal coding.
  - Only consider upgrades or alternatives when explicitly requested to perform deep design, architecture work, or explore alternatives.
  **NEVER** use introspection of private interfaces to determine apis/functions, look up current skills and online api reference for the currently used versions
---

## 🎨 4. UI / UX Standards (Gradio)

- **Layout Stability & Full-Width Rules**:
  - Always ensure all tabs maintain a consistent full width to prevent UI jumping/shifting when switching tabs.
  - CSS rule required in `app.py`:
    ```css
    .gradio-container { max-width: 95% !important; width: 95% !important; margin: auto; }
    .tabitem { width: 100% !important; min-width: 100% !important; }
    ```
  - Dataframes must have `min_width` set (e.g. `min_width=800`) and `wrap=True`.
- **Directory / Path Input**:
  - Prefer compact, intelligent **Filterable Type-Ahead Dropdowns** (`gr.Dropdown(allow_custom_value=True, filterable=True)`) over heavy multi-component directory trees.
  - Auto-discover directory suggestions from Project CWD, User Home, subdirectories, and saved path history.
- **Port Management**:
  - Server defaults to port `7860`.
  - Do not spawn random dynamic fallback ports. If port 7860 is occupied, catch `OSError` and output a clean, friendly notification directing the user to `http://127.0.0.1:7860`.

---

## 🧪 5. Testing & Code Quality

- **Running Tests & Stratification**:
  - Always verify changes with `uv run python -m tests`.
  - **Stratified Test Execution**:
    - **Fast Core Suite (`uv run python -m tests`)**: Executes unit and controller tests deterministically in $< 15$ seconds without spawning ephemeral web servers or headless browsers.
    - **On-Demand E2E Suite (`uv run python -m tests --e2e`)**: Runs the Playwright headless browser suite across viewports and interactive UI flows only on demand.
    - **Remote Cloud Testing**: Remote instances (e.g. Hugging Face Spaces) must never be tested during regular local test loops; test them only on demand with specialized scripts.
  - Test runner must use `CleanTestRunner` to mute third-party logger noise (`Pixeltable`, Python 3.13 `asyncio` loop warnings) and provide formatted timing metrics.
  - Maintain descriptive docstrings (`[Config]`, `[Scanner]`, `[UI]`, `[Database]`, `[Ingest]`, `[Controller]`) on all test methods.
  - Ensure Windows terminal encoding compatibility (`cp1252` safe or `reconfigure(encoding='utf-8')`).

---

## 🧠 6. Behavioral Guidelines (Karpathy Guidelines)

Guidelines to reduce common LLM coding pitfalls, biasing toward caution and simplicity over speed:

### 0. Action Rationale & Concise Communication
- **Always provide a clear reason** before taking any tool action or asking a question.
- **State issues and solutions concisely in 1 to 2 sentences at most.**

### 1. Think Before Coding
*Don't assume. Don't hide confusion. Surface tradeoffs.*
- **State assumptions explicitly**: If uncertain, ask.
- **Present alternatives**: If multiple interpretations exist, present them rather than picking silently.
- **Propose simpler approaches**: If a simpler approach exists, say so. Push back when warranted.
- **Stop when unclear**: If something is confusing or underspecified, stop and clarify.

### 2. Simplicity First
*Minimum code that solves the problem. Nothing speculative.*
- No features beyond what was explicitly requested.
- No abstractions or helpers for single-use code.
- No "flexibility" or "configurability" that wasn't asked for.
- No defensive error handling for impossible scenarios.
- If you write 200 lines and it could be done in 50, rewrite it.
- Ask: *"Would a senior engineer say this is overcomplicated?"* If yes, simplify.
- **Declarative Computed Columns Over Imperative Loops**: Always express data mutations, AI completions, and feature extraction as Pixeltable `@pxt.udf` computed columns. Imperative row-by-row loops require explicit documented authorization.

### 3. Surgical Changes
*Touch only what you must. Clean up only your own mess.*
- When editing existing code:
  - Do not "improve" adjacent code, comments, or formatting without request.
  - Do not refactor things that aren't broken.
  - Match existing style, even if you'd write it differently.
  - If you notice unrelated dead code, mention it—don't delete it.
- When changes create orphans:
  - Remove imports/variables/functions that *your* changes made unused.
  - Do not remove pre-existing dead code unless asked.
- **The Golden Test**: Every changed line must trace directly to the user's request.

### 4. Goal-Driven Execution
*Define success criteria. Loop until verified.*
- Transform tasks into verifiable goals:
  - *"Add validation"* → Write tests for invalid inputs, then make them pass.
  - *"Fix the bug"* → Write a test reproducing it, then make it pass.
  - *"Refactor X"* → Verify tests pass before and after.
- For multi-step tasks, state a brief plan:
  1. `[Step]` → verify: `[check]`
  2. `[Step]` → verify: `[check]`
  3. `[Step]` → verify: `[check]`

### 5. Explaining and Documentation
- **Authorized Documentation Files Only**:
  - Exclusively maintain and use the three authorized project documentation files:
    1. `README.md`: What the tool is, capabilities, toolchain, and how to use.
    2. `planning.md`: Architecture, system design, tasks, roadmap, and research items.
    3. `journal.md`: Verbatim developer directives, mentoring notes, and key architectural decisions.
  - **NEVER** create additional arbitrary documentation files (such as `walkthrough.md`, `specs.md`, etc.) without explicit user authorization. You may propose new documentation files, but never create them unprompted.
- **Explain Changes**:
  - Explain why and what you have done whenever changes are made to any file in 1-2 simple, concise sentences.

---

## 🌿 7. Git Branching, Release Versioning & Main Branch Gates

- **Mandatory Branching Workflow**:
  - Direct commits to `main` are **strictly forbidden**.
  - All feature implementations, UI changes, and experiments must be developed on `feature/<name>` (or `feat/<name>`) branches.
  - All bug fixes must be developed on `fix/<name>` (or `bugfix/<name>`) branches.
- **Explicit Main Branch Push / Merge Gate**:
  - Pushing to `main` or merging a feature/bug branch into `main` **always requires explicit user authorization**.
  - Agents may push feature/bug branches to origin for CI verification or PR creation, but must never update `main` without confirmation.
- **Release Versioning Policy**:
  - Version numbers in `pyproject.toml` follow Semantic Versioning (`MAJOR.MINOR.PATCH`).
  - **Patch version** increments with each completed development session / commit cycle (e.g., `1.1.0` -> `1.1.1`).
  - **Minor / Major versions** increment only upon explicit user request or milestone completion.
- **Automated CI Requirement**:
  - All commits pushed to GitHub are automatically validated via GitHub Actions CI (`.github/workflows/test.yml`), which builds the environment and executes the full test suite (`uv run python -m tests`).

### 🔄 Multi-Machine & Multi-Session Git Hygiene (Cross-Device Policy)
*The developer frequently moves between 3 computers (e.g., mlpc, laptop, desktop) and 2 Antigravity instances. To prevent silent remote divergence and merge collisions, agents must adhere to strict sync discipline:*
1. **Mandatory Pre-Flight Remote Fetch**:
   - **Always run `git fetch origin`** before writing code, proposing plans, or creating branches.
   - Run `git status -uno` to detect whether local tracking branches are behind `origin/main` or remote feature branches.
   - If `origin/main` has advanced, always rebase or fast-forward before creating new feature branches: `git checkout -b feature/<name> origin/main`.
2. **Never Develop Directly on `main`**:
   - Every modification must be committed on a dedicated `feature/<name>` or `fix/<name>` branch.
3. **Session Hand-Off & Remote Push**:
   - At the conclusion of each development session or work chunk, push the feature branch to `origin` (`git push -u origin <branch-name>`).
   - Never leave unpushed work on local feature branches at session close; another computer or instance needs access to the latest commits.
4. **Clean Remote Branch Resumption**:
   - When resuming work on another machine, fetch all branches (`git fetch origin`) and checkout the remote branch (`git checkout <branch-name>; git pull origin <branch-name>`) to ensure uninterrupted continuity.


