# Feature: Publishing, Packaging & Community Launch

- **Feature ID**: `publishing`
- **Status**: Planning & Roadmap (Phase 6 & 7)
- **Primary Goal**: Distribute Pipeline Tools as an easily installable package and launch across developer communities.

---

## 1. Overview & Launch Channels

Pipeline Tools transforms multimodal local folders into structured, queryable AI datasets. To maximize reach, adoption, and developer utility, the publishing strategy spans packaging, community announcements, and technical deep dives:

1. **PyPI & modern `uvx`**: 1-command installation (`pip install pipeline-tools` or `uvx pipeline-tools`).
2. **Developer Blog Deep-Dive**: In-depth architecture story: *"Building a Local-First Multimodal AI Workbench: Why I Paired Pixeltable with Gradio"*.
3. **Hacker News (Show HN)**: Showcase declarative multimodal ETL, local privacy, zero-memory table streaming, and instant 1-click lineage undo.
4. **Pixeltable Forums & Discord**: Community case study highlighting real-world declarative computed column usage.
5. **Y Combinator / Tech Socials**: Video demo reels showing 1-click folder ingestion, dry-run prompt tuning, and Markdown sidecar generation.

---

## 2. Core Packaging & Distribution Requirements

### 2.1 PyPI Package & CLI Entrypoint (`RES-16`)
- Standard PEP 517/621 packaging in `pyproject.toml` using `hatchling`.
- Expose executable CLI command:
  ```bash
  uvx pipeline-tools
  # or
  pip install pipeline-tools && pipeline-tools
  ```
- Graceful embedded PostgreSQL binary handling across Windows, Linux, and macOS (handling file permissions, socket locations, and PID cleanups).

### 2.2 Documentation & Onboarding Collateral
- Clean, concise `README.md` with 3-minute quickstart guide.
- Curated sample multimodal dataset (`samples/`) with mixed PDFs, images, and text files.
- Visual GIF / MP4 walkthroughs demonstrating key workflows.

### 2.3 Closed Beta Cohort & Friction Logging
- Recruit 5–10 initial test users (researchers, archivists, engineers).
- Structured friction log capturing first-run setup issues and workflow bottlenecks.

### 2.4 Developer Blog Article Outline
- **The Pain**: Chaotic local directories, unindexed PDFs, fragile custom Python scripts, and expensive cloud vector DB lock-in.
- **The Architecture**: Pixeltable declarative schema + Gradio 6.0 decoupled controller architecture.
- **Key Engineering Lessons**:
  - Eliminating memory leaks on 100 MB CSV rows with database-level substring slicing (`table.content.slice(0, 500)`).
  - Replacing imperative Python loops with declarative `@pxt.udf` computed columns for automatic caching and 15x speedups.
  - Mitigating prompt token explosions by strictly enforcing standard Markdown and forbidding inline HTML/SVG.

---

## 3. Implementation Plan & Checklist

- [ ] **Phase 1: PyPI Packaging & Build Configuration**
  - [ ] Configure `pyproject.toml` with project metadata, dependencies, classifiers, and entrypoint `pipeline-tools = "app:main"`.
  - [ ] Test build with `uv build` and verify wheel installation in clean virtual environment.
- [ ] **Phase 2: Launch Documentation & Assets**
  - [ ] Record high-resolution 30-second workflow demo video / animated GIF.
  - [ ] Author developer blog post draft.
  - [ ] Create Show HN announcement draft and test launch checklist.
- [ ] **Phase 3: Beta Testing & Validation**
  - [ ] Distribute to closed beta cohort; gather friction logs.
  - [ ] Resolve cross-platform packaging issues (macOS arm64, Linux, Windows).
- [ ] **Phase 4: Community Launch**
  - [ ] Publish to PyPI.
  - [ ] Publish blog post and trigger Show HN submission.
  - [ ] Post to Pixeltable community forums and social channels.
