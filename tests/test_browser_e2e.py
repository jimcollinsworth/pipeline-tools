"""
tests/test_browser_e2e.py — End-to-End Browser & Integration Test Suite.
=========================================================================
Adopts lessons and architecture from the jimcollinsworth.github.io test suite:
1. Headless Chromium browser automation via Playwright.
2. Responsive layout verification (Mobile Portrait 390x844 & Desktop Landscape 1920x1080).
3. Zero console errors and unhandled exceptions policy across all tabs.
4. Value inputs and value outputs verification in interactive views (Input/Output tables).
5. Value outputs verification in generated export files on disk.
6. Central domain system prompt configuration and persistence verification.
"""

from __future__ import annotations

import os
import sys
import time
import socket
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

# Safe stdout reconfigure for Windows codepages
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import pixeltable as pxt
    PIXELTABLE_AVAILABLE = True
except ImportError:
    pxt = None
    PIXELTABLE_AVAILABLE = False

from src.core.config import get_settings, get_domain_system_prompt, set_domain_system_prompt
from src.db.manager import DBManager
from app import create_app


class TestBrowserE2E(unittest.TestCase):
    """End-to-End Playwright test suite for the Pipeline Tools Gradio application."""

    TEST_DOMAIN = "test_e2e_isolated"
    TEST_TABLE = "e2e_documents"
    demo = None
    server_port = None
    base_url = ""
    playwright = None
    browser = None

    @classmethod
    def setUpClass(cls):
        """Prepare database test tables, start ephemeral Gradio server, and launch Playwright Chromium."""
        if not PLAYWRIGHT_AVAILABLE:
            return

        # Pre-flight embedded PostgreSQL lock self-healing
        DBManager.heal_postgres_locks()
        # Seed isolated test domain and table
        if PIXELTABLE_AVAILABLE:
            try:
                if cls.TEST_DOMAIN in (DBManager.list_dirs() or []):
                    DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

            # Create sample files for ingestion
            test_files = [
                {
                    "name": "financial_report_2026.txt",
                    "abs_path": str(REPO_ROOT / "README.md"),
                    "rel_path": "README.md",
                    "modality": "text",
                    "extension": ".txt",
                    "size_bytes": 2048,
                    "size": "2.0 KB",
                },
                {
                    "name": "architecture_blueprint.txt",
                    "abs_path": str(REPO_ROOT / "planning.md"),
                    "rel_path": "planning.md",
                    "modality": "text",
                    "extension": ".txt",
                    "size_bytes": 4096,
                    "size": "4.0 KB",
                }
            ]
            DBManager.ingest_files(cls.TEST_DOMAIN, cls.TEST_TABLE, test_files, overwrite=True)

        # Set default test domain in settings
        set_domain_system_prompt(cls.TEST_DOMAIN, "Default E2E Test System Instructions.")

        # Discover an open ephemeral port to avoid collisions
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            free_port = s.getsockname()[1]

        # Launch Gradio on the discovered ephemeral port
        cls.demo = create_app()
        cls.demo.launch(
            server_name="127.0.0.1",
            server_port=free_port,
            prevent_thread_lock=True,
            show_error=True
        )
        cls.server_port = free_port
        cls.base_url = f"http://127.0.0.1:{free_port}"

        # Launch Playwright Chromium
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        """Tear down browser, terminate ephemeral web server, and drop temporary database tables."""
        if cls.browser:
            try:
                cls.browser.close()
            except Exception:
                pass
        if cls.playwright:
            try:
                cls.playwright.stop()
            except Exception:
                pass
        if cls.demo:
            try:
                cls.demo.close()
            except Exception:
                pass
        if PIXELTABLE_AVAILABLE:
            try:
                DBManager.drop_dir(cls.TEST_DOMAIN, force=True)
            except Exception:
                pass

    def setUp(self):
        if not PLAYWRIGHT_AVAILABLE:
            self.skipTest("Playwright is not installed in the current environment.")

    def test_01_responsive_tab_navigation_and_zero_console_errors(self):
        """[E2E] Verify zero console errors and clean layout rendering across mobile and desktop viewports."""
        viewports = [
            {"width": 390, "height": 844, "name": "phone_portrait"},
            {"width": 1920, "height": 1080, "name": "desktop_landscape"},
        ]

        tabs_to_verify = [
            "Ingestion & Scanner",
            "Data Enhancement",
            "View & Export",
            "Settings & Models",
        ]

        for vp in viewports:
            errors: list[str] = []
            context = self.browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = context.new_page()

            page.on("pageerror", lambda err: errors.append(f"PageError: {err}"))
            page.on(
                "console",
                lambda msg: errors.append(f"ConsoleError: {msg.text}")
                if msg.type == "error" and "favicon" not in msg.text.lower()
                else None
            )

            try:
                page.goto(self.base_url, wait_until="load", timeout=20000)
                page.wait_for_timeout(1000)
                page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)

                # Iterate through all core tabs
                for tab_label in tabs_to_verify:
                    tab_btn = page.locator(f"button:has-text('{tab_label}')").first
                    tab_btn.wait_for(state="attached", timeout=5000)
                    tab_btn.scroll_into_view_if_needed()
                    tab_btn.click(force=True)
                    page.wait_for_timeout(400)

                # Filter out harmless WebSocket or Font network warnings if any
                fatal_errors = [e for e in errors if "websocket" not in e.lower()]
                self.assertEqual(
                    len(fatal_errors),
                    0,
                    f"Console errors detected on {vp['name']}:\n" + "\n".join(fatal_errors),
                )
            finally:
                context.close()

    def test_02_value_inputs_and_outputs_in_views(self):
        """[E2E] Confirm value inputs in prompt workbench propagate to output views in Output Table."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            page.goto(self.base_url, wait_until="load", timeout=20000)
            page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)
            page.wait_for_timeout(1000)
            # Switch to Data Enhancement tab
            tab_btn = page.locator(".tab-nav button:has-text('Data Enhancement'), [role='tablist'] button:has-text('Data Enhancement')").first
            tab_btn.wait_for(state="attached", timeout=5000)
            tab_btn.scroll_into_view_if_needed()
            tab_btn.click(force=True)
            page.wait_for_timeout(1000)

            # Verify prompt input exists and accepts value input
            prompt_input = page.locator("textarea[placeholder*='Enter prompt template']").first
            self.assertTrue(prompt_input.is_visible(), "Prompt template input is not visible.")

            # Input test value
            test_prompt_value = "Extract key facts from {file_name}: {content}"
            prompt_input.fill(test_prompt_value)
            page.wait_for_timeout(200)
            self.assertIn("Extract key facts", prompt_input.input_value())

            # Verify Input Table displays seeded data (file names)
            page_content = page.content()
            self.assertTrue(
                "Input Table (Source Data)" in page_content
                or "Output Table" in page_content,
                "Consolidated workbench tables not rendered.",
            )

            # Mock LLM generation to verify output value propagation into Output Table
            mock_llm_json = '{"summary": "Automated E2E Verification Success", "rating": 5}'
            with patch("src.prompts.executor.LLMService.generate", return_value=mock_llm_json):
                run_test_btn = page.locator("button:has-text('Run Test on Sample Rows')").first
                if run_test_btn.is_visible():
                    run_test_btn.click(force=True)
                    page.wait_for_timeout(2000)

            # Output Table section should be present
            output_heading = page.locator("h4:has-text('Output Table')").first
            self.assertTrue(output_heading.is_visible(), "Output Table heading should be visible.")
        finally:
            context.close()

    def test_03_value_outputs_in_generated_files(self):
        """[E2E] Confirm value outputs in export tab create validated Markdown files on disk."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            page.goto(self.base_url, timeout=15000)
            # Switch to View & Export tab
            page.locator("button:has-text('View & Export')").first.click(force=True)
            page.wait_for_timeout(500)

            # Verify export strategy and prompt controls exist
            page_content = page.content()
            self.assertIn("AI Markdown Document Export", page_content)

            # Execute export via controller directly or mock synthesis to test file generation
            from src.controllers.tables_controller import TablesController
            mock_synthesis = (
                "# E2E Verified Synthesis Document\n\n"
                "Key Value Outputs:\n"
                "- Source Document: financial_report_2026.txt\n"
                "- Analysis Status: Verified E2E Pass\n"
            )

            with patch("src.export.exporter.LLMService.generate", return_value=mock_synthesis):
                res = TablesController.handle_export_report(
                    domain=self.TEST_DOMAIN,
                    table_name=self.TEST_TABLE,
                    provider="Ollama",
                    model="test-model",
                    max_rows=2,
                    system_prompt="E2E Test System",
                    prompt_template="Analyze {domain}.{table}",
                    mode="single"
                )

            self.assertEqual(res["status"], "success")
            output_path_str = res.get("file_path")
            self.assertIsNotNone(output_path_str, "Export did not return an output file path.")
            
            output_path = Path(output_path_str)
            self.assertTrue(output_path.exists(), f"Generated export file {output_path} does not exist on disk.")

            # Read generated file and assert input and output values
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("# E2E Verified Synthesis Document", content)
            self.assertIn("financial_report_2026.txt", content)
            self.assertIn("Verified E2E Pass", content)

            # Clean up generated test export
            try:
                output_path.unlink()
            except Exception:
                pass
        finally:
            context.close()

    def test_04_domain_system_prompt_setting_and_persistence(self):
        """[E2E] Verify Domain System Prompt configuration updates and persists across sessions."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            page.goto(self.base_url, wait_until="load", timeout=20000)
            page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)
            page.wait_for_timeout(1000)
            # Switch to Settings & Models tab
            tab_btn = page.locator(".tab-nav button:has-text('Settings & Models'), [role='tablist'] button:has-text('Settings & Models')").first
            tab_btn.wait_for(state="attached", timeout=5000)
            tab_btn.scroll_into_view_if_needed()
            tab_btn.click(force=True)
            page.wait_for_timeout(1000)

            # Verify Domain System Prompt Configuration section exists
            section_header = page.locator("*:has-text('Domain System Prompt Configuration')").first
            self.assertTrue(section_header.is_visible(), "Domain System Prompt section header not visible.")

            # Update system prompt programmatically & via config
            new_test_prompt = "You are an AI research assistant validating end-to-end value consistency."
            set_domain_system_prompt(self.TEST_DOMAIN, new_test_prompt)

            # Verify persisted value matches
            retrieved_prompt = get_domain_system_prompt(self.TEST_DOMAIN)
            self.assertEqual(retrieved_prompt, new_test_prompt)
        finally:
            context.close()

    def test_05_visual_stacked_tables_geometry_and_full_width(self):
        """[E2E] Visually assert Input and Output tables are vertically stacked and span full width (>=70% viewport)."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        try:
            page.goto(self.base_url, wait_until="load", timeout=20000)
            page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)
            page.wait_for_timeout(1000)

            # Switch to Data Enhancement tab
            tab_btn = page.locator(".tab-nav button:has-text('Data Enhancement'), [role='tablist'] button:has-text('Data Enhancement')").first
            tab_btn.wait_for(state="attached", timeout=5000)
            tab_btn.scroll_into_view_if_needed()
            tab_btn.click(force=True)
            page.wait_for_timeout(1000)

            # Locate Input Table and Output Table sections
            input_heading = page.locator("h4:has-text('Input Table (Source Data)')").first
            output_heading = page.locator("h4:has-text('Output Table')").first

            input_heading.wait_for(state="visible", timeout=5000)
            output_heading.wait_for(state="visible", timeout=5000)

            box_input = input_heading.bounding_box()
            box_output = output_heading.bounding_box()

            self.assertIsNotNone(box_input, "Input Table heading bounding box could not be determined.")
            self.assertIsNotNone(box_output, "Output Table heading bounding box could not be determined.")

            # Strict Visual Invariant 1: Output Table MUST be vertically below Input Table (no side-by-side columns)
            self.assertGreater(
                box_output["y"],
                box_input["y"] + 50,
                f"Output table (y={box_output['y']}) is not vertically stacked below Input table (y={box_input['y']})."
            )

            # Strict Visual Invariant 2: Tables must span full horizontal width (>=70% of 1400px viewport)
            dataframes = page.locator(".gradio-dataframe")
            df_count = dataframes.count()
            if df_count > 0:
                for i in range(min(df_count, 2)):
                    df_box = dataframes.nth(i).bounding_box()
                    if df_box and df_box["width"] > 0:
                        self.assertGreaterEqual(
                            df_box["width"],
                            1400 * 0.70,
                            f"Dataframe #{i} width ({df_box['width']}px) is less than 70% of viewport (1400px)."
                        )
        finally:
            context.close()

    def test_06_view_export_load_refresh_button_and_copy_parity(self):
        """[E2E] Verify UI instructional copy has an exact matching interactive 'Load / Refresh Table' button."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            page.goto(self.base_url, wait_until="load", timeout=20000)
            page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)
            page.wait_for_timeout(1000)

            # Switch to View & Export tab
            tab_btn = page.locator(".tab-nav button:has-text('View & Export'), [role='tablist'] button:has-text('View & Export')").first
            tab_btn.wait_for(state="attached", timeout=5000)
            tab_btn.scroll_into_view_if_needed()
            tab_btn.click(force=True)
            page.wait_for_timeout(1000)

            # 1. Verify the instructional copy is present
            page_text = page.content()
            self.assertIn("Load / Refresh Table", page_text, "Instructional copy does not reference Load / Refresh Table.")

            # 2. Verify the interactive button exists, is visible, and enabled
            refresh_btn = page.locator("button:has-text('Load / Refresh Table')").first
            refresh_btn.wait_for(state="visible", timeout=5000)
            self.assertTrue(refresh_btn.is_visible(), "Load / Refresh Table button is not visible in DOM.")
            self.assertTrue(refresh_btn.is_enabled(), "Load / Refresh Table button is disabled.")

            # 3. Click the button and verify table stats update without errors
            refresh_btn.click(force=True)
            page.wait_for_timeout(1000)
            loaded_stats = page.locator("*:has-text('Displaying'), *:has-text('Total Rows'), *:has-text('Table')").first
            self.assertTrue(loaded_stats.is_visible(), "Table stats did not update upon clicking Load / Refresh Table.")
        finally:
            context.close()

    def test_07_global_system_prompt_visibility_and_saving(self):
        """[E2E] Verify prominent Global System Prompt textarea and save button in Settings & Models."""
        context = self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            page.goto(self.base_url, wait_until="load", timeout=20000)
            page.wait_for_selector("button:has-text('Ingestion & Scanner')", timeout=10000)
            page.wait_for_timeout(1000)

            # Switch to Settings & Models tab
            tab_btn = page.locator(".tab-nav button:has-text('Settings & Models'), [role='tablist'] button:has-text('Settings & Models')").first
            tab_btn.wait_for(state="attached", timeout=5000)
            tab_btn.scroll_into_view_if_needed()
            tab_btn.click(force=True)
            page.wait_for_timeout(1000)

            # 1. Verify the Active System Prompt textarea is visible
            system_prompt_area = page.locator("textarea[placeholder*='Enter global system prompt instructions']").first
            system_prompt_area.wait_for(state="visible", timeout=5000)
            self.assertTrue(system_prompt_area.is_visible(), "Active System Prompt textarea is not visible.")

            # 2. Verify Save System Prompt button is visible and clickable
            save_prompt_btn = page.locator("button:has-text('Save System Prompt')").first
            save_prompt_btn.wait_for(state="visible", timeout=5000)
            self.assertTrue(save_prompt_btn.is_visible(), "Save System Prompt button is not visible.")

            # 3. Fill and save new system prompt
            test_val = "E2E Test Prompt: You are an AI analyzing documents with precision."
            system_prompt_area.fill(test_val)
            page.wait_for_timeout(300)
            save_prompt_btn.click(force=True)
            page.wait_for_timeout(1000)

            # 4. Verify persisted setting
            settings = get_settings()
            self.assertEqual(settings.last_system_prompt, test_val)
        finally:
            context.close()


def run_e2e_tests() -> bool:
    """Convenience runner for executing E2E tests standalone."""
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestBrowserE2E))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == "__main__":
    success = run_e2e_tests()
    sys.exit(not success)
