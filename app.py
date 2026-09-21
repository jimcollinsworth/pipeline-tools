import os
import sys
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
import string
import signal
import atexit
from pathlib import Path
import json
import gradio as gr
from src.core.skills import SkillsRegistry
from src.ui.settings_tab import render_settings_tab
from src.ui.ingest_tab import render_ingest_tab
from src.ui.playground_tab import render_playground_tab
from src.ui.context_tab import render_context_tab
from src.ui.tables_tab import render_tables_tab

# Hugging Face ZeroGPU compatibility hook: prevents startup error if ZeroGPU hardware is selected
try:
    import spaces
    @spaces.GPU
    def _hf_zero_gpu_guard():
        return True
except Exception:
    pass

# Gradio 6.0: theme and css must be passed to launch(), not Blocks()
clean_theme = gr.themes.Default(
    primary_hue=gr.themes.colors.blue,
    secondary_hue=gr.themes.colors.neutral,
    neutral_hue=gr.themes.colors.neutral,
    text_size="sm",
    radius_size="sm",
    font=[gr.themes.GoogleFont("Inter"), "SF Pro Text", "Segoe UI", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "SF Mono", "Consolas", "monospace"]
).set(
    body_background_fill="#f7f5f0",
    body_background_fill_dark="#121212",
    block_background_fill="#ffffff",
    block_background_fill_dark="#181818",
    block_border_width="0px",
    block_shadow="none",
    button_primary_background_fill="#2563eb",
    button_primary_background_fill_hover="#1d4ed8",
    button_primary_text_color="#ffffff",
    button_primary_border_color="#1d4ed8",
    button_secondary_background_fill="#ffffff",
    button_secondary_background_fill_hover="#f4f1ea",
    button_secondary_text_color="#18181b",
    button_secondary_border_color="#d4d0c8",
    input_background_fill="#ffffff",
    input_border_color="#d4d0c8",
    input_border_width="1px",
    input_radius="6px",
    table_border_color="#e5e1d8",
    table_row_focus="#f4f1ea"
)

custom_css = """
/* Full-Width Layout & Clean Canvas */
body, gradio-app, .gradio-container {
    max-width: 98% !important;
    width: 98% !important;
    margin: 6px auto !important;
    background-color: #f7f5f0 !important;
    color: #18181b !important;
}

.tabitem, .tabs, .tab-nav {
    width: 100% !important;
    min-width: 100% !important;
}

/* Remove excessive nested boxes and borders */
.gr-block, .gr-form, .gr-box, fieldset {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 4px 0 !important;
}

/* Minimalist Header */
.app-header {
    border-bottom: 1px solid #d4d0c8;
    padding-bottom: 12px;
    margin-bottom: 16px;
}
.app-header h1 {
    font-size: 1.45rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.3px !important;
    margin-bottom: 2px !important;
    color: #18181b !important;
}
.app-header p {
    font-size: 0.85rem !important;
    color: #71717a !important;
    margin: 0 !important;
}

/* Clean Modern Tabs */
.tab-nav {
    border-bottom: 1px solid #d4d0c8 !important;
    gap: 8px !important;
    margin-bottom: 20px !important;
    background: transparent !important;
}
.tab-nav button {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    color: #71717a !important;
    padding: 8px 16px !important;
    border: none !important;
    border-radius: 6px !important;
    background: transparent !important;
    transition: all 0.15s ease !important;
}
.tab-nav button.selected, .tab-nav button[aria-selected="true"] {
    background: #e4e0d5 !important;
    color: #18181b !important;
    font-weight: 700 !important;
}
.tab-nav button:hover:not(.selected) {
    background: #eae6dd !important;
    color: #18181b !important;
}

/* Status Panels - Clean single-card container */
.status-panel {
    margin-top: 14px !important;
    padding: 14px 18px !important;
    border-radius: 6px !important;
    border: 1px solid #d4d0c8 !important;
    background: #ffffff !important;
    min-height: 70px !important;
    width: 100% !important;
}
.status-panel table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 12px 0 !important;
}
.status-panel th, .status-panel td {
    padding: 8px 12px !important;
    border: 1px solid #e5e1d8 !important;
    text-align: left !important;
}
.status-panel th {
    background-color: #f4f1ea !important;
    font-weight: 600 !important;
}
.progress-level {
    margin-bottom: 8px !important;
    max-width: 100% !important;
    overflow: hidden !important;
}
.progress-level-inner {
    max-width: 100% !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
.meta-text {
    font-size: 0.8rem !important;
    max-width: 100% !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

/* Regular, Clean Interactive Buttons */
button.primary, button[variant="primary"], button.stop, button[variant="stop"] {
    background: #2563eb !important;
    color: #ffffff !important;
    border: 1px solid #1d4ed8 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
    cursor: pointer !important;
    transition: background 0.12s ease, transform 0.08s ease, box-shadow 0.08s ease !important;
}
button.primary:hover, button[variant="primary"]:hover, button.stop:hover, button[variant="stop"]:hover {
    background: #1d4ed8 !important;
    border-color: #1e40af !important;
}
button.primary:active, button[variant="primary"]:active, button.stop:active, button[variant="stop"]:active {
    transform: translateY(1px) !important;
    box-shadow: 0 0 1px rgba(0,0,0,0.1) !important;
    background: #1e40af !important;
}

button.secondary, button[variant="secondary"], .gr-button:not(.primary):not(.stop):not([variant="primary"]):not([variant="stop"]):not(.icon-button) {
    background: #ffffff !important;
    color: #18181b !important;
    border: 1px solid #d4d0c8 !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    padding: 6px 14px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    cursor: pointer !important;
    transition: background 0.12s ease, transform 0.08s ease, box-shadow 0.08s ease !important;
}
button.secondary:hover, button[variant="secondary"]:hover, .gr-button:not(.primary):not(.stop):not([variant="primary"]):not([variant="stop"]):not(.icon-button):hover {
    background: #f4f1ea !important;
    border-color: #b8b3a8 !important;
}
button.secondary:active, button[variant="secondary"]:active, .gr-button:not(.primary):not(.stop):not([variant="primary"]):not([variant="stop"]):not(.icon-button):active {
    transform: translateY(1px) !important;
    box-shadow: 0 0 1px rgba(0,0,0,0.08) !important;
    background: #eae6dd !important;
}

/* Neutralize dataframe internal icon/utility buttons so they don't render as ghost buttons */
.gr-dataframe button, button.icon-button, button:empty, button[aria-label="Fullscreen"], button[title="Fullscreen"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 2px 4px !important;
    min-width: unset !important;
}

/* Single-layer Clean Inputs */
input:not([type="checkbox"]):not([type="radio"]), textarea, select, .gr-dropdown {
    border: 1px solid #d4d0c8 !important;
    border-radius: 6px !important;
    background: #ffffff !important;
    color: #18181b !important;
}
input:focus, textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 1px #2563eb !important;
}

/* Clean Native Checkboxes & Radios */
input[type="checkbox"], input[type="radio"] {
    accent-color: #2563eb !important;
    cursor: pointer !important;
}

/* Checkbox & Radio Labels - Consistent, No Dark Black Fills */
.gr-checkboxgroup label, .gr-radio label {
    border: 1px solid #d4d0c8 !important;
    border-radius: 6px !important;
    background: #ffffff !important;
    color: #18181b !important;
    padding: 4px 10px !important;
    transition: all 0.15s ease !important;
    margin-right: 6px !important;
    cursor: pointer !important;
}
.gr-checkboxgroup label:hover, .gr-radio label:hover {
    background: #f4f1ea !important;
}
.gr-checkboxgroup label:has(input:checked), .gr-radio label:has(input:checked) {
    background: #ffffff !important;
    color: #18181b !important;
    border-color: #94a3b8 !important;
}
.gr-checkboxgroup label:has(input:checked) span, .gr-radio label:has(input:checked) span {
    color: #18181b !important;
    font-weight: 600 !important;
}

/* Clean High-Contrast Data Tables */
.gr-dataframe, table {
    border: 1px solid #d4d0c8 !important;
    border-radius: 6px !important;
    background: #ffffff !important;
    font-size: 0.85rem !important;
}
th {
    background: #f0ece4 !important;
    border-bottom: 1px solid #d4d0c8 !important;
    color: #18181b !important;
    font-weight: 600 !important;
    font-size: 0.8rem !important;
}
td {
    border-bottom: 1px solid #f0ece4 !important;
    color: #27272a !important;
}

/* Micro typography */
code {
    background: #f0ece4 !important;
    color: #18181b !important;
    padding: 1px 4px !important;
    border-radius: 3px !important;
    font-size: 0.82rem !important;
}

/* Floating Slash Intellisense Menu */
.slash-intellisense-menu {
    position: absolute;
    z-index: 10000;
    background: #ffffff;
    border: 1px solid #d4d0c8;
    border-radius: 8px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    max-height: 280px;
    overflow-y: auto;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.slash-menu-header {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 6px 12px;
    background: #f4f1ea;
    color: #52525b;
    border-bottom: 1px solid #e5e1d8;
}
.slash-menu-list {
    padding: 4px 0;
}
.slash-menu-item {
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid #f4f1ea;
    transition: background-color 0.15s ease;
}
.slash-menu-item:last-child {
    border-bottom: none;
}
.slash-menu-item.active, .slash-menu-item:hover {
    background-color: #eff6ff;
}
.slash-menu-cmd {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: #2563eb;
    margin-bottom: 2px;
}
.slash-menu-desc {
    font-size: 0.76rem;
    color: #71717a;
    line-height: 1.3;
}

/* Interactive Column Visibility Check-Pills (No Checkboxes) */
.column-pills-group input[type="checkbox"] {
    display: none !important;
}
.column-pills-group label {
    border: 1px solid #d4d0c8 !important;
    border-radius: 9999px !important;
    padding: 3px 12px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    background: #f4f4f5 !important;
    color: #71717a !important;
    margin: 2px 4px !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
}
.column-pills-group label:has(input:checked) {
    border-color: #2563eb !important;
    background: #eff6ff !important;
    color: #1d4ed8 !important;
    font-weight: 600 !important;
}
.column-pills-group label:hover {
    border-color: #94a3b8 !important;
}
"""

def get_custom_head() -> str:
    """Generate HTML head script injecting discovered skills and in-textbox slash Intellisense."""
    skills_json = json.dumps(SkillsRegistry.list_skills())
    return f"""
<script>
window.PIPELINE_SKILLS = {skills_json};

const initSlashIntellisense = () => {{
    const disableAutofill = () => {{
        document.querySelectorAll("input").forEach(input => {{
            if (input.type === "password") {{
                input.setAttribute("autocomplete", "new-password");
                input.setAttribute("data-1p-ignore", "true");
            }} else {{
                input.setAttribute("autocomplete", "off");
            }}
        }});
    }};
    if (document.body) {{
        disableAutofill();
        const observer = new MutationObserver(disableAutofill);
        observer.observe(document.body, {{ childList: true, subtree: true }});
    }}

    // In-Textbox Direct Slash Intellisense
    let activeTextarea = null;
    let selectedIndex = 0;
    let currentMatches = [];
    let queryStartIndex = -1;

    let menu = document.getElementById("slash-intellisense-menu");
    if (!menu) {{
        menu = document.createElement("div");
        menu.id = "slash-intellisense-menu";
        menu.className = "slash-intellisense-menu";
        menu.setAttribute("role", "listbox");
        menu.setAttribute("aria-label", "Discovered Agent Skills");
        menu.style.display = "none";
        (document.body || document.documentElement).appendChild(menu);
    }}

    const hideMenu = () => {{
        menu.style.display = "none";
        activeTextarea = null;
        currentMatches = [];
        selectedIndex = 0;
    }};

    const insertSkill = (skill) => {{
        if (!activeTextarea || queryStartIndex === -1) return;
        const text = activeTextarea.value;
        const cursorPos = activeTextarea.selectionStart;
        const beforeSlash = text.substring(0, queryStartIndex);
        const afterCursor = text.substring(cursorPos);
        const cmd = skill.slash_command || `/${{skill.name}}`;
        const insertedText = `${{cmd}} `;

        activeTextarea.value = beforeSlash + insertedText + afterCursor;
        const newCursor = queryStartIndex + insertedText.length;
        activeTextarea.setSelectionRange(newCursor, newCursor);

        // Notify Gradio of state change
        activeTextarea.dispatchEvent(new Event("input", {{ bubbles: true }}));
        activeTextarea.dispatchEvent(new Event("change", {{ bubbles: true }}));
        hideMenu();
        activeTextarea.focus();
    }};

    const positionMenu = () => {{
        if (!activeTextarea) return;
        const rect = activeTextarea.getBoundingClientRect();
        menu.style.left = `${{window.scrollX + rect.left}}px`;
        menu.style.top = `${{window.scrollY + rect.bottom + 4}}px`;
        menu.style.width = `${{Math.min(rect.width, 540)}}px`;
    }};

    const renderMenu = () => {{
        if (!currentMatches.length) {{
            hideMenu();
            return;
        }}
        let html = '<div class="slash-menu-header">⚡ Agent Skills & Directives</div><div class="slash-menu-list">';
        currentMatches.forEach((s, idx) => {{
            const isSelected = idx === selectedIndex;
            const cmd = s.slash_command || `/${{s.name}}`;
            html += `<div class="slash-menu-item ${{isSelected ? 'active' : ''}}" role="option" aria-selected="${{isSelected}}" data-index="${{idx}}">
                <div class="slash-menu-cmd">${{cmd}}</div>
                <div class="slash-menu-desc">${{s.description || ''}}</div>
            </div>`;
        }});
        html += '</div>';
        menu.innerHTML = html;

        menu.querySelectorAll(".slash-menu-item").forEach(item => {{
            item.addEventListener("mousedown", (e) => {{
                e.preventDefault();
                const idx = parseInt(item.getAttribute("data-index"), 10);
                insertSkill(currentMatches[idx]);
            }});
        }});

        positionMenu();
        menu.style.display = "block";
    }};

    document.addEventListener("input", (e) => {{
        const target = e.target;
        if (!target || target.tagName !== "TEXTAREA") return;
        const parent = target.closest(".prompt-slash-input");
        if (!parent) return;

        const val = target.value;
        const cursorPos = target.selectionStart;
        const textBeforeCursor = val.substring(0, cursorPos);

        const match = textBeforeCursor.match(/(?:^|[\\s\\n])\\/([a-zA-Z0-9_\\-]*)$/);
        if (match) {{
            activeTextarea = target;
            queryStartIndex = cursorPos - match[1].length - 1;
            const query = match[1].toLowerCase();

            const allSkills = window.PIPELINE_SKILLS || [];
            currentMatches = allSkills.filter(s => 
                s.name.toLowerCase().includes(query) ||
                (s.slash_command && s.slash_command.toLowerCase().includes(query)) ||
                (s.description && s.description.toLowerCase().includes(query))
            );
            selectedIndex = 0;
            renderMenu();
        }} else {{
            hideMenu();
        }}
    }});

    document.addEventListener("keydown", (e) => {{
        if (menu.style.display !== "block" || !activeTextarea) return;

        if (e.key === "ArrowDown") {{
            e.preventDefault();
            selectedIndex = (selectedIndex + 1) % currentMatches.length;
            renderMenu();
        }} else if (e.key === "ArrowUp") {{
            e.preventDefault();
            selectedIndex = (selectedIndex - 1 + currentMatches.length) % currentMatches.length;
            renderMenu();
        }} else if (e.key === "Enter" || e.key === "Tab") {{
            if (currentMatches[selectedIndex]) {{
                e.preventDefault();
                insertSkill(currentMatches[selectedIndex]);
            }}
        }} else if (e.key === "Escape") {{
            hideMenu();
        }}
    }});

    document.addEventListener("click", (e) => {{
        if (menu.style.display === "block" && !menu.contains(e.target) && e.target !== activeTextarea) {{
            hideMenu();
        }}
    }});
}};

if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", initSlashIntellisense);
}} else {{
    initSlashIntellisense();
}}
</script>
"""

def create_app():
    # Pre-flight embedded PostgreSQL lock self-healing
    try:
        from src.db.manager import DBManager
        DBManager.heal_postgres_locks(force_purge_orphans=False)
    except Exception:
        pass

    with gr.Blocks(title="Pipeline Tools v1.3", fill_width=True) as demo:
        gr.Markdown(
            """
            <div class="app-header">
                <h1>PIPELINE TOOLS v1.3 // Multimodal Workbench</h1>
                <p>Declarative Ingestion (Pixeltable) &bull; Data Enhancement &bull; Context Knowledge &bull; View & Export</p>
            </div>
            """
        )
        
        with gr.Tabs():
            with gr.Tab("Ingestion & Scanner") as ingest_tab:
                print("  [1/5] Initializing Ingestion & Scanner tab...", flush=True)
                render_ingest_tab(tab=ingest_tab)
                
            with gr.Tab("Data Enhancement") as playground_tab:
                print("  [2/5] Initializing Data Enhancement tab (discovering models & tables)...", flush=True)
                render_playground_tab(tab=playground_tab)

            with gr.Tab("Context View") as context_tab:
                print("  [3/5] Initializing Context View tab (governance & knowledge register)...", flush=True)
                render_context_tab(tab=context_tab)
                
            with gr.Tab("View & Export") as tables_tab:
                print("  [4/5] Initializing View & Export tab...", flush=True)
                render_tables_tab(tab=tables_tab)
                
            with gr.Tab("Settings & Models") as settings_tab:
                print("  [5/5] Initializing Settings & Models tab...", flush=True)
                render_settings_tab(tab=settings_tab)

    print("  ✅ All 5 workbench tabs and database connections initialized!", flush=True)
    return demo
demo = None

if __name__ == "__main__":
    def clean_exit(sig=None, frame=None):
        print("\n🛑 Shutting down Pipeline Tools cleanly...", flush=True)
        if demo is not None:
            try:
                demo.close()
            except Exception:
                pass
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, clean_exit)
        signal.signal(signal.SIGTERM, clean_exit)
    except Exception:
        pass
    atexit.register(lambda: demo.close() if demo is not None else None)

    if "--reload" in sys.argv:
        import subprocess
        print("\n🔄 Launching Pipeline Tools in Gradio Auto-Reload mode (watching app.py & src/)...", flush=True)
        cmd = [sys.executable, "-m", "gradio", "app.py", "--watch-dirs", "src"]
        sys.exit(subprocess.call(cmd))

    print("\n⏳ Initializing Pipeline Tools workbench & database...", flush=True)
    demo = create_app()
    port = 7860

    # Collect existing drives and user paths so Gradio can serve local media anywhere on the system
    existing_drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    allowed_system_paths = list(set(existing_drives + [str(Path.home()), str(Path.cwd())]))

    is_hf_space = bool(os.environ.get("SPACE_ID"))
    server_name = "0.0.0.0" if is_hf_space else "127.0.0.1"

    print(f"🚀 Launching Pipeline Tools web server on http://{server_name}:{port} ...\n", flush=True)
    try:
        demo.launch(
            server_name=server_name,
            server_port=port,
            show_error=True,
            allowed_paths=allowed_system_paths,
            theme=clean_theme,
            css=custom_css,
            head=get_custom_head()
        )

    except KeyboardInterrupt:
        clean_exit()
    except OSError as e:
        if "7860" in str(e) or "port" in str(e).lower():
            print(f"\n❌ ERROR: Port {port} is already in use!", flush=True)
            print(f"ℹ️ An instance of Pipeline Tools is already running on http://127.0.0.1:{port}", flush=True)
            print(f"💡 Open http://127.0.0.1:{port} in your browser, or stop the existing process to launch a new one.\n", flush=True)
            sys.exit(1)
        else:
            raise e


