"""
Capture Screenshots for All Tabs Across Key Viewports (Forced Tab Click)
"""
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTDIR = Path("screenshots/tabs")
OUTDIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR = Path(r"C:\Users\jimco\.gemini\antigravity\brain\df01f286-4b7e-4f94-965f-1585188883e5\screenshots")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

TABS = [
    ("Data Enhancement", "data_enhancement"),
    ("Ingestion & Scanner", "ingest_scanner"),
    ("View & Export", "view_export"),
    ("Settings & Models", "settings_models"),
]

VIEWPORTS = [
    ("desktop", "landscape", 1920, 1080),
    ("laptop", "landscape", 1366, 768),
    ("tablet", "portrait", 820, 1180),
    ("phone", "portrait", 390, 844),
    ("phone", "landscape", 844, 390),
]

captured = []

with sync_playwright() as p:
    browser = p.chromium.launch()

    for dev, orient, w, h in VIEWPORTS:
        context = browser.new_context(viewport={"width": w, "height": h}, color_scheme="light")
        page = context.new_page()
        page.goto("http://127.0.0.1:7860", wait_until="load", timeout=30000)
        page.wait_for_timeout(1500)

        for tab_label, tab_slug in TABS:
            try:
                # Force click the tab
                tab_btn = page.locator(f'button[role="tab"]:has-text("{tab_label}")').first
                if tab_btn.count() > 0:
                    tab_btn.click(force=True)
                    page.wait_for_timeout(800)

                filename = f"{tab_slug}_{dev}_{orient}_{w}x{h}.png"
                dest = OUTDIR / filename
                page.screenshot(path=str(dest), full_page=True)

                artifact_dest = ARTIFACTS_DIR / filename
                shutil.copy2(dest, artifact_dest)

                captured.append({
                    "tab": tab_label,
                    "device": dev,
                    "orientation": orient,
                    "dim": f"{w}x{h}",
                    "file": filename,
                    "artifact_path": str(artifact_dest).replace("\\", "/")
                })
                print(f"  [OK] {tab_label:<20} | {dev:<8} {orient:<10} ({w}x{h}) -> {filename}")
            except Exception as e:
                print(f"  [FAIL] {tab_label} {dev}: {e}")

        context.close()

    browser.close()

print(f"\nCaptured {len(captured)} tab screenshots successfully!")
