"""
Update the saved Jupyter host URL used by run_gui.py on remote deployments.

Run this script once when setting up SpectraPyle on a remote Jupyter server
(e.g. ESA Datalabs), or whenever the host URL changes.

Usage:
    python modify_host.py
"""

from pathlib import Path


def main():
    base = Path(__file__).resolve().parent
    host_file = base / ".launcher_host"

    current = host_file.read_text().strip() if host_file.exists() else "(not set)"

    print("SpectraPyle — Remote Host Configuration")
    print("=" * 42)
    print(f"Current host : {current}")
    print()
    print("Enter the full URL visible in your browser when JupyterLab is open.")
    print("Include the scheme and any path prefix, but NOT '/lab' or file paths.")
    print()
    print("  Datalabs example:")
    print("    https://euclid.dataspace.esa.int/data-analysis/apps/my-app")
    print()
    print("Leave empty to keep the current value. Ctrl+C to cancel.")
    print()

    try:
        new_host = input("New host URL: ").strip().rstrip("/")
    except KeyboardInterrupt:
        print("\n[SpectraPyle] Cancelled — no changes made.")
        return

    if not new_host:
        print("[SpectraPyle] No change made.")
        return

    host_file.write_text(new_host + "\n")
    print()
    print(f"[SpectraPyle] Saved  : {new_host}")
    print(f"[SpectraPyle] Launch : python run_gui.py")


if __name__ == "__main__":
    main()
