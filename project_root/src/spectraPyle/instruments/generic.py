"""
Generic FITS instrument driver for SpectraPyle.

Supports standard astronomical FITS formats without instrument-specific assumptions.
Reads from binary table columns (with fallback to WCS header) and enables rapid
stacking analysis for any single-grism spectrograph.

Implements the instrument interface required by the stacking pipeline:
:func:`readSpec`, :func:`readSpec_metadata`, and :func:`prepare_stacking`.

Supported features:
- Column aliases: wavelength, flux, error (with automatic fallback)
- Wavelength reconstruction: binary table columns OR WCS header (linear/log/SDSS-style COEFF)
- Flux scale factor: auto-read from FITS header (BSCALE, FLUXSCAL, FLUX_SCALE)
- Spectra mode: individual FITS or combined FITS
"""

import numpy as np
from astropy.io import fits
from astropy.table import Table
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_pixel_size_warning_logged = False


def _read_wavelength_from_table(table):
    """Extract wavelength column from binary table.

    Tries column names in order: 'wavelength' -> 'WAVE' -> 'LAMBDA'.

    Parameters
    ----------
    table : astropy.table.Table
        Binary table to search.

    Returns
    -------
    ndarray or None
        Wavelength array if found, None otherwise.
    """
    for col_name in ['wavelength', 'WAVE', 'LAMBDA']:
        if col_name in table.colnames:
            return np.asarray(table[col_name])
    return None


def _read_wavelength_from_header(header, naxis1):
    """Reconstruct wavelength array from FITS header keywords.

    Tries three formats in order:
    1. SDSS-style: COEFF0 + COEFF1 * arange (log-spaced)
    2. Log-linear WCS: CRVAL1/CDELT1 with CTYPE1 containing 'LOG'
    3. Linear WCS (default): CRVAL1 + CDELT1 * (arange - (CRPIX1 - 1))

    Parameters
    ----------
    header : astropy.io.fits.Header
        FITS primary header.
    naxis1 : int
        Number of spectral elements.

    Returns
    -------
    ndarray
        Wavelength array (Angstroms).

    Raises
    ------
    ValueError
        If required WCS keywords are missing.
    """
    # SDSS-style coefficients
    if 'COEFF0' in header and 'COEFF1' in header:
        coeff0 = float(header['COEFF0'])
        coeff1 = float(header['COEFF1'])
        lbd = 10.0 ** (coeff0 + coeff1 * np.arange(naxis1))
        return lbd

    # Log-linear WCS
    ctype1 = header.get('CTYPE1', '').upper()
    if 'LOG' in ctype1:
        try:
            crval1 = float(header['CRVAL1'])
            cdelt1 = float(header['CDELT1'])
            crpix1 = float(header.get('CRPIX1', 1.0))
            lbd = 10.0 ** (crval1 + (np.arange(naxis1) - (crpix1 - 1)) * cdelt1)
            return lbd
        except KeyError as e:
            raise ValueError(f"Log-linear WCS: missing keyword {e}")

    # Linear WCS (default)
    try:
        crval1 = float(header['CRVAL1'])
        cdelt1 = float(header['CDELT1'])
        crpix1 = float(header.get('CRPIX1', 1.0))
        lbd = crval1 + (np.arange(naxis1) - (crpix1 - 1)) * cdelt1
        return lbd
    except KeyError as e:
        raise ValueError(f"Linear WCS: missing keyword {e}")


def _read_scale_factor(header):
    """Extract flux scale factor from FITS header.

    Tries keywords in order: 'BSCALE' -> 'FLUXSCAL' -> 'FLUX_SCALE'.
    Defaults to 1.0 if none found.

    Parameters
    ----------
    header : astropy.io.fits.Header
        FITS header to search.

    Returns
    -------
    float
        Scale factor to apply to flux (and error) arrays.
    """
    for key in ['BSCALE', 'FLUXSCAL', 'FLUX_SCALE']:
        if key in header:
            scale = float(header[key])
            if scale != 1.0:
                logger.warning(
                    f"Found flux scale factor {key}={scale} in FITS header. "
                    f"Applying to flux and error arrays."
                )
            return scale
    return 1.0


def _extract_spectrum(hdul, mode):
    """Extract wavelength, flux, and error from FITS HDU.

    Parameters
    ----------
    hdul : astropy.io.fits.HDUList
        Open FITS file.
    mode : str
        Either 'table' (read hdul[1] as binary table) or 'image' (read hdul[0] as image).

    Returns
    -------
    lbd : ndarray
        Wavelength array (Angstroms).
    flux : ndarray
        Flux array.
    error : ndarray
        Error array.

    Raises
    ------
    ValueError
        If required data or keywords are missing.
    """
    if mode == 'table':
        # Try to read from binary table (hdul[1])
        if len(hdul) < 2 or hdul[1].data is None:
            raise ValueError("FITS file has no binary table HDU at index 1")

        table = Table(hdul[1].data)
        lbd = _read_wavelength_from_table(table)

        if lbd is None:
            # Wavelength not in table; try header WCS
            naxis1 = hdul[0].header.get('NAXIS1')
            if naxis1 is None:
                raise ValueError("Cannot reconstruct wavelength: no column in table and NAXIS1 missing")
            lbd = _read_wavelength_from_header(hdul[0].header, naxis1)

        # Extract flux and error columns
        flux = None
        for col_name in ['flux', 'FLUX', 'SIGNAL']:
            if col_name in table.colnames:
                flux = np.asarray(table[col_name])
                break
        if flux is None:
            raise ValueError(f"Flux column not found. Available: {table.colnames}")

        error = None
        error_col_name = None
        for col_name in ['error', 'ERROR', 'NOISE', 'VAR']:
            if col_name in table.colnames:
                error = np.asarray(table[col_name])
                error_col_name = col_name
                break
        if error is None:
            error = np.full_like(flux, np.nan)
        elif error_col_name == 'VAR':
            error = np.sqrt(error)

        # Apply scale factor
        scale = _read_scale_factor(hdul[0].header)
        flux = flux * scale
        error = error * scale

        return lbd, flux, error

    elif mode == 'image':
        # Read from primary image HDU (hdul[0])
        if hdul[0].data is None or hdul[0].data.ndim != 1:
            raise ValueError("Primary HDU is not a 1-D image")

        flux = np.asarray(hdul[0].data, dtype=float)
        naxis1 = flux.shape[0]

        # Try to read error from hdul[1] image if it exists
        error = None
        if len(hdul) > 1 and hdul[1].data is not None and hdul[1].data.ndim == 1:
            if hdul[1].data.shape[0] == naxis1:
                error = np.asarray(hdul[1].data, dtype=float)

        if error is None:
            error = np.full_like(flux, np.nan)

        # Reconstruct wavelength from header
        lbd = _read_wavelength_from_header(hdul[0].header, naxis1)

        # Apply scale factor
        scale = _read_scale_factor(hdul[0].header)
        flux = flux * scale
        error = error * scale

        return lbd, flux, error

    else:
        raise ValueError(f"Unknown mode: {mode}")


def readSpec(config, specid, grism):
    """Read a single spectrum from individual or combined FITS.

    Parameters
    ----------
    config : dict
        Flat config dict with I/O and quality settings.
    specid : str or int
        Spectrum identifier.
    grism : str
        Grism name (must be 'default' for generic instrument).

    Returns
    -------
    lbd : ndarray
        Wavelength array (Angstroms).
    flux : ndarray
        Flux array.
    error : ndarray
        Error array.

    Raises
    ------
    FileNotFoundError
        If the spectrum file does not exist.
    ValueError
        If the FITS format is not recognized or required data is missing.
    """
    global _pixel_size_warning_logged
    if not _pixel_size_warning_logged:
        logger.warning(
            "Generic instrument: only manual pixel_size_type is supported. "
            "Ensure pixel_resampling is set in your config."
        )
        _pixel_size_warning_logged = True

    spectrum_edges = config.get('spectrum_edges')
    spectra_mode = config.get('spectra_mode', 'individual fits')

    gcfg = config.get('grism_io', {}).get('default', {})
    spectra_dir = gcfg.get('spectra_dir')
    spectra_datafile = gcfg.get('spectra_datafile')

    if spectra_mode == 'combined fits' and spectra_datafile:
        # Combined FITS: multiple spectra in one file
        filepath = Path(spectra_dir) / f"{spectra_datafile}.fits"
        with fits.open(filepath, memmap=True) as hdul:
            # Try per-spectrum HDUs first
            if str(specid) in hdul:
                lbd, flux, error = _extract_spectrum(fits.HDUList([hdul[0], hdul[str(specid)]]), 'table')
            elif f"{specid}_default" in hdul:
                lbd, flux, error = _extract_spectrum(fits.HDUList([hdul[0], hdul[f"{specid}_default"]]), 'table')
            else:
                # Try primary HDU (image) lookup by name
                try:
                    # Fall back to assuming per-spectrum HDUs with the specid as a direct lookup
                    raise KeyError(f"HDU {specid} or {specid}_default not found")
                except KeyError:
                    raise ValueError(
                        f"Spectrum '{specid}' not found in {spectra_datafile}.fits. "
                        f"Expected HDU named '{specid}' or '{specid}_default'."
                    )
    else:
        # Individual FITS: one spectrum per file
        if not spectra_dir:
            raise ValueError(
                f"spectra_dir is not configured for grism '{grism}'. "
                "Check config['grism_io']."
            )
        filepath = Path(spectra_dir) / f"{specid}.fits"
        if not filepath.exists():
            raise FileNotFoundError(f"Spectrum file not found: {filepath}")

        with fits.open(filepath, memmap=True) as hdul:
            # Try binary table (hdul[1]) first, then fall back to primary image
            try:
                lbd, flux, error = _extract_spectrum(hdul, 'table')
            except (ValueError, IndexError):
                lbd, flux, error = _extract_spectrum(hdul, 'image')

    # Apply spectrum_edges trimming
    if spectrum_edges is not None:
        lo, hi = spectrum_edges
        flux[:lo] = error[:lo] = np.nan
        flux[hi:] = error[hi:] = np.nan

    return lbd, flux, error


def readSpec_metadata(config, specid, metadata_name, hdu_indx):
    """Read spectrum from metadata-provided FITS path and HDU index.

    Parameters
    ----------
    config : dict
        Flat config dict with quality settings.
    specid : str or int
        Spectrum identifier (unused; included for interface compatibility).
    metadata_name : str
        Full path to FITS file.
    hdu_indx : int
        HDU index to read from.

    Returns
    -------
    lbd : ndarray
        Wavelength array (Angstroms).
    flux : ndarray
        Flux array.
    error : ndarray
        Error array.
    """
    spectrum_edges = config.get('spectrum_edges')

    with fits.open(metadata_name) as hdul:
        # Try to read as table or image depending on HDU type
        hdu = hdul[hdu_indx]
        if hdu.data is None:
            raise ValueError(f"HDU {hdu_indx} in {metadata_name} has no data")

        if isinstance(hdu.data, np.ndarray) and hdu.data.ndim == 1:
            # 1-D array; assume image mode
            lbd, flux, error = _extract_spectrum(fits.HDUList([hdul[0], hdu]), 'image')
        else:
            # Try table mode first, then image
            try:
                lbd, flux, error = _extract_spectrum(fits.HDUList([hdul[0], hdu]), 'table')
            except (ValueError, TypeError):
                lbd, flux, error = _extract_spectrum(fits.HDUList([hdul[0], hdu]), 'image')

    # Apply spectrum_edges trimming
    if spectrum_edges is not None:
        lo, hi = spectrum_edges
        flux[:lo] = error[:lo] = np.nan
        flux[hi:] = error[hi:] = np.nan

    return lbd, flux, error


def prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges):
    """Compute wavelength grid bounds for stacking.

    If lambda_edges is provided, uses it directly (shifted to observed frame).
    Otherwise, reads the first spectrum to auto-detect the wavelength range and
    logs a warning that all spectra are assumed to share this range.

    Parameters
    ----------
    config : dict
        Flat config dict with I/O settings and catalog info.
    z_stacking : float
        Stacking redshift reference.
    zMin : float
        Minimum source redshift in sample.
    zMax : float
        Maximum source redshift in sample.
    lambda_edges : tuple[float, float] or None
        Rest-frame wavelength override (Å); if given, overrides auto-detection.

    Returns
    -------
    lbd_min : float
        Minimum wavelength for stacking (observed frame, Å).
    lbd_max : float
        Maximum wavelength for stacking (observed frame, Å).
    grismList : list of str
        List of grisms to iterate over (always ['default'] for generic).
    """
    if lambda_edges is not None:
        lbd_min = lambda_edges[0] * (1 + z_stacking)
        lbd_max = lambda_edges[1] * (1 + z_stacking)
    else:
        # Read first spectrum to detect wavelength range
        try:
            # Get first specid from catalog
            from spectraPyle.io.IO import read_catalog

            catalog_dir = config.get('catalog_dir')
            catalog_fname = config.get('catalog_fname')
            catalog_extension = config.get('catalog_extension')
            id_column = config.get('ID_column_name', 'ID')

            catalog_data = read_catalog(
                catalog_dir,
                catalog_fname,
                catalog_extension,
                mandatory_keys=[id_column]
            )
            first_specid = catalog_data[id_column][0]

            lbd, _, _ = readSpec(config, first_specid, 'default')
            lbd_min = np.nanmin(lbd)
            lbd_max = np.nanmax(lbd)

            logger.warning(
                f"Generic instrument: wavelength range inferred from first spectrum "
                f"[{lbd_min:.1f}, {lbd_max:.1f}] Å. "
                f"Assumes all spectra share this range. "
                f"Set lambda_edges_rest in config to override."
            )
        except Exception as e:
            raise ValueError(
                f"Could not auto-detect wavelength range from first spectrum: {e}. "
                f"Provide lambda_edges_rest in config to set it manually."
            )

    return lbd_min, lbd_max, ['default']
