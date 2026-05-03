from pathlib import Path
import sys
import socket
import contextlib
import subprocess

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
    """
    base = Path(__file__).resolve().parent
    notebook = base / "make_config.ipynb"
    
    port = find_free_port()

    cmd = [
        sys.executable,
        "-m",
        "voila",
        str(notebook),
        "--strip_cell_tags=hide-input",
        "--theme=light",
        "--show_tracebacks=True",
    ]

    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    launch_gui()