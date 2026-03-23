import subprocess
import sys
from pathlib import Path


def launch_gui():

    base = Path(__file__).resolve().parent
    notebook = base / "build_config.ipynb"

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

# from terminal: python path-to-file/launch_gui.py