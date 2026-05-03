"""
Euclid NISP instrument driver for SpectraPyle.

Implements the instrument interface required by the stacking pipeline:
:func:`readSpec`, :func:`readSpec_metadata`, :func:`prepare_stacking`,
and the internal :func:`_resolve_filepath` for per-release filename patterns.

Supported grisms: ``red``, ``blue``.
"""

import numpy as np
from astropy.io import fits
from astropy.table import Table
from pathlib import Path


# ---------------------------------------------------------------------------
# Filename resolution — Strategy pattern per data release
# ---------------------------------------------------------------------------

def _resolve_filepath(spectra_dir: Path, specid, grism: str, data_release: str) -> Path:
    """Return the first matching spectrum file path for the given specid/grism/release.

    Tries candidate filenames in order and returns the first that exists on disk.
    Filename patterns are data-release-specific (Q1, DR1, etc.).

    Parameters
    ----------
    spectra_dir : Path
        Directory containing spectrum files.
    specid : str or int
        Spectrum identifier.
    grism : str
        Grism name (``"red"``, ``"blue"``).
    data_release : str
        Data release identifier (e.g. ``"Q1"``, ``"DR1"``).

    Returns
    -------
    Path
        Path to the spectrum FITS file.

    Raises
    ------
    ValueError
        If data_release is not recognised.
    FileNotFoundError
        If no matching file exists on disk.
    """
    spectra_dir = Path(spectra_dir)

    if data_release == "Q1":
        candidates = [
            spectra_dir / f"{specid}.fits",
        ]

    elif data_release == "DR1":
        _PREFIX = {"red": "RGS", "blue": "BGS"}
        prefix = _PREFIX.get(grism)
        if prefix is None:
            raise ValueError(
                f"Grism '{grism}' has no DR1 prefix mapping. "
                f"Extend _PREFIX in _resolve_filepath()."
            )
        candidates = [
            spectra_dir / f"{specid}.fits",
            spectra_dir / f"{specid}_{grism}.fits",
            spectra_dir / f"SPECTRA_{prefix}-sedm {specid}.fits",
        ]

    else:
        raise ValueError(
            f"Unknown data_release '{data_release}'. "
            f"Please add its filename patterns to _resolve_filepath() in euclid.py "
            f"and document them in instruments_rules.json."
        )

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"No file found for specid={specid}, grism={grism}, release={data_release}.\n"
        "Tried:\n" + "\n".join(f"  {p}" for p in candidates)
    )


# ---------------------------------------------------------------------------
# Stacking preparation
# ---------------------------------------------------------------------------

def prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges):
    """Compute the wavelength grid bounds and the grism iteration list.

    The wavelength range is the union over all selected grisms, so stacking
    over blue+red covers the full range.

    Parameters
    ----------
    config : dict
        Flat config. Must contain ``'grisms'`` (List[str]), ``'wavelengths_blue'``,
        ``'wavelengths_red'``, ``'spectra_mode'``, ``'z_type'``.
    z_stacking : float
        Stacking redshift reference.
    zMin : float
        Minimum source redshift in sample.
    zMax : float
        Maximum source redshift in sample.
    lambda_edges : tuple[float, float] or None
        Rest-frame wavelength override (Å); if given, overrides per-grism bounds.

    Returns
    -------
    lbd_min : float
        Minimum wavelength for stacking (observed frame, Å).
    lbd_max : float
        Maximum wavelength for stacking (observed frame, Å).
    grismList : list of str
        List of grisms to iterate over.
    """
    grisms = config['grisms']

    _wl = {
        'blue': config['wavelengths_blue'],
        'red':  config['wavelengths_red'],
    }

    use_metadata = config.get('spectra_mode') == 'metadata path'

    if config['z_type'] == 'observed_frame':
        z_stacking = zMax = zMin = 0

    if lambda_edges is None:
        lbd_mins, lbd_maxs = [], []
        for g in grisms:
            if g not in _wl:
                raise ValueError(
                    f"Grism '{g}' is not in the wavelength map. "
                    f"Known grisms: {list(_wl)}."
                )
            lbd_mins.append(_wl[g][0] * (1 + z_stacking) / (1 + zMax))
            lbd_maxs.append(_wl[g][1] * (1 + z_stacking) / (1 + zMin))
        lbd_min = min(lbd_mins)
        lbd_max = max(lbd_maxs)
    else:
        lbd_min = lambda_edges[0] * (1 + z_stacking)
        lbd_max = lambda_edges[1] * (1 + z_stacking)

    grismList = ['metadata'] if use_metadata else list(grisms)

    return lbd_min, lbd_max, grismList


# ---------------------------------------------------------------------------
# Pixel bitmask helper
# ---------------------------------------------------------------------------

def int_to_bin7(mask_spec, list_bits_to_be_masked=None):
    """Convert integer bitmask to boolean array of flagged pixels.

    Parameters
    ----------
    mask_spec : array-like
        Array of integer bitmask values (one per pixel).
    list_bits_to_be_masked : list[int], optional
        Bit positions to flag as bad. Default: [0, 2, 6].

    Returns
    -------
    ndarray
        Boolean array; True where any flagged bit is set.

    Raises
    ------
    ValueError
        If mask_spec is not 1-D.
    """
    if list_bits_to_be_masked is None:
        list_bits_to_be_masked = [0, 2, 6]

    mask_spec = np.asarray(mask_spec)
    if mask_spec.ndim != 1:
        raise ValueError(f"mask_spec must be 1-D, got shape {mask_spec.shape}")

    masked_array = np.zeros(mask_spec.shape, dtype=bool)
    for k, n in enumerate(mask_spec):
        nb = f'{int(n):07b}'[::-1]
        list_bits = [i for i, b in enumerate(nb) if b == '1']
        masked_array[k] = any(x in list_bits_to_be_masked for x in list_bits)

    return masked_array


# ---------------------------------------------------------------------------
# Spectrum reading
# ---------------------------------------------------------------------------

def readSpec(config, specid, grism):
    """Read a single spectrum for the given grism.

    I/O paths are resolved per-grism from ``config['grism_io'][grism]``.

    Supported layouts
    ------------------
    **combined fits** (``spectra_datafile`` is set):
        a) One spectrum per HDU (name == specid or specid_grism)
        b) All spectra in a single 'SPECTRA' table HDU

    **individual fits** (``spectra_datafile`` is None):
        One FITS file per spectrum, path resolved by :func:`_resolve_filepath`
        according to ``data_release``.

    Parameters
    ----------
    config : dict
        Flat config dict with instrument, I/O, and quality settings.
    specid : str or int
        Spectrum identifier.
    grism : str
        Grism name (``"red"``, ``"blue"``).

    Returns
    -------
    lbd : ndarray
        Wavelength array (Å).
    flux : ndarray
        Flux array (erg/s/cm²/Å or arbitrary units).
    error : ndarray
        Error/variance array.
    """
    pixel_mask     = config['pixel_mask']
    n_min_dithers  = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']
    data_release   = config['data_release']

    # ---- per-grism I/O paths ----
    gcfg = config.get('grism_io', {}).get(grism, {})
    spectra_dir      = gcfg.get('spectra_dir')
    spectra_datafile = gcfg.get('spectra_datafile')

    # ---- combined FITS ----
    if spectra_datafile:
        filepath = Path(spectra_dir) / f"{spectra_datafile}.fits"
        with fits.open(filepath, memmap=True) as hdul:

            if str(specid) in hdul:
                table1 = Table(hdul[str(specid)].data)

            elif f"{specid}_{grism}" in hdul:
                table1 = Table(hdul[f"{specid}_{grism}"].data)

            elif 'SPECTRA' in hdul:
                data   = hdul['SPECTRA'].data
                id_col = config['ID_column_name']
                if id_col not in hdul['SPECTRA'].columns.names:
                    raise NameError(f"ID column '{id_col}' not found in HDU 'SPECTRA'")
                mask_id = data[id_col] == int(specid)
                if not np.any(mask_id):
                    raise NameError(f"Spectrum '{specid}' not found in {spectra_datafile}.fits")
                table1 = Table(data[mask_id])

            else:
                raise NameError(
                    f"Unrecognised FITS layout in {spectra_datafile}.fits. "
                    "Expected: per-spectrum HDUs or a 'SPECTRA' table HDU."
                )

    # ---- individual FITS ----
    else:
        if not spectra_dir:
            raise ValueError(
                f"spectra_dir is not configured for grism '{grism}'. "
                "Check config['grism_io']."
            )
        filepath = _resolve_filepath(
            spectra_dir=Path(spectra_dir),
            specid=specid,
            grism=grism,
            data_release=data_release,
        )
        with fits.open(filepath, memmap=True) as hdul:
            table1 = Table(hdul[1].data)

    # ---- extract columns ----
    flux  = ravel_array(_require_col(table1, ('flux',  'SIGNAL'),     'flux'),     'flux')
    error = ravel_array(_require_col(table1, ('error', 'VAR'),        'error'),    'error')
    lbd   = ravel_array(_require_col(table1, ('wave',  'WAVELENGTH'), 'wavelength'), 'wavelength')

    # sqrt(VAR) → std
    if 'VAR' in table1.colnames and 'error' not in table1.colnames:
        error = np.sqrt(error)

    mask  = _optional_col(table1, ('mask',  'MASK'))
    ndith = _optional_col(table1, ('NDith', 'NDITH'))
    if mask  is not None: mask  = ravel_array(mask,  'mask')
    if ndith is not None: ndith = ravel_array(ndith, 'ndith')

    # ---- quality filters ----
    if pixel_mask and mask is not None:
        bad = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
        flux[bad] = error[bad] = np.nan

    if n_min_dithers and n_min_dithers > 0 and ndith is not None:
        flux  = np.where(ndith < n_min_dithers, np.nan, flux)
        error = np.where(ndith < n_min_dithers, np.nan, error)

    if spectrum_edges is not None:
        flux[:spectrum_edges[0]]  = error[:spectrum_edges[0]]  = np.nan
        flux[spectrum_edges[1]:]  = error[spectrum_edges[1]:]  = np.nan

    return lbd, flux, error


def readSpec_metadata(config, specid, metadata_name, hdu_indx):
    """Read spectrum from a metadata-driven FITS path + HDU index.

    Parameters
    ----------
    config : dict
        Flat config dict with instrument and quality settings.
    specid : str or int
        Spectrum identifier (unused; included for interface compatibility).
    metadata_name : str
        Full path to FITS file.
    hdu_indx : int
        HDU index to read from.

    Returns
    -------
    lbd : ndarray
        Wavelength array (Å).
    flux : ndarray
        Flux array.
    error : ndarray
        Error array.
    """
    pixel_mask     = config['pixel_mask']
    n_min_dithers  = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']

    with fits.open(metadata_name) as hdul:
        data = hdul[hdu_indx].data

    lbd   = data.field('WAVELENGTH')
    flux  = data.field('SIGNAL')
    error = np.sqrt(data.field('VAR'))
    mask  = data.field('MASK')
    ndith = data.field('NDITH')

    if pixel_mask and mask is not None:
        bad = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
        flux[bad] = error[bad] = np.nan

    if n_min_dithers and n_min_dithers > 0 and ndith is not None:
        flux  = np.where(ndith < n_min_dithers, np.nan, flux)
        error = np.where(ndith < n_min_dithers, np.nan, error)

    if spectrum_edges is not None:
        flux[:spectrum_edges[0]]  = error[:spectrum_edges[0]]  = np.nan
        flux[spectrum_edges[1]:]  = error[spectrum_edges[1]:]  = np.nan

    return lbd, flux, error


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------

def _require_col(table, names, label):
    """Return first matching column; raise NameError if none found.

    Parameters
    ----------
    table : astropy.table.Table
        Table to search.
    names : tuple of str
        Column names to try in order.
    label : str
        Column label for error messages.

    Returns
    -------
    array-like
        Column data.

    Raises
    ------
    NameError
        If no matching column found.
    """
    for name in names:
        if name in table.colnames:
            return table[name]
    raise NameError(
        f"Required column not found (tried: {names}). "
        f"Available: {table.colnames}"
    )


def _optional_col(table, names):
    """Return first matching column or None if absent.

    Parameters
    ----------
    table : astropy.table.Table
        Table to search.
    names : tuple of str
        Column names to try in order.

    Returns
    -------
    array-like or None
        Column data if found, None otherwise.
    """
    for name in names:
        if name in table.colnames:
            return table[name]
    return None


def ravel_array(arr, name):
    """Ensure a spectrum array is strictly 1-D.

    Accepts 1-D of length N, or 2-D of shape (1, N).
    Raises ValueError for anything else.

    Parameters
    ----------
    arr : array-like
        Input array to validate.
    name : str
        Array name for error messages.

    Returns
    -------
    ndarray
        1-D array.

    Raises
    ------
    ValueError
        If array is not 1-D or of shape (1, N).
    """
    arr = np.asarray(arr)
    if arr.ndim == 2 and arr.shape[0] == 1:
        return arr[0]
    if arr.ndim != 1:
        raise ValueError(f"Unexpected {name} shape: {arr.shape}")
    return arr
