# Feature: User Interface & Modern Interaction

- **Feature ID**: `user-interface`
- **Status**: Planning & Backlog (Phase 5 / Complete Refresh)
- **Primary Stakeholder / Vision**: Complete modern UI refresh, abstract, cool, interactive document-centric experience

---

## 1. Overview & Vision

The current Gradio interface provides a functional 4-tab workbench (Ingestion & Scanner, Data Enhancement, View & Export, Settings & Models). The next generation of Pipeline Tools will transition to a **complete UI refresh**:
1. **Interactive Document-Centric Canvas**: Moving beyond traditional spreadsheet/table grids toward an abstract, fluid workspace where records are presented as living documents with embedded visualizations, interactive rollups, and visual cards.
2. **Direct Visual & Touch Column Manipulation**: Replace dense drop-down menus with direct-manipulation visual chips, drag reordering, and 1-tap column toggling.
3. **Integrated Activity & Debug Drawer**: A persistent, collapsible bottom console streaming live LLM requests, tokens/sec metrics, and system activity in real time.

---

## 2. Core Requirements

### 2.1 Complete UI Refresh & Theming
- **Visual Design**: Sleek, modern design language with high contrast, responsive typography, and consistent spacing across all tabs.
- **Full-Width Stability**: Maintain strict layout rules preventing tab jumping or content shifting (`max-width: 95% !important`).
- **Interactive Themes**: Dark Terminal, Modern Editorial, and Minimal Slate themes selectable by the user.

### 2.2 Table Grid vs. Single Document View Mode Toggle (Option 1)
- **Unified Mode Toggle**: `[ 📊 Table Grid ]`  `[ 📄 Single Document ]` segmented radio placed above data displays.
- **Table Grid Mode**: Full-width multi-row spreadsheet view (`gr.Dataframe`) for multi-record browsing and row selection.
- **Single Document Mode**: Focused full-width single-record document card with row paging toolbar (`◀ Previous`, `Record X of Y`, `Next ▶`), untruncated text, entity highlighting, and active media players.
- **Simplicity Principle**: Clean native Gradio components without custom CSS complexity; instant 0ms switching.

### 2.3 Direct Visual Column Selection & Pill Bar (`RES-15`)
- **Column Visibility Pill Bar**: Clickable interactive chips (`[✓ file_name]  [✓ content]  [✓ summary]  [✗ file_size]`) directly above the table/document.
- **Bi-Directional Filtering**: Toggling a pill immediately hides/shows the column in both Table Grid and Single Document views without re-querying the database.
- **Bulk Toggles**: 1-click `Select All` and `Deselect All` buttons.
- **Prompt Auto-Chips**: 1-click insertion of `{column_name}` placeholders directly into active prompt templates.
- **Prefix Badges**: Visual indicators for column lineage:
  - `[I]` Imported / Source columns
  - `[C]` Calculated / Computed LLM columns
  - `[U]` User / Manual annotations

### 2.3 Live Activity & LLM Console Drawer (`RES-22`)
- **Slide-Up Bottom Console**: Collapsible bottom drawer showing real-time pipeline execution, LLM prompts/responses, network latency, and memory telemetry.
- **Filterable Streams**: Toggles for *LLM Prompts & Responses*, *Network Calls*, *Database Events*, and *Warnings/Errors*.
- **Ring Buffer & Export**: Keep the last 500 lines in memory with 1-click Copy Log and Clear Log actions.

### 2.4 Mobile & Tablet Responsive Viewports (`RES-10`)
- **Adaptive Breakpoints**: Mobile breakpoints (`@media (max-width: 768px)`) adapting the grid to stacked single-column layouts.
- **Touch-Friendly Controls**: Touch targets $\ge 44\text{px}$ and swipeable card navigation for mobile review.

---

## 3. Implementation Plan & Checklist

- [ ] **Phase 1: Incremental UI Fixes & Refinements**
  - [ ] Polish active button press effects and eliminate residual layout jumps.
  - [ ] Streamline tab auto-refresh and selection state synchronization.
  - [ ] Refactor column list selector into initial prototype pill bar.
- [ ] **Phase 2: Live Activity & Debug Drawer (`RES-22`)**
  - [ ] Implement sliding bottom accordion component in `app.py`.
  - [ ] Create logger handler streaming to Gradio output component via ring buffer.
  - [ ] Unit and controller tests for log stream capturing.
- [ ] **Phase 3: Interactive Document Canvas & Theming**
  - [ ] Prototype rich card / living document layout for row review.
  - [ ] Implement CSS theme switcher (Dark, Editorial, Slate).
- [ ] **Phase 4: Responsive & Mobile Polish**
  - [ ] Add mobile media queries and touch target testing.
