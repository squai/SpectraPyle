from pathlib import Path
import json
import os
import sys
import socket
import contextlib
import subprocess
import threading
import time
import webbrowser


def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def get_server_base_path():
    """Return base_url path from the running Jupyter server, e.g. '/data-analysis/apps/unknown/'."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "jupyter", "server", "list", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            servers = json.loads(result.stdout)
            if servers:
                base = servers[0].get("base_url", "/")
                return base if base.endswith("/") else base + "/"
    except Exception:
        pass
    return None


def launch_gui():
    """
    Launch a Voilà app for the make_config.ipynb notebook.

    URL detection priority:
    1. JUPYTERHUB_SERVER_URL         — standard JupyterHub (full URL)
    2. JUPYTERHUB_SERVICE_PREFIX     — older JupyterHub
    3. SPECTRAPYLE_HOST + jupyter server list — non-standard remote Jupyter (e.g. Datalabs)
    4. jupyter server list alone     — relative path + hint to set SPECTRAPYLE_HOST
    5. localhost                     — local machine (also opens browser automatically)
    """
    base = Path(__file__).resolve().parent
    notebook = base / "make_config.ipynb"
    port = find_free_port()

    spectrapyle_host = os.environ.get("SPECTRAPYLE_HOST", "").rstrip("/")
    server_url = os.environ.get("JUPYTERHUB_SERVER_URL", "").rstrip("/")
    service_prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "")
    is_remote = True
    url = None
    hints = []

    if server_url:
        url = f"{server_url}/proxy/{port}/"

    elif service_prefix:
        from urllib.parse import urlparse
        oauth_url = os.environ.get("JUPYTERHUB_OAUTH_CALLBACK_URL", "")
        if oauth_url:
            parsed = urlparse(oauth_url)
            url = f"{parsed.scheme}://{parsed.netloc}{service_prefix}proxy/{port}/"
        else:
            url = f"{service_prefix}proxy/{port}/"

    else:
        base_path = get_server_base_path()
        if spectrapyle_host:
            # Stable host + dynamically detected session path (e.g. Datalabs)
            path = base_path if (base_path and base_path != "/") else "/"
            url = f"{spectrapyle_host}{path}proxy/{port}/"
        elif base_path and base_path != "/":
            url = f"{base_path}proxy/{port}/"
            hints = [
                f"Proxy path (relative): {url}",
                "For a clickable URL set once in your terminal:",
                "  export SPECTRAPYLE_HOST=https://<your-host>",
                "(the session path is detected automatically)"
            ]
        else:
            url = f"http://localhost:{port}/"
            is_remote = False

    for hint in hints:
        print(f"[SpectraPyle] {hint}")

    print(f"[SpectraPyle] GUI starting on port {port}")
    print(f"[SpectraPyle] Open in browser: {url}")

    cmd = [
        sys.executable, "-m", "voila",
        str(notebook),
        f"--port={port}",
        "--no-browser",
        "--theme=light",
        "--show_tracebacks=True",
    ]

    if not is_remote:
        def _open_browser():
            time.sleep(2)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    launch_gui()