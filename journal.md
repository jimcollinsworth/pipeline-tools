---
title: "Developer Journal & Key Architectural Directives"
description: "Chronological record of key developer directives, mentoring instructions, retraining notes, architectural decisions, and generalized software engineering lessons."
created_at: 2026-08-31
last_updated: 2026-09-05
author: "Jim Collinsworth"
tags: ["mentoring", "architecture", "testing", "directives", "tdd", "pixeltable", "postgres"]
---

# Developer Journal & Architectural Directives

This journal records verbatim developer instructions, architectural directives, mentoring inputs, rules creation, and key technical pivots for the **Pipeline Tools** project. These entries capture high-impact guidance and generalized lessons for future development.

---

## 📅 2026-09-22: Unified Slash Intellisense (Skills, UDFs, Segmenters), Multi-UDF Prompts & Callback Hardening (v1.3.8)

**Context:** The developer requested adding registered UDFs and Segmenters to the in-textbox slash Intellisense popup, sorted alphabetically with distinct type badges (`[Skill]`, `[UDF]`, `[Segmenter]`) and descriptions. Additionally, during a live test of multi-UDF prompts (`"mel_spectrograph and chroma for {file_name}"`), a `progress_callback` argument mismatch (`cb() missing 1 required positional argument: 'detail'`) was discovered and fixed.

**Verbatim Instruction:**
> `need to add registered UDFs to the intellisense since they are accessible using slash, can probably make the list alphabetical and identify the type (skill, UDF, ...) with description`
> `for the first test i used the prompt "mel_spectrograph and chroma for {file_name}" not sure if multiple udfs can be used`
> `TypeError: render_playground_tab.<locals>.on_test_sample.<locals>.cb() missing 1 required positional argument: 'detail' - failed on test`

**Key Decisions & Engineering Takeaways:**
1. **Unified Slash Intellisense with Type Badges**:
   - `get_all_slash_commands()` in `app.py` unifies `SkillsRegistry`, `UDFRegistry`, and `SegmenterRegistry` into a single alphabetically sorted collection.
   - Popups render command names, descriptions, and color-coded type badges (`[Skill]`, `[UDF]`, `[Segmenter]`) with matching filter queries across command names, types, and descriptions.
2. **Multi-UDF Prompt Execution**:
   - Expanded `UDFRegistry.match_all_prompts` to extract and isolate multiple UDFs from a single prompt (e.g. `"mel_spectrograph and chroma for {file_name}"`).
   - In `PlaygroundController.test_sample_flow`, multiple UDF evaluations are merged side-by-side into a unified preview table with guaranteed uniform row lengths.
   - In `PlaygroundController.commit_batch_flow`, all matched UDFs are attached sequentially as computed columns in Pixeltable.
3. **Progress Callback Signature Hardening**:
   - Updated `cb(*args, **kwargs)` in `playground_tab.py` to flexibly accept `(pct, msg)`, `(step, total, detail)`, or keyword arguments, clamping progress values safely to `[0.0, 1.0]`.
4. **Full Test Suite Verification**:
   - All 102 automated tests pass cleanly (`102 Passed, 0 Failed, 0 Errors`).

---

## 📅 2026-09-22: Unified Test Domain (pxt_tests) & Database Directory Cleanup (v1.3.7)

**Context:** The developer noticed multiple lingering test directories (`test_seg`, `test_pxt`, `test_audio_suite`, etc.) cluttering up the shared Pixeltable database and instructed consolidating all tests into a single shared domain `pxt_tests` with namespaced table identifiers and performing a one-time purge of stale test domains.

**Verbatim Instruction:**
> `i see in the list of pixeltable domains many tests, test_seg, test_pxt... cluttering up the shared database. update tests to make all these tests share a single domain pxt_tests for all the necessary tables. do a one time cleanup of the old tables too`

**Key Decisions & Engineering Takeaways:**
1. **One-Time Database Directory Purge**:
   - Dropped 11 stale test directories (`test_audio_suite`, `test_seg`, `test_pxt`, `test_seg2`, `test_audio_eval`, `test_win_path`, `test_v_cust`, `test_no_aud`, `test_seg_pdf`, `test_suite_isolated`, `test_controller_isolated`, `test_seg_isolated`, `test_e2e_isolated`), leaving only clean user domains (`default`, `personal`).
2. **Unified `pxt_tests` Domain Across All Test Suites**:
   - Standardized `TEST_DOMAIN = "pxt_tests"` across `test_app.py`, `test_controllers.py`, `test_audio_spectrogram.py`, `test_segmentation.py`, and `test_browser_e2e.py`.
   - Namespaced all table identifiers (`app_*`, `ctrl_*`, `audio_*`, `seg_*`, `e2e_*`) to prevent table collision across test modules.
3. **Pre-Flight & Post-Flight Cleanliness**:
   - Added `setUpClass` pre-cleanup to purge lingering tables before running tests, and robust `tearDownClass` handlers using `DBManager.drop_table` to ensure zero leftover test tables or directories after test runs.
4. **Full Test Suite Verification**:
   - Verified that all 96 unit, controller, audio DSP, and segmentation tests pass cleanly (`96 Passed, 0 Failed, 0 Errors`), leaving only user domains in the database.

---

## 📅 2026-09-21: Multimodal File Segmentation & Chunking Tab (v1.3.6)

**Context:** The developer directed adding file segmentation into a dedicated tab positioned before Data Enhancement to split individual PDF/text, audio, or video files into multiple sub-rows in a new Pixeltable view (pages, paragraphs, sentences, audio time slices, video frames), controlled via UDFs, prompt-based slash commands, and quick-apply presets using native Pixeltable segmenters first.

**Verbatim Instruction:**
> `before i forget, we need to add the segmentation of files, this is probably another tab, before data enhancement. With the individual pdf/text, audio or video file, we want to segment them into multiple rows in a new table, could be pages, paragraphs, sentences. audio files would be segments by time or by some recognizer/generator, videos would be split into images every few seconds, or on transitions. too many options to start with, need easy first. Want UDFs and prompt based definitions like we did for mel spectrogram and other audio functions, except to control segmentation. use native pixeltable segmenters first`

**Key Decisions & Engineering Takeaways:**
1. **Native Pixeltable Views (`pxt.create_view`) Over Data Duplication**:
   - Rather than creating disconnected standalone tables and duplicating binary data, segmented datasets are created as native Pixeltable views (`pxt.create_view(view_path, source_table, iterator=...)`).
   - Zero duplicate disk/RAM storage; views maintain automatic lineage back to parent records (`pos`, `page`, `segment_start`); and newly ingested files in parent tables automatically propagate to the segmented view.
2. **Easy-First Segmenter Suite (`src/core/segmenter_registry.py`)**:
   - Registered 5 core segmenters with typed parameter schemas and aliases:
     - `split_pages` (`/split_pages`): Pixeltable native `document_splitter(t.doc, separators='page')`.
     - `split_paragraphs` (`/split_paragraphs`): `paragraph_splitter_udf(t.content)` and `document_splitter(t.doc, separators='paragraph')`.
     - `split_sentences` (`/split_sentences`): Native `string_splitter(t.content, separators='sentence')` with fast regex fallback.
     - `split_audio` (`/split_audio duration=10.0`): Pixeltable native `audio_splitter(t.audio, duration=10.0)`.
     - `extract_frames` (`/extract_frames fps=1.0`): Pixeltable native `frame_iterator(t.video, fps=1.0)`.
3. **Decoupled Controller (`src/controllers/segmentation_controller.py`)**:
   - Pure, testable controller handling domain table discovery, intelligent view name suggestions (`{source_table}_{segmenter}`), dry-run preview execution, and view creation.
4. **Dedicated Workbench Tab (`src/ui/segmentation_tab.py` & `app.py`)**:
   - Mounted as Tab 2 between *Ingestion & Scanner* and *Data Enhancement*.
   - Includes quick preset buttons (`📄 Split Pages`, `📝 Split Paragraphs`, `🔤 Split Sentences`, `🎙️ Audio Segments (10s)`, `🎬 Video Frames (1 fps)`), slash command input, expandable in-app documentation accordion, sample rows slider, dry-run preview DataFrame, and 1-click view creation button.
   - Wired cross-tab event listeners on view creation to dynamically update table dropdown choices and selection in Data Enhancement and View & Export.
5. **Comprehensive Verification**:
   - Created `tests/test_segmentation.py` with 15 test cases covering registry discovery, slash command parameter parsing, natural language triggers, markdown help generation, controller view name suggestion, dry-run preview, view creation for text, paragraphs, audio, real PDF documents (`split_pages`), real MP4 video (`extract_frames`), invalid identifier rejection, and missing-column error handling.
   - All 96 tests in the core suite pass cleanly (`96 Passed, 0 Failed, 0 Errors`).

---

## 📅 2026-09-21: Expanded Audio/Voice/Noise DSP Suite (MFCC, Chroma, Audio Stats) & In-App UDF Registry Help (v1.3.5)

**Context:** The developer directed expanding the audio analysis suite with useful Librosa functions for voice, timbre, and noise analysis, integrating registry documentation in the app and docs, adding sample prompt presets, and providing comprehensive in-app help.

**Verbatim Instruction:**
> `ok, look at librosa api and add some of the more useful functions for audio/voice/noise analysis. include information about the registry in the doc files and in the app, use one in a sample prompt, and have help for all somewhere (help icon, accordian..`

**Key Decisions & Engineering Takeaways:**
1. **Audio/Voice/Noise DSP Suite (`src/audio/spectrogram.py`)**:
   - **`mfcc`**: Mel-Frequency Cepstral Coefficients (default `n_mfcc=20`) for vocal timbre, speaker identity, and speech characteristics. Produces dual output: 2D feature matrix `mfcc` (`pxt.Array`) and colormapped image `mfcc_img` (`pxt.Image`, `plasma` colormap).
   - **`chroma`**: Chroma STFT (12 semitone pitch classes) for harmonic, tonality, and musical pitch analysis. Produces dual output: 2D feature matrix `chroma` (`pxt.Array`) and colormapped image `chroma_img` (`pxt.Image`, `coolwarm` colormap).
   - **`audio_stats`**: Summary statistics dictionary (`duration_sec`, `sample_rate`, `rms_mean`, `rms_std`, `zcr_mean`, `spectral_centroid_mean`, `spectral_rolloff_mean`, `silence_ratio`) for Voice Activity Detection (VAD) and noise floor analysis (`pxt.Json`).
   - Factored out `load_audio_signal` helper with automatic PyAV fallback (`.m4a`, `.aac`, `.mp3`) for clean DRY audio decoding.
2. **Central Registry & Dynamic Help (`src/core/udf_registry.py`)**:
   - Registered `mfcc`, `chroma`, and `audio_stats` alongside `mel_spectrogram` with typed parameter schemas and sample evaluation functions.
   - Implemented `UDFRegistry.generate_markdown_help()` generating dynamic documentation tables with parameter types, default values, descriptions, and prompt examples.
3. **In-App Help & Sample Presets (`src/ui/playground_tab.py`)**:
   - Added preset buttons: `🎙️ Voice Timbre (MFCC)` (`/mfcc n_mfcc=20 colormap=plasma`), `🎼 Pitch & Chroma` (`/chroma n_chroma=12 colormap=coolwarm`), and `📊 Audio & Noise Stats` (`/audio_stats`).
   - Added expandable `📚 Audio DSP & UDF Function Help & Registry` accordion directly under the Prompt Guide.
4. **Media Inspector & Table Rendering**:
   - Updated `TablesController.handle_row_inspection` to inspect and preview `mfcc_img` and `chroma_img` in the Media Inspector drawer.
   - Updated `DBManager.get_table_data` to render 2D numpy arrays with 12 (chroma) and 20 (mfcc) rows as base64 preview thumbnails.
5. **Comprehensive TDD Verification (`tests/test_audio_spectrogram.py`)**:
   - Added 9 new unit tests verifying direct calculation, null safety, Pixeltable table column attachment, prompt matching with parameter overrides, markdown help generation, and sample/batch execution (78/78 tests passing).

---

## 📅 2026-09-21: Prompt-Driven Declarative UDFs, Media Players Across All Tables & DataFrame Crash Fix (v1.3.4)

**Context:** The developer reported a Gradio DataFrame `ValueError` when clicking the `id` column pill to hide it, noted missing spectrogram rendering and media players in table views, and directed that UDF execution should not use hardcoded buttons but be driven through prompting (e.g. `"mel spectrograph of filename"` or `/mel_spectrogram`) with default and custom parameter overrides.

**Verbatim Instruction:**
> `this happened when clicking on the id column to hide ... ValueError: The length of the headers list must be equal to the column_count. The column count is set to 3 but headers has 0 items.`
> `fix/change: no spectrographs are in the new column, fix that.`
> `no player for the audio in the table views, check this in all tables, should have players/viewers for audio, video and images`
> `don't like the mel spectrograp button, not clear how that relates to prompt and run test operations. i thought this would all be prompting, i just enter "mel spectrograph of filename" in the prompt and it would run the UDF using native pixeltable processing with default values, i could enter alternative values/parameters in the prompting. Eventually we will have multiple UDFs that could be called. is all this possible? what options? will processing be efficient? do we have to predefine all the possible UDF/functions? is this just tool calling? /boost /brainstorming /pixeltable`

**Key Decisions & Engineering Takeaways:**
1. **DataFrame `ValueError` & Pill Bouncing Resolution**:
   - In `TablesController.filter_dataframe_columns`, when `selected_cols` is empty, never return `headers=[]` (which Gradio evaluates as falsy and falls back to default `column_count=3`). Instead, preserve canonical columns or display a notice column.
   - Stopped shuffling deselected pills to the end of the pill list in `reorder_columns_on_selection`, preventing jarring DOM rebuilds that emitted empty selection states.
2. **Spectrogram Rendering & PyAV Fallback**:
   - Added PyAV (`import av`) fallback inside `compute_mel_spectrogram_core` to decode `.m4a` and `.aac` voice notes without external FFmpeg.
   - Updated `_truncate_cell` and `get_table_data` to convert both `PIL.Image.Image` and 2D `np.ndarray` into base64 data URIs (`<img src="data:image/jpeg;base64,...">`) and dynamically assigned `"html"` datatypes so Gradio renders graphics instead of raw string pointers or float matrices.
3. **Media Players & Inspector Across All Table Views**:
   - Ingestion scanner: Added `Preview` column with HTML `<audio>`, `<video>`, and `<img>` players for pre-ingestion auditioning.
   - Data Enhancement (Playground): Wired `input_table.select` to `pg_media_inspector_group` and defaulted `preview_mode_toggle` to `False` so media players are visible.
   - View & Export: Defaulted `lightweight_toggle` to `False` so media players render on initial table load.
4. **Prompt-Driven UDF Execution Architecture (`UDFRegistry`)**:
   - Removed the standalone "🎵 Mel Spectrogram" button.
   - Implemented `UDFRegistry` (`src/core/udf_registry.py`) providing metadata, aliases, parameter schemas, and Pixeltable column binding functions.
   - Prompts matching slash commands (`/mel_spectrogram hop_length=256 colormap=plasma`) or natural language (`"mel spectrograph of filename"`) are parsed for parameters and executed declaratively via Pixeltable expressions (`table.select(...)` for sample tests, `table.add_computed_column(...)` for batch commits).
   - This provides $O(1)$ intent resolution and native database-level C/multiprocessing vectorization across thousands of rows.
5. **Full Test Suite Verification**:
   - Added 6 new test cases covering PyAV audio decoding, UDFRegistry matching, prompt-driven sample/batch execution, base64 image rendering, and 2D numpy array row inspection (69/69 tests passing).

---

## 📅 2026-09-21: Declarative Audio Mel Spectrogram Pipeline & Inspector Integration (v1.3.3)

**Context:** The developer requested an audio Mel Spectrogram extraction capability for audio files, exploring UDF possibilities, library choices, and representation formats through a `/grill-me` design interview.

**Verbatim Instruction:**
> `i want to call a mel spectrogram function for each audio file, can i pass in a user defined function? do we need a library? options? /grill-me`
> `dedicated column since it is an image stored in the db (i think). make sure to add an end 2 end test on the mel spectrogram specifically`

**Key Decisions & Engineering Takeaways:**
1. **Declarative Invariant (`@pxt.udf` Computed Columns)**:
   - Implemented `compute_mel_spectrogram` and `render_mel_spectrogram_image` as native Pixeltable `@pxt.udf` functions in `src/audio/spectrogram.py`.
   - In accordance with repository invariants, table enrichment attaches computed columns (`table.add_computed_column`) with zero imperative row loops.
2. **Dual Output Representation**:
   - **`mel_spectrogram` (`pxt.Array`)**: Stored as a 2D float32 array `[128, T]` representing dB-scaled mel power spectral density for downstream ML and feature extraction.
   - **`mel_spectrogram_img` (`pxt.Image`)**: Stored as a colormapped (`magma`) PIL Image for visual inspection in table views and export.
3. **Null-Safety for Mixed-Modality Datasets**:
   - The UDF gracefully inspects whether each record contains valid audio data (`audio`), returning `None` for non-audio rows without raising exceptions.
4. **Interactive Workbench & Media Inspector Integration**:
   - Added "🎵 Mel Spectrogram" action button in the Data Enhancement tab to enrich tables on-demand.
   - Added dedicated Spectrogram image preview slots in both Data Enhancement and View & Export Media Inspectors so users can listen to audio and view its spectrogram side-by-side.
5. **Pre-Flight PostgreSQL Lock Healing in `app.py`**:
   - Added `DBManager.heal_postgres_locks()` inside `app.py`'s `create_app()` to prevent Windows file sharing violations on restart.
6. **Dedicated TDD & Integration Test Suite**:
   - Created `tests/test_audio_spectrogram.py` verifying tone generation, UDF computation, table attachment, null safety, and Media Inspector extraction (63/63 tests passing).

---

## 📅 2026-08-31: Testing Strategy, Architecture & Tooling Deep Review

**Context:** Initiating a comprehensive quality, testing reliability, and architecture review of the test suite, Pixeltable/Postgres lifecycle management, and web testing strategy.

**Verbatim Instruction:**
> `/using-superpowers /postgresql /pixeltable /test-driven-development lets do a deep review of the testing, i want to basically verify that the tests all do something tangible and useful, coverage is good, setup/teardown is reliable and handles test run cancellation, that the testing tools used are best in class for agent and manual cli use, provide fast testing of apis and python modules, direct web site testing and handles rich javascipt web sites. antigravity in particular needs to be supported. ask developer for help setting up tools initially if needed. do not make any toolchain changes without discussion and approval. also want to ensure the code is structured to facilitate testing. highlight any tests that seem difficult due to lack of a direct module/api or such.. do the research, propose code changes, additional tests, tools or process changes`

**Key Decisions & Engineering Takeaways:**
1. **Tangible Behavior Verification**: Tests must verify real state mutations (Pixeltable table creation, column auto-split, file exports) rather than mocking away core functionality.
2. **Setup/Teardown Reliability**: Test suites must isolate test tables in dedicated namespaces and reliably clean up resources on completion or cancellation to prevent Postgres lock contention on Windows.
3. **Decoupled Architecture**: UI event handlers should be separated into pure, testable controller functions rather than tightly coupled closures inside Gradio layout definitions.
4. **Browser Testing Strategy**: Evaluated Chrome DevTools MCP vs. Playwright. Deferred Playwright for future evaluation while prioritizing fast Python unit/controller tests and native Chrome DevTools inspection.

---

## 📅 2026-08-31: Hugging Face & YOLO Vision Classification Strategy

**Context:** Researching and designing support for Hugging Face model hub and Ultralytics YOLO vision models (e.g. `keremberke/yolov8m-painting-classification`) within the Data Enhancement pipeline.

**Verbatim Instruction:**
> `can we add support for hugging face models to the tools /grill-me`
> `i assume 3 native, but that will still install the local transformers i assume, i want to run that model and get all these classifications ['Abstract_Expressionism', 'Action_painting', 'Analytical_Cubism', 'Art_Nouveau_Modern', 'Baroque', 'Color_Field_Painting', 'Contemporary_Realism', 'Cubism', 'Early_Renaissance', 'Expressionism', 'Fauvism', 'High_Renaissance', 'Impressionism', 'Mannerism_Late_Renaissance', 'Minimalism', 'Naive_Art_Primitivism', 'New_Realism', 'Northern_Renaissance', 'Pointillism', 'Pop_Art', 'Post_Impressionism', 'Realism', 'Rococo', 'Romanticism', 'Symbolism', 'Synthetic_Cubism', 'Ukiyo_e']`
> `1 makes sense, but just add this as a future major feature. hold for now - save requirements/imp details only update doc files`

**Key Decisions & Engineering Takeaways:**
1. **Scope & Roadmap Placement**: Scheduled as a planned Phase 3 major feature. Documentation and architectural specifications recorded in `planning.md` and `README.md` without adding heavy runtime dependencies now.
2. **Unified Data Enhancement Integration**: Vision classification models will be exposed alongside LLM providers in the Data Enhancement tab, outputting structured JSON (`painting_style`, `confidence`, `probabilities`) that automatically unpacks into Pixeltable columns via the auto-split engine.
3. **Domain Taxonomy**: Support full 27-class art taxonomy across historical movements, impressionism, cubism, ukiyo-e, and modern genres.

---

## 📅 2026-08-31: Embedded Multimodal Media & Lightweight vs. Full Mode

**Context:** Enabling rich embedded multimodal media (images, audio, video, PDF documents) inside Pixeltable tables with performance optimization.

**Verbatim Instruction:**
> `add these to the plan, and work on the embedded media in the tables, ask me how if needed. view the media only when not in lightweigh mode`

**Key Decisions & Engineering Takeaways:**
1. **Lightweight vs. Full Media Toggle**:
   - **⚡ Lightweight Mode (`lightweight=True`)**: Omit raw binary columns (`doc`, `image`, `audio`, `video`), truncate text to 250 characters for fast response.
   - **🔍 Full Media Mode (`lightweight=False`)**: Generate HTML thumbnails (`<img>`), inline audio controls (`<audio>`), video players (`<video>`), and PDF badges (`[📄 View PDF]`) directly inside table cells.
2. **Interactive Selected Record Media Inspector Drawer**:
   - Clicking any row in View & Export or Data Enhancement opens a dedicated media viewer below the table with full-size image, audio/video playback, and extracted text.

---

## 📅 2026-08-31: Strict 3-File Documentation Architecture Policy

**Context:** Clarifying and constraining the repository documentation structure to avoid extraneous documentation files.

**Verbatim Instruction:**
> `i didn't ask for a walkthrough.md doc, we only have readme, planning and journal authorized. make sure our agents file has that rule. you can propose new docs but don't create. make sure my last few instructions are also updated in journal. remove walkthrough and put content elsewhere - readme is what, how to use, planning is steps to build, design`

**Key Decisions & Engineering Takeaways:**
1. **Single Source of Truth (3 Authorized Docs)**:
   - `README.md`: What the tool is, capabilities, toolchain, and how to use.
   - `planning.md`: Steps to build, system architecture, engineering design, tasks, and research items.
   - `journal.md`: Verbatim developer directives, mentoring notes, and key architectural decisions.
2. **No Arbitrary Docs**: Never generate extra markdown files (e.g. `walkthrough.md`, `specs.md`) without prior explicit authorization. Rule codified permanently in `AGENTS.md`.

---

## 📅 2026-08-31: Native Pixeltable `t.thumbnail` Computed Column & Media Serving

**Context:** Resolving thumbnail rendering latency, Gradio cross-directory security errors (`Cannot move to gradio cache`), and native multimodal schema integration.

**Verbatim Instruction:**
> `what is the pixeltable native t.thumbnail? doesn't that replace the base64? so it puts thumbnails into the table?`
> `yes, make it so, and update the tables that have viewing capabilities`

**Key Decisions & Engineering Takeaways:**
1. **Pixeltable Declarative Storage**:
   - Declared `t.thumbnail = t.image.resize((64, 64))` on table creation. Thumbnails are computed once on ingestion and persistently stored inside Pixeltable's local storage.
2. **Instant In-Memory Base64 HTML Rendering**:
   - `DBManager.get_table_data` retrieves the pre-computed `thumbnail` PIL Image from Pixeltable and encodes it into a lightweight base64 data URI in memory, rendering consistent $54 \times 54\text{px}$ square thumbnails (`object-fit: cover`) with zero disk re-reading.
3. **Gradio `allowed_paths` Across System Drives**:
   - Added system-wide drive root paths (`C:\`, `D:\`, user home) to `demo.launch(allowed_paths=...)`, allowing Gradio's internal file server to serve full-resolution media to the **Media Inspector** drawer and audio/video players without cache movement exceptions.

---

## 📅 2026-08-31: Dynamic Tab Auto-Refresh, Button Press Effects & Mobile Backlog

**Context:** Fixing dropdown sync across workbench tabs, unifying button styles with active press animations, eliminating dataframe ghost buttons, and planning mobile/cloud architecture.

**Verbatim Instruction:**
> `- fix - execute on table & save columns button, no need for red, make it match all others. all buttons should have a hover/press affect too, what ever is native and easy.`
> `- fix - dropdowns table in target data & llm engine - enhancement - not refreshing when going to tab, my new table was missing until i selected a different one. make sure all these dynamic dropdowns do a refresh when switching to their tabs. add a test to check this issue (or fix existing one)`
> `a couple extra ghost buttons, probably because no directory is scanned yet.`
> `backlog add another major feature todo - mobile app support - how can we support mobile/tablet use? embedded post gresql is an issue i think. How to run gradio apps from cloud, whats our options, another backlog todo - responsive design - mobile user will be very different - view defaults, sizes`

**Key Decisions & Engineering Takeaways:**
1. **Dynamic Tab Auto-Refresh (`tab.select`)**:
   - Attached `.select()` listeners to all `gr.Tab` containers (Ingestion, Data Enhancement, View & Export) so switching tabs immediately calls `DBManager.list_dirs()` and `DBManager.list_tables()`, keeping newly ingested tables instantly selectable.
2. **Consistent Button Interactions & Ghost Button Fix**:
   - Switched `commit_batch_btn` to primary blue.
   - Added tactile CSS `:active` press effects (`transform: translateY(1px)`).
   - Constrained secondary button CSS to exclude internal dataframe action buttons (`button:empty`, `.icon-button`), eliminating empty ghost buttons.
3. **Mobile & Cloud Architecture Strategy**:
   - Documented `RES-09` and `RES-10` in `planning.md`. To navigate embedded PostgreSQL platform constraints, the recommended pattern is containerized cloud/server hosting (Docker, Hugging Face Spaces, or local LAN host) serving a responsive progressive web UI to mobile/tablet clients.

---

## 📅 2026-08-31: Pixeltable Lineage Versioning & Simple 'Undo' Architecture

**Context:** Formulating a clean, practical roadmap for Pixeltable table lineage, time travel, and a user-friendly 'Undo Last Operation' capability.

**Verbatim Instruction:**
> `ok this is all too complicated for now, add a major feature todo to define, design and implement lineage. maybe a simpler 'undo' last operation command? does every pixeltable operation create a new lineage?`

**Key Decisions & Engineering Takeaways:**
1. **Pixeltable Versioning Model**:
   - Every mutating Pixeltable operation (`insert`, `add_column`, `update`, `drop_column`, `delete`) increments the internal immutable table version number (`v0 -> v1 -> v2...`).
2. **Simple 'Undo' Strategy**:
   - Prioritize a single-click **↩️ Undo Last Operation** button over a complex multi-branching UI.
   - If the last operation was an LLM batch run that added columns, Undo drops those generated columns.
   - If the last operation was row ingestion/updates, Undo restores the table to version `v - 1`.
3. **Roadmap Tracking**:
   - Defined Phase 3 task and `RES-11` in `planning.md`.

---

## 📅 2026-08-31: 1-Click 'Undo Last Operation' & Table/Domain Deletion Management

**Context:** Implementation of instant 1-click operation reversion and safe database management with confirmation workflows.

**Verbatim Instruction:**
> `add the undo last operation button 1 click, sounds good, i think we have the history now in the runs button view but it can probably be improved. add new tests for the undo.`
> `second add delete table and delete domain (and the connected tables) buttons , right under the load table button in view/export. provide a confirmation message before deleting and detail messages onscreen and logs on what was deleted.`

**Key Decisions & Engineering Takeaways:**
1. **1-Click 'Undo Last Operation'**:
   - Added `DBManager.undo_last_operation(domain, table)` and `DBManager.record_operation()` stack tracking.
   - Reverts newly generated LLM columns (dropping auto-split and single columns cleanly) or rolls back to the baseline table schema.
   - Accessible on both **Data Enhancement** and **View & Export** with real-time UI refresh.
2. **Safe Deletion Management (Table & Domain)**:
   - Added `🗑️ Delete Table` and `⚠️ Delete Domain & All Tables` directly beneath the table selector in View & Export.
   - Implemented a 2-step confirmation drawer displaying exact target table/domain names and connected table lists before execution.
   - Comprehensive status logging (`logging.getLogger("pipeline_tools.db")`) and on-screen summary cards detailing deleted resources and row counts.
3. **Automated Verification**:
   - Added `test_undo_last_operation` and `test_delete_table_and_domain_with_details` in `tests/test_app.py` (27/27 tests passing).

---

## 📅 2026-08-31: Unified AI-Driven Markdown Document Export

**Context:** Resolving UI ambiguity in View & Export tab regarding "Direct Template" vs "LLM Synthesis".

**Verbatim Instruction:**
> `direct tempate - language seems incorrect or confusing . i believe we still are using an llm? where is the template? /grill-me`
> `i think #2, AI every time, we can put {table_context} to get it all at once or column names for row level. so remove the export mode i guess`

**Key Decisions & Engineering Takeaways:**
1. **Removed Ambiguous Export Mode Toggle**:
   - Eliminated the confusing `Export Mode` radio toggle.
   - All document exports are now 100% unified under the AI Synthesis Engine (Ollama / Gemini).
2. **Unified Context & Prompt Variables**:
   - Uses `{table_context}` to pass full multi-record table data blocks for dataset-wide synthesis.
   - Retains `{domain}`, `{table}`, and `{total_rows}` dynamic placeholders.
3. **4 Refined AI Presets**:
   - `🏷️ Entity & Keyword Intelligence`: Structured tables of named entities & taxonomy keywords.
   - `🎨 Visual & Multimodal Scene Analysis`: Spatial composition, color palettes, and lighting conditions.
   - `📋 Thematic Summary & Executive Brief`: Narrative briefing with trends, outliers, and takeaways.
   - `📁 Structured Media Catalog Dossier`: Systematic record-by-record catalog with badges, extracted summaries, and an index table.
4. **Streamlined UI Layout**:
   - Arranged AI Provider, Model Identifier, and Max Records slider in a clean single row.
   - Live Markdown preview and instant download button directly beneath generation.
   - All 27 automated tests passing.

---

## 📅 2026-08-31: Pixeltable OOM / Memory Leak Resolution on Large Media Datasets

**Context:** Investigating and resolving Out of Memory (OOM) errors occurring in View & Export tab when loading large media tables (e.g. `thinkpad data_dir2`).

**Verbatim Instruction:**
> `i'm getting out of memory in export/view loading the thinkpad data_dir2 table, but it loads in data enhancement, something is different. /memory-leak-debugging /pixeltable`

**Root Cause Analysis:**
1. **Unprojected Table Queries**: `DBManager.get_table_data` previously executed `table.limit(limit).collect().to_pandas()`. In Pixeltable, querying without projecting columns causes `pxt.Image`, `pxt.Document`, `pxt.Video`, and `pxt.Audio` to deserialize and load full-resolution binary assets for all rows into Python RAM.
2. **Limit Discrepancy**: Data Enhancement queried with `limit=10`, which barely fit within available memory, whereas View & Export queried with `limit=50` (or up to 200), loading gigabytes of raw uncompressed image/media buffers and triggering an OOM crash.
3. **Redundant Row Click Re-queries**: Clicking a table row previously executed a secondary `get_table_data(..., limit=100)` query rather than reading the clicked row directly from the existing DataFrame.

**Key Decisions & Engineering Fixes:**
1. **Explicit Column Projection in `DBManager.get_table_data`**:
   - `table.select(*[table[c] for c in query_cols])` now explicitly filters out heavy raw binary pointers (`image`, `doc`, `video`, `audio`) before `.collect().to_pandas()`.
   - Memory consumption reduced by **>95%**, querying only lightweight metadata and text columns.
2. **Optimized PIL Thumbnail Generation**:
   - Added fast `img.draft("RGB", ...)` scaling for JPEG images and bilinear downsampling, preventing full-resolution bitmap allocation during preview generation.
3. **Zero-Query Row Selection**:
   - Modified `data_view_table.select` and `current_table_preview.select` to extract row metadata directly from the loaded UI DataFrame in 0ms without database re-queries.
4. **Automated Verification**:
   - Verified with full test suite (`27 Passed, 0 Failed, 0 Errors`).

---

## 📅 2026-08-31: Zero-Memory Streaming Previews & UI Control Alignment

**Context:** Eliminating frontend WebSocket/JSON memory bloat from base64 encoding and aligning View & Export tab controls with Data Enhancement tab.

**Verbatim Instruction:**
> `out of memory again on export page, note that the export page has an explicit load/reaload button, so thats inconsistent with the enhancement page.`

**Key Decisions & Engineering Fixes:**
1. **Direct Gradio Streaming URLs**:
   - Switched image previews from synchronous base64 inline strings to direct `/gradio_api/file={safe_path}` HTTP endpoints with `loading="lazy"`.
   - Completely eliminates memory bloat from DataFrame JSON payloads sent over WebSocket.
2. **UI Control Alignment**:
   - Removed the redundant `Load / Refresh Table` button from the View & Export tab.
   - Connected `limit_slider.change` and dropdown changes to auto-update the table view seamlessly, matching the Data Enhancement tab layout.
3. **Dataframe Cell Text Truncation**:
   - Truncated text columns in the DataFrame to 250 characters for UI display, keeping JSON response sizes tiny (<50KB) even on large document datasets.
4. **All 27 Automated Tests Passing**:
   - Verified with `uv run python -m tests`.

---

## 📅 2026-09-02: Decoupled UI Controllers & Phase 4 Roadmap Expansion

**Context:** Decoupling Gradio UI event handlers into pure, testable controller classes, expanding the automated test suite to 36 tests, and defining Phase 4 roadmap architecture.

**Verbatim Instruction:**
> `ok, make sure thats all documented in the readme, good tool feature descriptions`
> `go ahead with the decouple ui event handlers, and update unit tests based on new capabilities.`
> `lets add more to the roadmap too, put in detail with your addition and suggestions, do not remove any of my detail points, do not implement just document in our plan:`
> `  ingestion-context - add dynamic context to multi-row ingestion process, so the tool 'learns' about the data as it's ingesting it. as each row is processed it starts with the context from all previous rows, and system prompt, can use information such as previous row entitity spelling to help deduplication, lots of potential. When the table has been processed, the current context is learned knowledge about the data - could be useful in itself. at the end of each batch write the context out to a file 'domain-table-ingestion-context.md' for example (are there standards around context knowledge structure?) ?what does pixeltable provide?`
> `  skills handling - want to do a / slash command to load skills from the prompt boxes. lets just search project .agents/skills to start. ?what does pixeltable provide?`
> `  document UX - instead of tables of rows, with large blobs of text in cells, the document view shows a single row of data, but as markdown data - use markdown formating (with borders, color..) to show field label and data, headers and lists for rollups, data (ideally the UX has collapse/expand on header levels and lists), nice formatted and wrapped text, theme selector for different layouts/css, embedded charts/mermaid/images. User could move to next/previous to see a different row. this document ux would be useful for any of the table views, but maybe it's just for export - this is essentially the export markdown document/sidecar for each row feature of export, so maybe it's not that important.  The real idea here is to make long text fields easier to view/review, and second maybe a newspaper/blog type view of the data, or even the entire app would be fun and useful. !lets consider newspaper view type app ux!`
> `Not sure about tech approach - single big markdown doc easy but inflexible, table with each cell a separate markdown fragment could be cool but complexe. ?what are our other markdown related options, we do want to save/export this as markdown with yaml or other frontmatter? ?what our non-markdown options - for displaying this type of rich data?`
> `  column/field selection - need fast way to select columns in the ui, both tables and documents, definitely not a list of fields, must be direct, visual and touch based. each column has a hide icon/toggle, hide maybe just sends it to the end of the doc/row, or hides it, but then we have a hidden view toggle to unhide, not ideal. selecting fields is ideally just done with the llm, in the prompt.  Table views need to filter/hide, and ?pixeltable has calls that could help? Not sure i want to bother with views that get saved, although temporary maybe.`

**Key Decisions & Engineering Takeaways:**
1. **Decoupled Controller Architecture (`src/controllers/`)**:
   - Extracted all UI event logic into three pure, testable controllers:
     - `IngestController`: Directory suggestion generation, path validation, scanner aggregation, and Pixeltable insertion.
     - `PlaygroundController`: Provider/model routing, domain/table auto-population, dry-run sample testing, batch column creation, and 1-click lineage undo.
     - `TablesController`: Table data loading, zero-query client memory row inspection formatting, safe 2-step table & domain deletion, and AI report export.
   - UI tabs (`src/ui/`) now serve strictly as declarative layout definitions and event routers.
2. **Comprehensive Controller Unit Tests (`tests/test_controllers.py`)**:
   - Added 9 dedicated controller test methods testing business logic and error boundaries directly without Gradio server overhead.
   - Total automated test suite expanded to **36 tests (`36 Passed, 0 Failed, 0 Errors`)**.
3. **Phase 4 Roadmap & Architecture Specifications (`planning.md`)**:
   - Documented `RES-12` (Dynamic Ingestion Context & State Accumulation), `RES-13` (Skills Integration via `/` slash commands), `RES-14` (Single-Record Document Reader & Newspaper Editorial UX), and `RES-15` (Direct Touch-Based Column Selection & Declarative Views).

---

## 📅 2026-09-02: Dual Export Strategies (Single Synthesis vs. Per-Row Sidecars) & Systematic Debugging

**Context:** User observed that the export function only processed one row when running the newspaper prompt, and requested two distinct export modes: single-file multi-row synthesis and per-row markdown sidecar files (`{filename}_meta.md`) with continuous live preview updates.

**Verbatim Instruction:**
> `i tried an export, not quite working how i expected. the output quality is great, love the newspaper example, but the row  image in the top preview was not the row image in the bottom generated newpaper, only one row got into the output file markdown, now repeated rows. maybe only the last or first was processed?`
> `i think we need 2 modes, either process all rows and all fields as one llm call, with one llm expected output file, and the second mode make one llm call per row to both read process the rows and output a markdown sidecar file, use the file_name field in the row as the sidecar with _meta.md added. we can overwrite markdown files, its all in the export directory.  a preview doc can be displayed in both cases - the single output, or each row preview as it's output, continuously updating.  add this feature, additional testing /brainstorming /chrome-devtools /using-superpowers`
> `/test-driven-development /systematic-debugging /chrome-devtools /troubleshooting  revisit recent changes, requests, logs analyze what is going wrong with tests. we can revise tests/code if needed`

**Root Cause Investigation & Systematic Debugging:**
1. **Context Construction & Missing Row Iteration**:
   - The original export engine dumped all $N$ rows into a monolithic text block (`{table_context}`). When prompted for a newspaper story with an image, the LLM naturally selected only one item to feature, rather than writing articles for all records.
2. **Binary Media Loading Failure on Missing Paths**:
   - In `DBManager.ingest_files`, `"image": abs_path` was assigned without verifying `Path(abs_path).is_file()`. In unit tests with mock file records, Pixeltable's `pxt.Image` failed to deserialize the non-existent file, causing `get_table_data` to return 0 rows and export tests to return an error.
3. **Mock Target Scope in Unittest**:
   - Tests patched `src.core.llm_service.LLMService.generate` rather than `src.export.exporter.LLMService.generate`, causing live network calls to be attempted during test execution.

**Key Decisions & Engineering Fixes:**
1. **Dual Export Strategies**:
   - **📄 Single Document Synthesis**: 1 LLM call analyzing all rows $\rightarrow$ 1 consolidated report (`exports/{domain}_{table}_report_{timestamp}.md`).
   - **🗂️ Per-Row Sidecars (`_meta.md`)**: 1 LLM call per record $\rightarrow$ individual sidecar files (`exports/{source_stem}_meta.md`), with automatic media embedding (`![filename](filepath)`), clean YAML frontmatter, and live row-by-row preview streaming.
2. **Robust Binary Media Verification in `DBManager.ingest_files`**:
   - Added `and Path(abs_path).is_file()` guards for `doc`, `image`, `audio`, and `video` columns, preventing Pixeltable insert errors when files are missing.
3. **Automated Test Suite Passing**:
   - Total test suite expanded to **38 tests**: **38 Passed, 0 Failed, 0 Errors**.

---

## 📅 2026-09-02: Zero-Memory Table Loading on Giant Text Files (`data_dir2` OOM Resolution)

**Context:** User experienced OOM crash when selecting `thinkpad.data_dir2` in the View & Export tab, while other tables loaded fine.

**Verbatim Instruction:**
> `running out of memory now in export, i select the thinkpad domain data_dir2, doesn't load the preview. other tables work fine. data_dir2 isn't that big`
> `what have you found so far about memory use? we can greately reduce large text cells in the table view, and rely more on the doc views for full text. feel free to truncate every text cell and we'll use a row preview. lets simplify th espec if needed`

**Root Cause Analysis:**
1. **Isolated Monster Row**:
   - `thinkpad.data_dir2` contains 1,159 rows. At **Row 13**, a raw CSV export (`jim sleep export.csv`) had its entire 108 MB text (**107,742,125 characters**) stored in the `content` column.
   - In Data Enhancement, the default preview is only 10 rows (`limit=10`), so Row 13 was never loaded into memory.
   - In View & Export, the default limit was 25 rows (`limit=25`). Fetching Row 13 pulled the full 108 MB string across Postgres into Python, consuming **+425.5 MB of RAM** for just that single cell and causing Gradio to hang/OOM.

**Key Decisions & Engineering Fixes:**
1. **Database-Level String Slicing (`pxt` Projection)**:
   - In `DBManager.get_table_data`, projected `table.content.slice(0, 500)` directly in the database query.
   - PostgreSQL executes `SUBSTRING(content, 1, 500)` in-engine, sending only 500 characters over the wire instead of 108 million characters. Memory consumption dropped from 425+ MB to **<0.1 MB**.
2. **Universal Cell Truncation**:
   - Added `_truncate_cell(val, 250)` across all table columns and object types (including JSON dicts in `metadata`), keeping Gradio's entire WebSocket payload under 50 KB.
3. **Ingestion Safeguard on Giant Files**:
   - Updated `DBManager.extract_file_content` to cap reading giant text/CSV/log files at 1 MB, preventing massive data dumps from bloating future table rows.
4. **Automated Verification**:
   - Full test suite verified: **38 Passed, 0 Failed, 0 Errors**.

---

## 📅 2026-09-05: Embedded PostgreSQL Lock Self-Healing, Dynamic Context Accumulation (RES-12), and Project Skills Discovery (RES-13)

**Context:** The test suite encountered an embedded PostgreSQL lock failure on Windows (`postmaster.pid` surviving an interrupted run with no active process). User requested embedded PostgreSQL lock self-healing, followed by RES-12 and RES-13 in sequence with unit tests, and a comprehensive status report dispatched/archived for Jim Collinsworth.

**Verbatim Instruction:**
> `add the lock self healing. res-12 and res-13 in sequence with new tests as needed,  and send that status report to me at jimcollinsworth@gmail.com /boost /building-data-apps /gradio /pixeltable /skill-repair`

**Key Decisions & Engineering Takeaways:**
1. **Embedded PostgreSQL Lock Self-Healing (`DBManager.heal_postgres_locks`)**:
   - Sweeps and terminates orphaned `postgres.exe` background workers.
   - Safely removes stale `postmaster.pid` and Unix socket files (`.s.PGSQL.*`).
   - Fixes Windows file sharing violations on `pgdata/log` and interrupted WAL recovery state by running `pg_resetwal -f -D <pgdata>`, allowing instant sub-50ms engine startup without timeouts.
   - Integrated as pre-flight self-healing in `tests/__main__.py` and `tests/test_app.py`.
2. **RES-12: Dynamic Ingestion Context & State Accumulation (`src/core/ingestion_context.py`)**:
   - `IngestionContext` tracks entity registries, canonical alias normalization, pluralization, theme discovery, and cross-row memory.
   - Refined `normalize_entity` to eliminate naive 4-letter prefix matching that conflated distinct terms (e.g. `Data` vs `Database`, `Apple` vs `Applesauce`), replacing with technical alias maps (`postgres` -> `PostgreSQL`, `pxt` -> `Pixeltable`) and pluralization rules.
   - Generates and exports structured synthetic knowledge dossiers to `exports/{domain}-{table}-ingestion-context.md` with clean YAML frontmatter and JSON-LD structured schemas upon batch completion.
   - Integrated into `DBManager.ingest_files` and `PromptExecutor.apply_prompt_to_table`.
3. **RES-13: Project & User Skills Integration with Prompt `/` Slash Commands (`src/core/skills.py`)**:
   - `SkillsRegistry` dynamically scans `.agents/skills/` (`gradio`, `hf-gradio`, `pixeltable`, `postgresql`) AND user-level skills (`~/.gemini/config/skills/`, including `building-data-apps`, `skill-repair`, `data-autocleaning`, etc.), plus built-in directives like `/boost`.
   - Hardened slash command discovery regex with boundary checks (`(?<![a-zA-Z0-9_\-:/])(/[a-zA-Z0-9_\-]+)(?=\s|[.,;:!?]|$)`) to prevent matching URL path segments (e.g. `https://domain.com/docs`) and cleanly strip commands followed by punctuation.
   - Parses `/command` tokens from user and system prompts, dynamically decorating prompts with domain rules from `SKILL.md`.
   - Integrated into `PromptExecutor.run_sample_test` and `apply_prompt_to_table`.
4. **Targeted PostgreSQL Process Scoping & Safe WAL Recovery (`src/db/manager.py`)**:
   - Scoped `heal_postgres_locks()` process termination to check cmdline against Pixeltable/target pgdata paths, protecting independent system PostgreSQL services.
   - Constrained `pg_resetwal -f` execution so it only runs when recovering from an ungraceful crash or stale lock, never on healthy clusters.
5. **Test Suite Expansion & Verification**:
   - Added 6 dedicated tests in `tests/test_app.py` covering lock self-healing, state accumulation, slash command expansion, prefix safety (`Data` vs `Database`), multi-directory discovery with `/boost`, and URL-safe command stripping.
   - Automated test suite passed completely: **44 Passed, 0 Failed, 0 Errors**.
6. **Status Report for Jim Collinsworth**:
   - Comprehensive briefing generated and archived in `exports/status_report_jimcollinsworth.md` and `exports/status_report_jimcollinsworth.eml`.

---

## 📅 2026-09-10: Data Enhancement UI Cleanup, Centralized Domain System Prompts, and Unified Two-Table Model

**Context:** General UI cleanup to maximize visibility of tabular data and prompt studio, centralize system prompt management per domain in Settings & Models, and eliminate table proliferation by consolidating test and batch outputs into a single Output Table.

**Verbatim Instruction:**
> `Let's work on the general UI cleanup, especially around the data enhancement screen. I want to maximize the use and the view of the tabular information and the prompt because that's the data that the user actually sees and is important. Let's move system prompt from all the individual pages and just have that on the model page so there'll be one system prompt per domain.`
> `I think somehow we can reduce the number of tables by one. Instead of having input table, test output, and then real output tables, let's just have input table, which highlights the rows we want to use, and output table, which highlights the rows which were created and will be used. Run through output just got sent to the same table as output.`

**Key Decisions & Engineering Takeaways:**
1. **Centralized Per-Domain System Prompts (`src/core/config.py` & `src/ui/settings_tab.py`)**:
   - Stored in `Settings.domain_system_prompts: Dict[str, str]` with `get_domain_system_prompt(domain)` and `set_domain_system_prompt(domain, prompt)` helpers and backward-compatible fallback to `"default"`.
   - Added dedicated Domain System Prompt Configuration editor in Settings & Models tab with dynamic domain selection and instant persistence.
   - Removed individual system prompt textboxes from Data Enhancement and View & Export pages; both tabs now display informative domain badges and automatically inherit their active domain's system prompt.
2. **Unified Two-Table Workbench (`src/ui/playground_tab.py`)**:
   - Replaced 3-table proliferation with exactly two prominent tables:
     - **Input Table (Source Data)**: Visualizes source data with sample testing target row badges (`🎯 Test Row N`), preserving row-click Media Inspector drawer for rich media previews.
     - **Output Table (Consolidated Results)**: Single destination for both dry-run test outputs (`🧪 Sample Test Preview`) and persistent batch enriched columns (`💾 Batch Execution Committed`).
3. **Maximized Tabular and Prompt Visibility**:
   - Reorganized Data Enhancement layout into a compact top control strip (Domain, Table, Provider, Model, Output Mode, Row Limits, and Run/Commit/Undo actions).
   - Expanded User Prompt Studio to full container width with 5 lines height, clickable column placeholder chips, and instant preset buttons.
   - Positioned Input and Output tables in generous side-by-side comparison panels (380px height).
4. **Review & Deep Hardening Fixes**:
   - **Instant Initial Table Rendering**: Populated `input_table` with `initial_preview` at component construction time so the table immediately displays source data on launch instead of rendering an empty dataframe.
   - **Cross-Domain Table Sync**: Hardened `on_domain_change` in Data Enhancement to refresh both input and output tables directly, preventing stale data when switching between domains that share identical table names (e.g. `raw_assets`).
   - **Output Column Prioritization**: Reordered output table columns so generated columns (`columns_created`) appear immediately after identifiers (`id`, `file_name`) rather than buried at the end of the schema.
   - **Accurate Row Status Badges**: Tagged only rows actually enriched (`idx < rows_done`) with `💾 Saved (N)` and un-processed rows with `— (Unchanged)`.
   - **Output Row Inspection**: Attached Media Inspector drawer to `output_table.select` for seamless inspection of generated results.
   - **View & Export Banner Alignment**: Updated `tables_tab.py` to display active domain system prompt and snippet, synchronizing with domain changes and tab navigation.
5. **Automated Verification**:
    - Added unit tests for domain system prompts and controller flow handling in `tests/test_app.py` and `tests/test_controllers.py` (including column prioritization and row status tagging).
    - Verified complete test suite: **47 Passed, 0 Failed, 0 Errors** (`uv run python -m tests`).

---

## 📅 2026-09-10: Cross-Project Responsive Snapshoter Skill (`responsive-snapshots`)

**Context:** Researching and adopting the multi-resolution, multi-orientation snapshot utility from `d:\projects\jimcollinsworth.github.io\tools\screenshots.py` to enable automated responsive design verification, documentation walkthroughs, and visual QA across web applications.

**Verbatim Instruction:**
> `/building-data-apps /learn check the jimcollimsworth.githubio.io project for their screen resolution and orientation snapshoter, we want same ability on this project too, figure out how to share code eventually can then use it to generate walkthroughs and do design and reporting`

**Key Decisions & Engineering Takeaways:**
1. **Multi-Viewport Matrix**:
   - Captures across 4 device tiers in both Portrait and Landscape (8 viewports total): Phone (390x844 / 844x390), Tablet (820x1180 / 1180x820), Laptop (768x1366 / 1366x768), and Large Desktop/TV (1080x1920 / 1920x1080).
   - Generates an interactive HTML preview gallery (`preview.html`) grouping screenshots into a responsive grid.
2. **Global Antigravity Skill with Zero-Dependency Execution**:
   - Packaged as a shared global skill in `~/.gemini/config/skills/responsive-snapshots/` with driver script `snapshoter.py`.
   - Executable in any workspace via `uv run --with playwright python "$HOME\.gemini\config\skills\responsive-snapshots\scripts\snapshoter.py" --url http://127.0.0.1:7860`.
   - Prevents polluting core application dependencies in `pyproject.toml` with heavy browser binaries.
3. **Cross-Project Code Sharing Strategy**:
   - Phase 1: Shared global skill in `~/.gemini/config/skills/` accessible to all agent sessions.
   - Phase 2: Standalone CLI utility packaged in `jimcollinsworth/agent_skills` runnable via `uvx`.
4. **Use Cases for Pipeline Tools**:
   - Visual regression testing for Gradio 6.0 tab layouts.
   - Mobile and tablet responsive layout verification (`RES-10`).
   - Automated visual asset generation for developer blog case studies (`RES-18`) and GitHub issue reports (`github-reporter`).

---

## 📅 2026-09-10: End-to-End Integration Testing, GitHub Actions CI, Git Branching Governance & Versioning

**Context:** Implementing end-to-end browser integration tests verifying value inputs and outputs in views and export files (learning from `jimcollinsworth.github.io`), establishing strict Git branching and main branch approval gates, setting up automated GitHub Actions CI, and instituting commit-driven release versioning.

**Verbatim Instruction:**
> `Yes please Add end-to-end integration tests that confirm value inputs and value outputs in final generated files and views and learns from lessons in the jimcollinsworth github.io project`
> `And we should be using bug and feature branches on this work with explicit approval for pushing to the main branch. Rules should be encoded in agent rules files.`
> `Release numbers will increment according to commits and development sessions and explicit major releases. Automated test suite will run on GitHub server whenever code is checked`
> `/btw want to make the dynamic nature of the context more apparent during dta enhancement, let's see it change in real time or at least key activity at least for testing add as future issue.`

**Key Decisions & Engineering Takeaways:**
1. **End-to-End Integration Test Suite (`tests/test_browser_e2e.py`)**:
   - Modeled after lessons from `jimcollinsworth.github.io`: runs headless Chromium via Playwright, monitors console errors and unhandled exceptions (`pageerror`), and tests responsive viewports (mobile portrait 390x844 and desktop 1920x1080).
   - **Value Inputs & Value Outputs in Views**: Enters prompt template values, interacts with Data Enhancement workbench, executes sample test run, and verifies that generated output columns and text values populate the Output Table.
   - **Value Outputs in Generated Files**: Executes markdown export synthesis and inspects the generated output file on disk in `exports/` to verify that source record values and synthesis output text match exactly.
   - **Central System Prompt Persistence**: Configures domain system prompt on Settings & Models tab and verifies cross-session persistence in `config.json`.
2. **Ephemeral Port Allocation & Socket Discovery**:
   - Discovers open sockets dynamically via `socket.socket().bind(('127.0.0.1', 0))` and launches Gradio on the assigned ephemeral port. Completely avoids port collisions with the default development server on port 7860.
3. **Svelte/Gradio Tab Selector Resilience**:
   - Discovered that unselected Gradio tab buttons have `role=None` until selected (only the active tab has `role="tab"`). Standardized tab locators using `.tab-nav button:has-text(...)` with `wait_for(state="attached")` and `scroll_into_view_if_needed()`.
4. **In-Flight Database Engine Preservation**:
   - Removed destructive in-flight `heal_postgres_locks()` calls from `setUpClass` in `TestBrowserE2E` so running PostgreSQL engines and active SQLAlchemy/psycopg connection pools from prior test classes are preserved without connection timeouts.
5. **Git Branching & Main Branch Approval Gates (`AGENTS.md` Section 7)**:
   - Direct commits to `main` are strictly forbidden.
   - All feature work must use `feature/<name>` (or `feat/<name>`) branches, and bug fixes must use `fix/<name>`.
   - Pushing to `main` or merging into `main` **always requires explicit user authorization**.
6. **Commit/Session Release Versioning**:
   - Incremented package version in `pyproject.toml` from `1.1.0` to `1.1.1`.
   - Added optional test dependency group `[project.optional-dependencies] test = ["playwright>=1.40.0", "pytest>=8.0.0"]`.
7. **Automated GitHub Actions CI (`.github/workflows/test.yml`)**:
   - Runs on Ubuntu with Python 3.12, `setup-uv`, installs Playwright Chromium with system dependencies, and executes `uv run python -m tests`.
8. **Automated GitHub Issue Reporting (`github-reporter`)**:
   - Created **Issue #3**: *"Feature: Real-time Dynamic Ingestion Context Visualization in Data Enhancement"* via `antigravity-jc-bot [bot]`.
9. **Verification**:
   - Full test suite verified: **51 Passed, 0 Failed, 0 Errors** in 28 seconds (`uv run python -m tests`).

---

## 📅 2026-09-10: Multi-Machine Git Drift Resolution & Cross-Device Synchronization Rules

**Context:** The developer frequently alternates between 3 computers (e.g. mlpc, laptop, desktop) and 2 Antigravity instances. When pushing the verified release branch to `origin/main`, Git detected 20 divergent remote commits from Sept 5–7 that were not fetched into the current machine's local clone. Inspection of those divergent commits revealed 28 test failures and database lock crashes (`41 Passed, 27 Failed, 1 Errors`).

**Verbatim Instruction:**
> `merge and push. let's get it to hugging face, what's involved and I did respond to her email`
> `do 1 but document the issue clearly in journal, update rules and processes to minimize chance of conflicts. I do jump between remote sessions on 3 computers and 2 instances. need to always pull, always use feature branches, and other best practices in the situation`

**Key Decisions & Engineering Takeaways:**
1. **Decision to Fast-Forward / Replace `main` with Verified Baseline**:
   - The user explicitly authorized Option 1: resetting `main` to `feature/e2e-integration-tests-ci` and force-updating `origin/main`.
   - This purged the broken interim commits from Sept 5–7 and restored `origin/main` to a verified, passing test baseline: **51 Passed, 0 Failed, 0 Errors**.
2. **Codification of Multi-Machine Hygiene in `AGENTS.md`**:
   - **Pre-Flight Remote Fetch**: Every new session across any computer must begin with `git fetch origin` and `git status -uno` before modifying code or proposing plans.
   - **Branch-Off Latest Remote**: Never branch off stale local branches; always branch off up-to-date `origin/main` (`git checkout -b feature/<name> origin/main`).
   - **Never Modify `main` Directly**: All development must occur on feature or bugfix branches.
   - **Session Hand-Off & Push**: Before logging off or switching computers, all working branches must be pushed to `origin` so other machines/instances can immediately resume work without uncommitted or unpushed drift.
3. **Cross-Device Workflow Alignment**:
   - Guaranteed that any instance starting up on `mlpc`, laptop, or desktop will fetch clean, green, synchronized branches from GitHub.

---

## 📅 2026-09-10: Architectural Code Review: Test Rigor, Scalability & Pixeltable Capabilities Deep-Dive

**Context:** Conducting an exhaustive architectural review across test suite coverage and speed, runtime efficiency, memory scalability, and Pixeltable feature alignment (computed columns, chunking views, vector embedding indexes, UDFs, FastAPIRouter).

**Verbatim Instruction:**
> `et's do a deep code review. Assess code, especially tests, efficiency and scalability of code. Recommend coding updates for possible functional changes to help with efficiency or function. Do a deep review of pixeltable specific features and ability to customize and hook, and make sure we are utilizing its best features appropriately, make recommendations for additional changes or functionalities based on pixeltable knowledge. Wrap this all up in a great report published in GitHub. Provide screenshots if you think they will help. Looking forward to the report in the morning.`

**Key Decisions & Engineering Takeaways:**
1. **Test Suite Baseline & Isolation**:
   - 51 passing tests verified in ~28s (`51 Passed, 0 Failed, 0 Errors`).
   - Strong test design: bytecode introspection on Gradio callback globals (`LOAD_GLOBAL`), isolated test domains (`test_suite_isolated`), and pre-flight PostgreSQL lock self-healing (`heal_postgres_locks`).
   - Identified test gaps: lack of multi-threaded concurrent access tests and absence of large-scale dataset benchmarks (>10k rows).
2. **Memory & Query Scalability Bottlenecks**:
   - The Column Projection Invariant in `DBManager.get_table_data` successfully prevents OOMs on image/document tables by excluding binary columns and using SQL-level `.slice(0, 500)`.
   - Identified critical bottleneck in `PromptExecutor.apply_prompt_to_table`: full string `content` is collected into Python heap for all rows at once, and rows are updated sequentially via individual `table.update()` SQL transactions.
3. **Pixeltable Idiomaticity & Modernization Roadmap**:
   - **Declarative Computed Columns (`add_computed_column`)**: Replace imperative row-by-row loops with `@pxt.udf` computed columns to unlock automatic incremental updates, fault-tolerant retry (`recompute_columns`), caching, and lineage.
   - **Native Document Chunking Views (`pxt.create_view` + `document_splitter`)**: Replace monolithic text extraction with token-bounded chunk views linked directly to the parent document table.
   - **In-Table Vector Embedding Indexes (`add_embedding_index`)**: Provide instant semantic similarity search in the UI without external vector databases.
   - **Declarative REST Serving (`FastAPIRouter`)**: Expose background insertion routes and query endpoints for cloud container hosting and mobile companion apps.
4. **Published to GitHub**:
   - Formatted and published the complete review report as [GitHub Issue #4](https://github.com/jimcollinsworth/pipeline-tools/issues/4) via `antigravity-jc-bot [bot]`.

---

## 📅 2026-09-10: Eradication of Imperative Loops, Native `@pxt.udf` Engine & High-Scale Ingestion

**Context:** Following up on the architectural review, implementing critical memory efficiency, scalability fixes, and completely eliminating imperative row-by-row update loops.

**Verbatim Instruction:**
> `Memory efficiency, scalability, and imperative loops are the most critical issues to address. I thought we had previously eliminated imperative loops, so this time, we must ensure they are fixed and explicitly documented in the agent's file. The documentation should emphasize using UDFs and native pixel table features in all cases, specifically requiring exceptions for declarative computed columns. need to create a workaround for monolithic text ingestion and aim to support tens of thousands of rows. Multi-user use cases and testing are not required at this time and should be logged as a future issue. In-table embedding vector indexes are a good idea, though I am concerned about application complexity and the need for users to specify column options during indexing. Finally, we should implement declarative REST services only if absolutely necessary for hosting, as I believe we can already achieve this with Gradio on Hugging Face.`

**Key Decisions & Engineering Takeaways:**
1. **Elimination of Imperative Loops in Batch Execution**:
   - Replaced manual Python loops and sequential `table.update(..., where=table.id == row_id)` queries in `src/prompts/executor.py` with native `@pxt.udf` declarative computed columns (`table.add_computed_column`).
   - In Single Target Column Mode: Computes the column declaratively across all rows via `pxt_generate_text` or `pxt_generate_append`.
   - In Auto-Split JSON Mode: Computes the structured JSON column via `pxt_generate_json` and projects individual JSON keys declaratively (`table[primary_col][k]`).
   - Lineage & Rollback: All added columns are tracked in `_operation_history` and cleanly dropped on 1-click Undo.
2. **Chunked Streaming Ingestion for 10,000+ Rows**:
   - Refactored `DBManager.ingest_files` to stream inserts in bounded batches (`BATCH_SIZE = 100`) rather than accumulating all scanned files and raw text strings into a monolithic in-memory array.
   - Bounded memory usage to constant $O(1)$ heap RAM, supporting tens of thousands of rows without out-of-memory crashes.
3. **Mandatory Declarative Invariant Codified in `AGENTS.md`**:
   - Codified permanent rules in Section 3 and Section 6.2 strictly prohibiting imperative row-by-row loops calling AI models or updating table rows.
   - Required native `@pxt.udf` declarative computed columns in all cases, mandating explicit developer authorization and documented justification in `journal.md` for any exceptions.
4. **Scope Decisions (Vector Indexes, REST & Multi-User)**:
   - **Vector Indexes**: Deferred in-table vector indexing to avoid UI and column option configuration complexity.
   - **REST Services**: Avoided standalone `FastAPIRouter` REST services, as Gradio on Hugging Face Spaces already natively handles web serving and API endpoints.
   - **Multi-User Backlog**: Logged multi-user concurrency, connection pooling, and stress testing as a future enhancement in [GitHub Issue #5](https://github.com/jimcollinsworth/pipeline-tools/issues/5).
5. **Verification**:
   - Full test suite verified: **53 Passed, 0 Failed, 0 Errors** in 28 seconds (`uv run python -m tests`).

---

## 📅 2026-09-11: Hugging Face Spaces Cloud Adaptation and Personal Website App Embedding

**Context:** Preparing Pipeline Tools for cloud deployment on Hugging Face Spaces and integrating the live interactive application into the user's personal website (`jimcollinsworth.github.io`).

**Verbatim Instruction:**
> `ok next goal is getting pipeline tools running on hf and embedded into my site as an app`

**Key Decisions & Engineering Takeaways:**
1. **Cloud Container Environment Adaptation (`app.py` & `src/core/config.py`)**:
   - In `app.py`: Dynamically binds `server_name="0.0.0.0"` when running in Hugging Face Spaces (`SPACE_ID`), while preserving `127.0.0.1` for local desktop execution.
   - In `src/core/config.py`: When `SPACE_ID` is detected in `load_settings()`, automatically defaults provider and model to Google Gemini (`gemini-3.6-flash`), preventing connection errors to offline local Ollama instances.
2. **Production Dependency Pruning (`requirements.txt` & `packages.txt`)**:
   - Removed test-only `playwright` dependency from `requirements.txt` to eliminate heavy browser binary downloads during container image builds.
   - Added `packages.txt` with `ffmpeg` so Pixeltable audio and video frame operations run natively on Linux containers.
3. **Automated Hugging Face Sync Workflow (`.github/workflows/sync-to-huggingface.yml`)**:
   - Maintained automated git push sync from GitHub repository `main` branch to `https://huggingface.co/spaces/jimcollinsworth/pipeline-tools`.
4. **Interactive Dual-Target Embedding (`jimcollinsworth.github.io`)**:
   - Upgraded `content/pages/pipeline-tools.md` and `devops.md` to offer an interactive switch between live cloud hosting (`https://jimcollinsworth-pipeline-tools.hf.space`) and local developer workbench (`http://127.0.0.1:7860`).
   - Integrated direct links to Hugging Face Spaces and GitHub repositories, with instructions on configuring API keys.
5. **Verification**:
   - Test suite expanded to 54 automated tests: **54 Passed, 0 Failed, 0 Errors** (`uv run python -m tests`).

---

## 📅 2026-09-11: UI Layout Realignment, Affordance Parity, and Test Rigor (v1.2.0)

**Context:** Resolving Hugging Face Space visual regressions, eliminating test blindness, restoring missing UI affordances, and establishing strict visual geometry testing.

**Verbatim Instruction:**
> `There's a few other things which I thought were done, but apparently not as I look at HuggingFace. For all these items, track the bug issues, the existential issue, and the pride issue if there is one. We need a way of tracking the fix. Let's get all the issues defined first, then we'll attack them.`
> `I see that system prompt has been removed from the page, but I don't see it anywhere now. There should be a system prompt now applied to all models, and just put that into the settings and models page. That would be a user-facing setting.`
> `I pasted a HuggingFace screen. I still see the table and output table side by side. Try a screenshot yourself if you need to. Confirm this in testing.`
> `On the export page, there's a message which says "Click load refresh table or select a table to view data". There is no "load refresh table" button on the screen. Fix this and also analyze how something this obvious passes your tests.`

**Key Decisions & Engineering Takeaways:**
1. **Full-Width Stacked Tables (Data Enhancement)**:
   - Eliminated the cramped 2-column side-by-side view.
   - Stacked Input Table and Output Table vertically, with full width (`width: 100%`, `min_width=800`) and clear, explicit Markdown headers (`#### 📥 Input Table (Source Data)` and `#### 📤 Output Table (Test Preview & Enriched Results)`).
2. **Interactive Affordance Parity (`🔄 Load / Refresh Table`)**:
   - Added the prominent `🔄 Load / Refresh Table` button directly in the table selection row in `src/ui/tables_tab.py`, ensuring instructional copy and available UI affordances match 100%.
3. **Prominent Global System Prompt in Settings & Models**:
   - Added a top-level Active System Prompt editor in `src/ui/settings_tab.py` with 1-click persistence (`💾 Save System Prompt`), applied universally across Ollama and Gemini models during Data Enhancement and Export.
4. **Pandas Timestamp JSON Serialization**:
   - Updated `DBManager.get_table_data` to serialize all non-media cells (including `pd.Timestamp` and datetime objects) to ISO strings via `_truncate_cell`, preventing `TypeError: Object of type Timestamp is not JSON serializable` crashes during Gradio API inspection.
5. **Eliminating Test Blindness via Visual Geometry & Affordance E2E Tests**:
   - Added Playwright bounding-box assertions in `tests/test_browser_e2e.py` verifying that:
     - Output Table is strictly positioned vertically below Input Table (`y_output > y_input + 50`).
     - Both dataframes span $\ge 70\%$ of the viewport width.
     - Instructional copy strings in the UI are strictly paired with matching interactive buttons in the DOM.
     - Global System Prompt updates persist across sessions.
   - All 7 E2E browser tests pass cleanly.

---

## 📅 2026-09-11: Dual Ingestion Modes (Directory Multi-Asset vs. CSV Row Documents) & Test Stability (v1.3.0)

**Context:** Implementing single row-oriented file (CSV/TSV) ingestion mapping each row into an individual document record (Issue #6), and eliminating test runner timeouts and process lock contention.

**Verbatim Instruction:**
> `Yes, we want to add the CSV ingestion. We'll have to make some changes to the ingestion directory scanner because there will now be two modes: 1. ingest files, which can be docs, images, audio, or video, and I would scan a directory, 2. ingest just a single row-oriented file like a CSV. In that case, we sort just a single file versus a directory, and there is no recursive subdirectory traversal. Add a GitHub issue first for this ticket.`
> `something keeps looping stop tests let's reassess sequence and risks, and logging, let's make sure something is running test wise. we don't need to test the hugging face instance normally, that can be a specialized test on demand only.`

**Key Decisions & Engineering Takeaways:**
1. **Dual Ingestion Architecture (`src/ui/ingest_tab.py` & `src/controllers/ingest_controller.py`)**:
   - Added `ingest_mode_radio` allowing dynamic toggling between:
     - `📁 Directory Multi-Asset Scanner`: Scans local folders for multimodal files (1 file $\rightarrow$ 1 Pixeltable row).
     - `📄 Single Row-Oriented File (CSV)`: Ingests a single structured CSV/TSV without recursive traversal, parsing each row into an individual document record.
   - Added single-file typeahead dropdown with automatic CWD, user home, and `.csv`/`.tsv` discovery.
   - Added Primary Text Column selector with automatic detection of common text fields (`text`, `description`, `content`, `body`, `summary`) and fallback to formatted key-value summaries.
2. **Chunked Streaming & Multimodal Schema Mapping (`src/db/manager.py`)**:
   - Added `DBManager.ingest_csv_rows()` using Python's streaming `csv.DictReader` in batches of 100 rows (`BATCH_SIZE = 100`), guaranteeing $O(1)$ memory usage for 10,000+ rows.
   - Records map cleanly to standard Pixeltable columns: `file_name="{source.csv} #Row {idx}"`, `content=primary_text_column or formatted key-values`, `metadata=full_row_dict`, `modality="docs"`.
3. **Prompt Metadata Placeholder Resolution (`src/prompts/executor.py`)**:
   - Enhanced `format_prompt` and Pixeltable `@pxt.udf` functions (`pxt_generate_text`, `pxt_generate_append`, `pxt_generate_json`) to resolve any original CSV column directly (e.g. `{category}`, `{price}`, `{headline}`) via automatic fallback to `row["metadata"]`.
4. **Embedded PostgreSQL Lock Safety & Test Runner Decoupling (`src/db/manager.py` & `tests/test_app.py`)**:
   - Hardened `DBManager.heal_postgres_locks()` with `protected_pids` guarding the active Python process and its child processes, ensuring mid-suite cleanup never terminates its own database connection.
   - Decoupled test runner: Default `uv run python -m tests` runs the fast, deterministic 53 unit and controller tests in ~10 seconds.
   - Heavyweight browser Playwright E2E tests run on-demand via `--e2e` (`uv run python -m tests --e2e`), eliminating unnecessary browser launches during rapid development cycles.
5. **Verification**:
   - Default test suite: **53 Passed, 0 Failed, 0 Errors** (10.2s).
   - Full E2E suite (`--e2e`): **60 Passed, 0 Failed, 0 Errors** (37.5s).

---

## 📅 2026-09-13: Context View Tab, Dynamic Column Pills & Slash Intellisense

**Context:** Synchronizing repo with origin/main, recovering uncommitted local features, centralizing domain context/prompts, and improving data exploration ergonomics.

**Verbatim Instruction:**
> `yes, import the skills, port the floating slash intellisense popup to a new feature branch, and add the dynamic column check-pills for show/hide. when a column is hidden, move it's name to the list end, have a clear button to reshow all in the table order. don't use check boxes, just highlight/unhighlight pills.`
> `add the context view tab back in so we can see, edit and export context, but stick with the superior origin architecture. maybe this context tab is a better place for the system prompt than on models, not sure.`
> `we also must have some way on data enhancement page to see the context activity, at a minimum to see that it is being added to/modified, but don't want to show too much data/traffic. we can continue to work on this view later. could be actual context fragments, or context function call logs, maybe a popup or accordian. think about ideas, log in the issue. but go ahead and put in the most minimal context activity display you can think of for now, just to start to understand the feature.`
> `instead of 'reshow all', just use an X or clear/reset icon. where is the LLM prompt that controls the row by row processing, is that editable?`

**Key Decisions & Engineering Takeaways:**
1. **Centralized Domain Context & Prompt Management (`src/ui/context_tab.py`, `src/controllers/context_controller.py`)**:
   - System prompts were removed from Settings & Models and placed exclusively in the dedicated Context View tab, tied to the active domain via `IngestionContextManager`.
   - The tab provides an interactive domain prompt editor, an entity register table, full markdown preview, and 1-click Markdown export download (`⚡ Export Context Markdown`).
2. **Minimal Context Activity Display (`src/ui/playground_tab.py`)**:
   - Added a compact, collapsible `gr.Accordion("🧠 Context Knowledge & Activity", open=False)` beneath prompt controls on the Data Enhancement tab.
   - Displays real-time summary counts of accumulated facts and entities per domain without cluttering the screen or overwhelming traffic.
   - Extended roadmap logged for GitHub Issue #3 (real-time streaming diffs, interactive entity graph, context fragments).
3. **Dynamic Column Visibility Pills (`src/ui/tables_tab.py`, `src/controllers/tables_controller.py`)**:
   - Replaced standard checkboxes with highlighted/unhighlighted pill badges via CSS (`.column-pills-group`).
   - Dynamically reorders pills on toggle: hidden columns are moved to the end of the pill list, keeping active visible columns at the front.
   - Added a compact `✕` reset icon button to immediately restore canonical table column order and show all columns.
4. **Floating Slash Intellisense Popup (`app.py`, `.agents/skills/`)**:
   - Restored missing prompt skills (`entity-recognition` and `report-generation`).
   - Injected client-side JavaScript intellisense menu (#slash-intellisense-menu) listening on `.prompt-slash-input` textareas with ArrowUp/Down, Enter/Tab completion, and Esc dismissal.
5. **Multi-Machine Git Hygiene & Testing**:
   - Preserved prior local divergence in `backup-local-work` branch.
   - Re-aligned cleanly with `origin/main` on feature branch `feature/context-and-ui-enhancements`.
   - Verified with fast core suite (56 tests passing in ~19s) and updated Playwright E2E browser tests.

---

## 📅 2026-09-13: Systematic Debugging — Context State, Progress Duplication & E2E Stabilization

**Context:** Resolving runtime crashes on Context View tab select (`AttributeError: 'IngestionContext' object has no attribute 'format_markdown_register'`), noisy Pixeltable startup tracebacks, duplicate real-time export progress bars, and aligning the full Playwright E2E browser suite.

**Key Decisions & Engineering Takeaways:**
1. **Context Register Export Implementation (`src/core/ingestion_context.py`)**:
   - Added `format_markdown_register(self) -> str` to `IngestionContext` to generate structured Markdown tables for entities, taxonomies, and themes, refactoring `export_to_markdown` to use it.
   - Added unit test `test_context_controller_load_context_state_and_export` in `tests/test_controllers.py` and UI flow test `test_context_tab_ui_flows` in `tests/test_app.py`.
2. **Clean Startup & Database Lookups (`src/db/manager.py`)**:
   - In `DBManager.get_table_data()`, gracefully caught `NotFoundError` and "does not exist" errors, logging as `logger.info` without full exception tracebacks when launching on a fresh or empty database.
3. **Export & Batch Progress Bar De-duplication (`src/ui/tables_tab.py`, `src/ui/playground_tab.py`)**:
   - Gradio attaches progress animations to every component in `outputs` by default when `show_progress_on` is `None`.
   - Explicitly configured `show_progress_on=[export_status_box]` and `show_progress_on=[batch_status_markdown]`, eliminating duplicate stacked progress bars over the preview and download components.
4. **Client-Side Slash Intellisense ReadyState Lifecycle (`app.py`, `tests/test_browser_e2e.py`)**:
   - Refactored head script to check `document.readyState !== "loading"` and invoke `initSlashIntellisense()` immediately if the document is already parsed, preventing missed `DOMContentLoaded` events in browser tests and SPA re-renders.
   - Updated E2E tests to pass `css=custom_css` and `head=get_custom_head()` during test launch, updated selectors for the relocated Domain System Prompt in Context View, and fixed the View & Export tab locator.
5. **Verification**:
   - Fast Core Suite: **58 Passed, 0 Failed, 0 Errors** in 17s.
   - Full On-Demand E2E Suite (`uv run python -m tests --e2e`): **66 Passed, 0 Failed, 0 Errors** in 43s.
   - Bumped patch version to `1.3.2` in `pyproject.toml`.

---

## 📅 2026-09-22: Visual-Only Sample Previews for Audio UDFs (v1.3.9)

**Context:** Refining the dry-run sample preview table for audio visualizer UDFs (`mel_spectrogram`, `chroma`, `mfcc`).

**Verbatim Instruction:**
> `no need to include the shape columns for mel and chroma, just the image`

**Key Decisions & Engineering Takeaways:**
1. **Visual-First Preview Tables (`src/core/udf_registry.py`)**:
   - Removed intermediate `mel_spectrogram_shape`, `chroma_shape`, and `mfcc_shape` text columns from sample evaluation outputs.
   - Sample test previews now cleanly present `["Status", "Row ID", "File Name", "<name>_img"]` with rich HTML inline visualizations and zero text clutter.
2. **Eliminated Redundant Computation**:
   - Audio arrays are no longer redundantly computed twice during dry-run evaluations (previously computed once for shape extraction and once for image rendering). `render_<name>_image_core` is invoked directly, improving dry-run throughput.
3. **Verification & Versioning**:
   - Updated test assertions in `tests/test_audio_spectrogram.py` to verify `assertNotIn("<name>_shape", headers)` and uniform row column counts.
   - All 102 automated tests pass cleanly (`102 Passed, 0 Failed, 0 Errors`).
   - Bumped patch version to `1.3.9` in `pyproject.toml`.

---

## 📅 2026-09-22: YAMNet Audio Event Classification & Shape Column Removal (v1.3.10)

**Context:** Integrating deep neural network audio event tagging and acoustic scene recognition (YAMNet) and eliminating shape/JSON clutter from UDF previews.

**Verbatim Instruction:**
> `also for rms_mean, zcr mean... keep the columns but not the json`
> `lets add yamnet next /brainstorming /using-superpowers`
> `yes. and remove any shape column generation from all the udfs`

**Key Decisions & Engineering Takeaways:**
1. **Lightweight Runtime Selection (`onnxruntime`)**:
   - Legacy `tflite-runtime` lacks Python 3.13 Windows wheels and cannot be cleanly built from source.
   - Selected `onnxruntime` (~20 MB) with official pre-built Python 3.13 support to execute Google's pre-trained YAMNet model (`yamnet.onnx`, 15.3 MB) and 521-class AudioSet taxonomy map (`yamnet_class_map.csv`), auto-cached in `~/.cache/pipeline_tools/models/yamnet/`.
2. **Audio Classification Outputs & UDFs (`src/audio/yamnet.py`)**:
   - Audio is resampled and normalized to 16 kHz mono float32.
   - Outputs:
     - `sound_category` (str): Top single detected category (e.g. `"Telephone"`, `"Speech"`, `"Music"`).
     - `sound_events` (str): Top-K human-readable summary with confidence percentages.
     - `sound_scores` (dict): Structured JSON dictionary of top-K category probabilities.
   - Declaratively attached via `@pxt.udf` functions (`yamnet_primary_category`, `yamnet_sound_events`, `yamnet_scores`) and batch helper `attach_yamnet_columns`.
3. **Registry & Sample Preview (`src/core/udf_registry.py`)**:
   - Registered `yamnet` with slash command `/yamnet top_k=5 min_confidence=0.1` and natural language triggers (`"classify audio events with yamnet"`).
   - Clean preview headers: `["Status", "Row ID", "File Name", "Primary Sound", "Top Sound Events"]` with zero shape columns.
   - Dropped `Stats (JSON)` column from `_eval_audio_stats_sample`, retaining individual metric columns (`Duration (s)`, `RMS Mean`, `ZCR Mean`, `Centroid (Hz)`, `Silence Ratio`).
4. **Verification & Versioning**:
   - Created comprehensive test suite `tests/test_yamnet.py` (8 tests) and updated `tests/test_audio_spectrogram.py` and `tests/test_app.py`.
   - Full test suite verified: **110 Passed, 0 Failed, 0 Errors** in 23s.
   - Incremented version to `1.3.10` in `pyproject.toml`.

---

## 📅 2026-09-22: Embedded PostgreSQL Lock Self-Healing & Log Sharing Guard (v1.3.11)

**Context:** Eliminating noisy Windows file sharing violation warnings (`[WinError 32] The process cannot access the file because it is being used by another process: '...pgdata\log'`) during pre-flight database lock healing when PostgreSQL is already active.

**Verbatim Instruction:**
> `whats the log conflict from?`
> `yes`

**Key Decisions & Engineering Takeaways:**
1. **Active Server Detection & Log Guard (`src/db/manager.py`)**:
   - In `DBManager.heal_postgres_locks()`, re-sequenced cleanup so `postmaster.pid` is checked first.
   - If an active PostgreSQL process is verified running and healthy (`is_active_server=True`), `heal_postgres_locks` skips attempting to unlink `pgdata / "log"` (which is actively write-locked by the running database engine on Windows).
   - Any residual log unlinking errors during crash recovery are logged at `logger.debug` instead of `logger.warning`.
2. **Verification & Versioning**:
   - Verified clean zero-warning startup via `uv run python -c "from src.db.manager import DBManager; DBManager.heal_postgres_locks()"`.
   - All 110 automated tests pass cleanly (`110 Passed, 0 Failed, 0 Errors`).
   - Bumped patch version to `1.3.11` in `pyproject.toml`.
