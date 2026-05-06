"""
Process-level singleton cache for combined FITS file handles.

This module maintains a cache of open FITS file handles for combined FITS files
(multiple spectra per file). It is designed to be initialized once per worker
process via multiprocessing.Pool's initializer parameter.

Each worker process has its own isolated cache — the module globals (_handles,
_indices) are NOT shared across processes. File handles are naturally
process-local and safe to use within a single process.
"""
import atexit
from pathlib import Path
from typing import Optional

from astropy.io import fits

_handles: dict = {}
_indices: dict = {}
_atexit_registered: bool = False


def init_file_handles(grism_paths: dict) -> None:
    """Open FITS file handles, deduplicating by resolved path."""
    global _atexit_registered
    path_to_hdul: dict = {}
    for grism, path in grism_paths.items():
        key = str(Path(path).resolve())
        if key not in path_to_hdul:
            path_to_hdul[key] = fits.open(path, memmap=True)
        _handles[grism] = path_to_hdul[key]
        _indices[grism] = None
    if not _atexit_registered:
        atexit.register(close_file_handles)
        _atexit_registered = True


def close_file_handles() -> None:
    """Close all open file handles, protecting against double-close."""
    seen: set = set()
    for hdul in _handles.values():
        hdul_id = id(hdul)
        if hdul_id not in seen:
            seen.add(hdul_id)
            try:
                hdul.close()
            except (OSError, RuntimeError, AttributeError):
                pass
    _handles.clear()
    _indices.clear()


def is_active(grism: str) -> bool:
    """Check if a cached handle exists for this grism."""
    return grism in _handles


def get_hdul(grism: str) -> Optional[fits.HDUList]:
    """Get the open FITS file handle for a grism, or None if not cached."""
    return _handles.get(grism)


def get_index(grism: str) -> Optional[dict]:
    """Get the built index for a grism, or None if not yet built."""
    return _indices.get(grism)


def set_index(grism: str, index: dict) -> None:
    """Store the built index for a grism."""
    _indices[grism] = index
