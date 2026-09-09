"""Local convenience launcher for the SpectraPyle GUI.

Run from a terminal with:

    python run_gui.py

This starts Voilà on ``gui_launcher.ipynb`` and opens the GUI
in the default web browser.
"""

from pathlib import Path
import contextlib
import socket
import subprocess
import sys
import threading
import time
import webbrowser


def find_free_port() -> int:
    """Return an available local TCP port."""
    with contextlib.closing(
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def launch_gui() -> None:
    """Launch the SpectraPyle GUI locally with Voilà."""
    launcher = Path(__file__).resolve().parent / "gui_launcher.ipynb"

    if not launcher.exists():
        raise FileNotFoundError(
            f"Could not find the GUI launcher notebook:\n{launcher}"
        )

    # Check that Voilà is available in the current Python environment.
    try:
        subprocess.run(
            [sys.executable, "-m", "voila", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            "Voilà is not available in the current environment. "
            "Install SpectraPyle with the notebook dependencies first."
        ) from exc

    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"

    print(f"[SpectraPyle] Starting GUI: {url}")
    print("[SpectraPyle] Press Ctrl+C to stop the server.")

    def open_browser() -> None:
        time.sleep(2)
        webbrowser.open(url)

    threading.Thread(
        target=open_browser,
        daemon=True,
    ).start()

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "voila",
                str(launcher),
                f"--port={port}",
                "--no-browser",
                "--theme=light",
                "--show_tracebacks=True",
            ],
            check=True,
        )
    except KeyboardInterrupt:
        print("\n[SpectraPyle] GUI stopped.")


if __name__ == "__main__":
    launch_gui()