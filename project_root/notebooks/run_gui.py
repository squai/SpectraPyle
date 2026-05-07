from pathlib import Path
import os
import sys
import socket
import contextlib
import subprocess
import webbrowser
import time

def find_free_port():
    """
    Find a free port on the current machine.
    """
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def launch_gui():
    """
    Launch a Voilà app for the make_config.ipynb notebook.
    On JupyterHub (Datalabs), prints the JupyterHub proxy URL.
    On local machines, opens the browser automatically.
    """
    base = Path(__file__).resolve().parent
    notebook = base / "make_config.ipynb"

    port = find_free_port()

    service_prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "")
    is_jupyterhub = bool(service_prefix)

    if is_jupyterhub:
        url = f"{service_prefix}proxy/{port}/"
    else:
        url = f"http://localhost:{port}/"

    print(f"[SpectraPyle] GUI starting on port {port}")
    print(f"[SpectraPyle] Open in browser: {url}")

    cmd = [
        sys.executable,
        "-m",
        "voila",
        str(notebook),
        f"--port={port}",
        "--no-browser",
        "--theme=light",
        "--show_tracebacks=True",
    ]

    # On local machines, open browser automatically after a short delay
    # to allow Voilà to start
    if not is_jupyterhub:
        def open_browser():
            time.sleep(2)
            webbrowser.open(url)

        import threading
        thread = threading.Thread(target=open_browser, daemon=True)
        thread.start()

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    launch_gui()