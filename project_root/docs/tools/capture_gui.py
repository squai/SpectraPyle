#!/usr/bin/env python3
"""
Playwright-based screenshot capture script for the SpectraPyle GUI.

Launches the Voilà-backed Jupyter notebook (make_config.ipynb) and captures
screenshots of each major tab in the configuration interface.

Usage:
    python project_root/docs/tools/capture_gui.py

This script:
1. Launches Voilà on port 8867
2. Connects via Playwright (chromium)
3. Waits for ipywidgets to render
4. Captures 5 screenshots: launch, instrument, I/O, catalogue, stack parameters
5. Saves PNG files to project_root/docs/_static/screenshots/
6. Cleans up gracefully
"""

import subprocess
import time
import sys
import os
import signal
from pathlib import Path
from typing import Optional

try:
    from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("ERROR: playwright not installed. Install with: pip install playwright")
    sys.exit(1)


def _wait_for_server(url: str, max_retries: int = 30, initial_delay: float = 0.5) -> bool:
    """
    Wait for the Voilà server to be ready, with exponential backoff.

    Args:
        url: Server URL to check (e.g., "http://localhost:8867")
        max_retries: Maximum number of connection attempts
        initial_delay: Initial delay between attempts (seconds)

    Returns:
        True if server is ready, False if timeout.
    """
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print("ERROR: urllib not available")
        return False

    for attempt in range(max_retries):
        try:
            response = urllib.request.urlopen(url, timeout=2)
            if response.status == 200:
                print(f"✓ Server ready at {url}")
                return True
        except (urllib.error.URLError, OSError, Exception):
            pass

        delay = initial_delay * (2 ** min(attempt, 5))  # Cap exponential backoff
        print(f"  Waiting for server... (attempt {attempt + 1}/{max_retries}, next check in {delay:.1f}s)")
        time.sleep(delay)

    return False


def _launch_voila_server(notebook_path: Path, port: int = 8867) -> Optional[subprocess.Popen]:
    """
    Launch Voilà server in the background.

    Args:
        notebook_path: Path to make_config.ipynb
        port: Port to serve on

    Returns:
        Subprocess handle, or None if launch fails.
    """
    if not notebook_path.exists():
        print(f"ERROR: Notebook not found: {notebook_path}")
        return None

    cmd = [
        "voila",
        str(notebook_path),
        f"--port={port}",
        "--no-browser",
        "--strip_cell_tags=hide-input",
        "--theme=light",
    ]

    print(f"Launching Voilà: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"✓ Voilà process started (PID {proc.pid})")
        return proc
    except Exception as e:
        print(f"ERROR: Failed to launch Voilà: {e}")
        return None


def _terminate_gracefully(proc: Optional[subprocess.Popen], timeout: float = 5.0) -> None:
    """
    Terminate a subprocess gracefully: SIGTERM, then SIGKILL if needed.

    Args:
        proc: Subprocess handle
        timeout: Seconds to wait before force-kill
    """
    if proc is None:
        return

    try:
        print(f"Terminating Voilà process (PID {proc.pid})...")
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
            print("✓ Process terminated gracefully")
        except subprocess.TimeoutExpired:
            print(f"  Forcing kill after {timeout}s timeout...")
            proc.kill()
            proc.wait()
            print("✓ Process killed")
    except Exception as e:
        print(f"WARNING: Error terminating process: {e}")


def _capture_screenshots(
    page: Page,
    output_dir: Path,
) -> bool:
    """
    Capture screenshots of all major GUI sections.

    Args:
        page: Playwright page object
        output_dir: Directory to save PNG files

    Returns:
        True if successful, False otherwise.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Wait for the main notebook cell and ipywidgets to render
    print("Waiting for widgets to render...")
    try:
        page.wait_for_selector(".jupyter-widgets", timeout=10000)
        page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        print("WARNING: Widgets did not render in time, continuing anyway...")

    time.sleep(2)  # Extra stability wait

    screenshots = [
        ("gui_launch.png", None),  # Initial launch, no tab click needed
        ("gui_instrument.png", "Instrument (*)"),
        ("gui_io.png", "Input/Output (*)"),
        ("gui_catalogue.png", "Catalogue (*)"),
        ("gui_stack_params.png", "Stack Parameters"),
    ]

    for filename, tab_name in screenshots:
        try:
            if tab_name:
                print(f"Clicking tab: {tab_name}")
                # Find the tab button by partial text match
                try:
                    tab_button = page.locator(f"button:has-text('{tab_name}')")
                    if tab_button.count() > 0:
                        tab_button.first.click()
                    else:
                        # Fallback: try to find any button with partial match
                        buttons = page.locator("button")
                        found = False
                        for i in range(buttons.count()):
                            btn = buttons.nth(i)
                            text = btn.text_content()
                            if text and tab_name.split("(")[0].strip() in text:
                                btn.click()
                                found = True
                                break
                        if not found:
                            print(f"  WARNING: Could not find tab '{tab_name}', skipping click")
                except Exception as e:
                    print(f"  WARNING: Error clicking tab: {e}")

                time.sleep(2)  # Wait for tab content to render

            output_path = output_dir / filename
            print(f"Capturing: {filename}")
            page.screenshot(path=str(output_path), full_page=True)
            print(f"✓ Saved {output_path}")

        except Exception as e:
            print(f"ERROR: Failed to capture {filename}: {e}")
            return False

    return True


def main():
    """Main entry point: launch server, capture screenshots, cleanup."""
    project_root = Path(__file__).parent.parent.parent
    notebook_path = project_root / "notebooks" / "make_config.ipynb"
    output_dir = project_root / "docs" / "_static" / "screenshots"

    voila_proc: Optional[subprocess.Popen] = None

    try:
        # Launch Voilà server
        voila_proc = _launch_voila_server(notebook_path, port=8867)
        if voila_proc is None:
            sys.exit(1)

        # Wait for server to be ready
        server_url = "http://localhost:8867"
        if not _wait_for_server(server_url):
            print(f"ERROR: Server did not start within timeout at {server_url}")
            sys.exit(1)

        # Connect with Playwright
        print("Connecting to server with Playwright...")
        with sync_playwright() as p:
            browser: Browser = p.chromium.launch(headless=True)
            try:
                page: Page = browser.new_page()
                page.set_viewport_size({"width": 1200, "height": 800})

                print(f"Navigating to {server_url}")
                page.goto(server_url, wait_until="networkidle")

                # Capture screenshots
                success = _capture_screenshots(page, output_dir)

                if success:
                    print("\n✓ All screenshots captured successfully!")
                    return 0
                else:
                    print("\nERROR: Some screenshots failed to capture")
                    return 1

            finally:
                browser.close()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        _terminate_gracefully(voila_proc)


if __name__ == "__main__":
    sys.exit(main())
