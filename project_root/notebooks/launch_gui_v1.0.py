from pathlib import Path
import sys
import socket
import contextlib

def find_free_port():
    """
    Find a free port on the current machine.
    """
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def launch_gui():
    """
    Launch a Voilà app for the build_config.ipynb notebook.
    Works in IPython/Datalab environment, with fallback to terminal.
    Automatically picks a free port if needed.
    """
    base = Path(__file__).resolve().parent
    notebook = base / "build_config.ipynb"

    try:
        # Try to import IPython to use %voila magic
        from IPython import get_ipython
        ip = get_ipython()
        if ip is None:
            raise RuntimeError("Not running inside IPython. Will fallback to subprocess.")

        # Load Voilà extension
        ip.run_line_magic("load_ext", "voila")

        # Launch the notebook as Voilà app
        ip.run_line_magic("voila", str(notebook))

    except Exception:
        import subprocess

        # Automatically pick a free port
        port = find_free_port()

        cmd = [
            sys.executable,
            "-m",
            "voila",
            str(notebook),
            "--strip_cell_tags=hide-input",
            "--theme=light",
            "--show_tracebacks=True",
            "--no-browser",
            "--ip=0.0.0.0",
            f"--port={port}",
        ]
        print(f"Launching Voilà on port {port}...")

        # Try to print a Datalab-accessible URL
        try:
            hostname = socket.gethostname()
            # Most Datalab setups proxy localhost ports as /proxy/{port}/
            print(f"Access the app via: https://{hostname}/proxy/{port}/")
        except Exception:
            print("Could not detect public hostname. Try localhost or the VM address.")

        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    launch_gui()