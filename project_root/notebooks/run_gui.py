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


def generate_launcher_notebook(source_nb: Path, launcher_nb: Path) -> None:
    """Create gui_launcher.ipynb from make_config.ipynb with all code cells collapsed."""
    with open(source_nb) as f:
        nb = json.load(f)
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell.setdefault("metadata", {}).setdefault("jupyter", {})["source_hidden"] = True
    with open(launcher_nb, "w") as f:
        json.dump(nb, f, indent=1)


def get_jupyter_server_info():
    """Return (base_url, root_dir) from the running Jupyter server, or (None, None)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "jupyter", "server", "list", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            servers = json.loads(result.stdout)
            if servers:
                s = servers[0]
                base = s.get("base_url", "/")
                if not base.endswith("/"):
                    base += "/"
                return base, s.get("root_dir", "")
    except Exception:
        pass
    return None, None


def load_saved_host(base: Path) -> str:
    """Read saved host URL from .launcher_host, if present."""
    host_file = base / ".launcher_host"
    if host_file.exists():
        return host_file.read_text().strip().rstrip("/")
    return ""


def launch_gui():
    """
    Launch the SpectraPyle configuration GUI.

    Generates gui_launcher.ipynb (all code cells hidden) from make_config.ipynb, then:
    - Remote Jupyter (e.g. Datalabs): prints a JupyterLab URL to open gui_launcher.ipynb.
      Run modify_host.py once to configure (and update) the host URL.
    - Local machine: starts Voilà on gui_launcher.ipynb, opens browser automatically.

    Remote mode is triggered by JUPYTERHUB env vars, a non-root Jupyter base_url,
    or a saved host in .launcher_host. SPECTRAPYLE_HOST env var overrides all.
    """
    base = Path(__file__).resolve().parent
    source_nb = base / "make_config.ipynb"
    launcher_nb = base / "gui_launcher.ipynb"

    print("[SpectraPyle] Preparing gui_launcher.ipynb ...")
    generate_launcher_notebook(source_nb, launcher_nb)

    # Resolve host: env var > saved file > empty
    spectrapyle_host = (
        os.environ.get("SPECTRAPYLE_HOST", "").rstrip("/")
        or load_saved_host(base)
    )
    server_url = os.environ.get("JUPYTERHUB_SERVER_URL", "").rstrip("/")
    service_prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "")

    base_url, root_dir = get_jupyter_server_info()

    is_remote = bool(
        spectrapyle_host
        or server_url
        or service_prefix
        or (base_url and base_url != "/")
    )

    if is_remote:
        # Build the JupyterLab lab/tree/... URL that opens gui_launcher.ipynb directly
        if server_url:
            lab_base = server_url.rstrip("/") + "/"
        elif service_prefix:
            pfx = service_prefix if service_prefix.endswith("/") else service_prefix + "/"
            lab_base = f"{spectrapyle_host}{pfx}" if spectrapyle_host else pfx
        else:
            if spectrapyle_host and base_url:
                lab_base = f"{spectrapyle_host}{base_url}"
            elif base_url:
                lab_base = base_url
            else:
                lab_base = ""

        lab_file_path = None
        if root_dir:
            try:
                lab_file_path = str(launcher_nb.relative_to(Path(root_dir)))
            except ValueError:
                pass

        print("[SpectraPyle] gui_launcher.ipynb is ready.")
        if lab_base and lab_file_path:
            url = f"{lab_base}lab/tree/{lab_file_path}"
            print(f"[SpectraPyle] Open in browser : {url}")
            print(f"[SpectraPyle] Then            : Kernel → Restart Kernel and Run All Cells")
        else:
            print("[SpectraPyle] Open notebooks/gui_launcher.ipynb in JupyterLab.")
            print("[SpectraPyle] Then: Kernel → Restart Kernel and Run All Cells")
        print("[SpectraPyle] Wrong URL?      : python modify_host.py")

    else:
        # Local — Voilà gives a clean browser tab with no notebook chrome
        port = find_free_port()
        url = f"http://localhost:{port}/"
        print(f"[SpectraPyle] GUI starting on port {port}")
        print(f"[SpectraPyle] Open in browser: {url}")
        print(f"[SpectraPyle] On a remote Jupyter server instead? Run: python modify_host.py")

        def _open_browser():
            time.sleep(2)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

        subprocess.run(
            [
                sys.executable, "-m", "voila",
                str(launcher_nb),
                f"--port={port}",
                "--no-browser",
                "--theme=light",
                "--show_tracebacks=True",
            ],
            check=True,
        )


if __name__ == "__main__":
    launch_gui()
