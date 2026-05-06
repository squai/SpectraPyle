"""
DESI instrument driver for SpectraPyle.

Implements the instrument interface for DESI spectra (grism: ``merged``):
:func:`readSpec`, :func:`readSpec_metadata`, :func:`prepare_stacking`,
:func:`_resolve_filepath`.
"""

import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy import units as u
import sys
from pathlib import Path

from spectraPyle.utils.log import get_logger
from spectraPyle.instruments import _combined_fits_cache as _cache

logger = get_logger(__name__)

def prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges):
    """Compute the wavelength grid bounds and the grism iteration list.

    The wavelength range for DESI covers the merged grism wavelength range,
    adjusted for redshift.

    Parameters
    ----------
    config : dict
        Flat config dict. Must contain ``'grisms'`` (List[str]),
        ``'wavelengths'`` (merged wavelength range), ``'spectra_mode'``, ``'z_type'``.
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

    Raises
    ------
    ValueError
        If grism is not supported for DESI.
    """

    grisms = config['grisms']          # List[str], e.g. ['merged']
    wavelengths_grism = config['wavelengths']

    _supported = {'merged': wavelengths_grism}

    if config['z_type'] == 'observed_frame':
        z_stacking = zMax = zMin = 0

    if lambda_edges is None:
        lbd_mins, lbd_maxs = [], []
        for g in grisms:
            if g not in _supported:
                raise ValueError(
                    f"Grism '{g}' is not supported for DESI. "
                    f"Supported: {list(_supported)}."
                )
            wl = _supported[g]
            lbd_mins.append(wl[0] * (1 + z_stacking) / (1 + zMax))
            lbd_maxs.append(wl[1] * (1 + z_stacking) / (1 + zMin))
        lbd_min = min(lbd_mins)
        lbd_max = max(lbd_maxs)
    else:
        lbd_min = lambda_edges[0] * (1 + z_stacking)
        lbd_max = lambda_edges[1] * (1 + z_stacking)

    use_metadata = config.get('spectra_mode') == 'metadata path'
    grismList = ['metadata'] if use_metadata else list(grisms)

    return lbd_min, lbd_max, grismList

"""
def int_to_bin7(mask_spec, list_bits_to_be_masked = [0,2,6]):
    masked_array = np.full_like(mask_spec, False, dtype=bool)
    for k, n in enumerate(mask_spec):
        nb = f'{n:07b}'[::-1]
        if len(str(nb)) == 7:
            list_bits = []
            for i in range(len(nb)):
                if nb[i] == str(1):
                    list_bits.append(i)
            masked_array[k] = any(x in list_bits_to_be_masked for x in list_bits)
        else:
            raise ValueError('wrong binary number!')
    return masked_array
"""

def _build_desi_index(hdul):
    names = frozenset(hdu.name for hdu in hdul)
    return {'layout': 'per_hdu', 'names': names}


def _lookup_desi(hdul, index, specid):
    if str(specid) in index['names']:
        return Table(hdul[str(specid)].data)
    raise NameError(f"Spectrum '{specid}' not found in combined FITS.")


def readSpec(config, specid, grism):
    """Read a single spectrum for the given grism.

    Supports both combined FITS (multiple spectra in one file) and
    individual FITS (one spectrum per file).

    Parameters
    ----------
    config : dict
        Flat config dict with I/O and quality settings.
    specid : str or int
        Spectrum identifier.
    grism : str
        Grism name (``"merged"`` for DESI).

    Returns
    -------
    lbd : ndarray
        Wavelength array (Å).
    flux : ndarray
        Flux array.
    error : ndarray
        Error/noise array.

    Raises
    ------
    NameError
        If required data columns are not found.
    ValueError
        If spectra_dir is not configured.
    """
    #pixel_mask = config['pixel_mask']
    #n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']
    
    gcfg = config.get('grism_io', {}).get(grism, {})
    spectra_dir      = gcfg.get('spectra_dir')
    spectra_datafile = gcfg.get('spectra_datafile')

    if spectra_datafile:
        filepath = Path(spectra_dir) / f"{spectra_datafile}.fits"
        if _cache.is_active(grism):
            hdul = _cache.get_hdul(grism)
            index = _cache.get_index(grism)
            if index is None:
                index = _build_desi_index(hdul)
                _cache.set_index(grism, index)
            table1 = _lookup_desi(hdul, index, specid)
        else:
            with fits.open(filepath, memmap=True) as hdul:
                for hdu in hdul:
                    if hdu.name == str(specid):
                        table1 = Table(hdu.data)
                        break
                else:
                    raise NameError(f"Spectrum '{specid}' not found in {spectra_datafile}.fits.")
    else:
        if not spectra_dir:
            raise ValueError(f"spectra_dir not configured for grism '{grism}'. Check config['grism_io'].")
        filepath = Path(spectra_dir) / f"{str(specid)}.fits"
        with fits.open(filepath) as hdulist:
            table1 = Table(hdulist[1].data)

    # Extract flux
    if 'flux' in table1.colnames:
        flux = table1['flux']
    else:
        raise NameError('Data model of the input fluxes *.fits file not recognized.')

    # Extract error
    if 'noise' in table1.colnames:
        error = table1['noise']
    else:
        raise NameError('Data model of the input errors *.fits file not recognized.')

    # Extract wavelength
    if 'wavelength' in table1.colnames:
        lbd = table1['wavelength']
    else:
        raise NameError('Data model of the input wavelengths *.fits file not recognized.')
    
    """
    # Optional extra data
    mask = table1['mask'] if 'mask' in table1.colnames else table1['MASK'] if 'MASK' in table1.colnames else None
    ndith = table1['NDith'] if 'NDith' in table1.colnames else table1['NDITH'] if 'NDITH' in table1.colnames else None
    quality = table1['Quality'] if 'Quality' in table1.colnames else table1['QUALITY'] if 'QUALITY' in table1.colnames else None

    # Apply pixel bitmask
    if pixel_mask and mask is not None:
        indxBadPixels = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
        flux[indxBadPixels] = np.nan
        error[indxBadPixels] = np.nan

    # Apply dithers filter
    if n_min_dithers > 0 and ndith is not None:
        flux = np.where(ndith < n_min_dithers, np.nan, flux)
        error = np.where(ndith < n_min_dithers, np.nan, error)
    """
    
    if spectrum_edges is not None:
        flux[:spectrum_edges[0]] = np.nan
        error[:spectrum_edges[0]] = np.nan
        
        flux[spectrum_edges[1]:] = np.nan
        error[spectrum_edges[1]:] = np.nan
    
        
    return lbd, flux, error


def readSpec_metadata(config, specid, metadata_name, hdu_indx):
    """Read spectrum from a metadata-driven FITS path + HDU index.

    Parameters
    ----------
    config : dict
        Flat config dict with spectrum quality settings.
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
        Error/noise array.
    """

    spectrum_edges = config['spectrum_edges']

    path_name = metadata_name

    with fits.open(path_name) as hdul:
        data = hdul[hdu_indx].data

        lbd = data.field('wavelength')
        flux = data.field('flux')
        error = data.field('noise')
        """
        mask = data.field('MASK')
        ndith = data.field('NDITH')

        # Apply pixel bitmask:
        if pixel_mask and mask is not None:
            indxBadPixels = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
            flux[indxBadPixels] = np.nan
            error[indxBadPixels] = np.nan

        # Apply dithers filter:
        if n_min_dithers > 0 and ndith is not None:
            flux = np.where(ndith < n_min_dithers, np.nan, flux)
            error = np.where(ndith < n_min_dithers, np.nan, error)
        """

        if spectrum_edges is not None:
            flux[:spectrum_edges[0]] = np.nan
            error[:spectrum_edges[0]] = np.nan

            flux[spectrum_edges[1]:] = np.nan
            error[spectrum_edges[1]:] = np.nan

    return lbd, flux, error
