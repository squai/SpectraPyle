"""
Multiprocessing driver for per-spectrum processing.

:func:`main_parallel` splits spectrum IDs across CPUs and runs the
read → redshift-shift → resample → normalize pipeline for each spectrum.
"""

import os
import os.path
import numpy as np
import pandas as pd
from astropy.io import fits
from multiprocessing import Pool
import logging
import logging.handlers
from pathlib import Path

import spectraPyle.spectrum.spectra as sspec
import spectraPyle.spectrum.normalization as snorm
import spectraPyle.spectrum.resampling as sres

from tqdm import tqdm

from spectraPyle.utils.log import get_logger
from spectraPyle.instruments._combined_fits_cache import init_file_handles, close_file_handles

logger = get_logger(__name__)


def _worker_logging_init(queue):
    """Configure logging in worker process via QueueHandler.

    Parameters
    ----------
    queue : multiprocessing.Queue
        Queue to send log records to the main process.
    """
    root = logging.getLogger("spectraPyle")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(logging.handlers.QueueHandler(queue))

def _worker_init(log_queue, grism_paths):
    """Initialize worker process with logging and combined FITS cache handles.

    Parameters
    ----------
    log_queue : multiprocessing.Queue
        Queue to send log records to the main process.
    grism_paths : dict or None
        Mapping of grism names to combined FITS file paths.
    """
    _worker_logging_init(log_queue)
    if grism_paths:
        init_file_handles(grism_paths)

def main_parallel(
    self,
    specIDs,
    redshift,
    ebv_galactic,
    custom_norm_param,
    wavelength_stacking_bins,
    pixelResampling,
    z_stacking,
    grismList,
    data_input=None
):
    """
    Parallel processing driver for spectrum stacking.

    This function prepares multiprocessing inputs and runs spectrum processing
    across CPUs. It supports both standard spectrum loading and metadata-driven
    loading depending on config['spectra_datafile'].

    Parameters
    ----------
    self : object
        Parent class instance containing config, cosmology, and num_cpus.
    specIDs : array-like
        Spectrum identifiers.
    redshift : array-like
        Source redshifts.
    ebv_galactic : array-like
        Galactic extinction values.
    custom_norm_param : array-like
        Custom normalization parameters (if used).
    wavelength_stacking_bins : ndarray, or 'none' (only if pixel_resampling_type='none')
        Target wavelength grid.
    pixelResampling : any, or 'none' (only if pixel_resampling_type='none')
        Resampling configuration.
    z_stacking : float, or 'observed' (only if z_type='observed_frame')
        Stacking reference redshift.
    grismList : list
        List of grisms to process.
    data_input : pandas.DataFrame, optional
        Required only if spectra_datafile='metadata'.

    Returns
    -------
    tuple
        specResampledArr, errResampledArr, normalization_factors,
        spectra_not_found, specid
    """

    config = self.config
    cosmology = self.cosmology
    use_metadata = config.get('spectra_mode') == 'metadata path'

    # -------- Metadata preparation --------
    if use_metadata:
        if data_input is None:
            logger.error("data_input must be provided when spectra_datafile='metadata'")
            raise ValueError(
                "data_input must be provided when spectra_datafile='metadata'"
            )

        metadata_name = (
            data_input[config['metadata_path_column_name']]
            + '/'
            + data_input[config['metadata_file_column_name']]
        )

        metadata_indx = data_input[config['metadata_indx_column_name']]

    else:
        metadata_name = [None] * len(specIDs)
        metadata_indx = [None] * len(specIDs)

    # -------- Argument packing --------
    args = [
        (
            specid, z, ebv_g, norm_param,
            mname, mindx,
            config, cosmology,
            wavelength_stacking_bins, pixelResampling,
            z_stacking, grismList
        )
        for specid, z, ebv_g, norm_param, mname, mindx in zip(
            specIDs, redshift, ebv_galactic,
            custom_norm_param, metadata_name, metadata_indx
        )
    ]

    # -------- Build grism_paths for combined FITS cache --------
    spectra_mode = config.get('spectra_mode')
    grism_paths = {}
    if spectra_mode == 'combined fits':
        for grism in grismList:
            gcfg = config.get('grism_io', {}).get(grism, {})
            datafile = gcfg.get('spectra_datafile')
            if datafile:
                grism_paths[grism] = Path(gcfg['spectra_dir']) / f"{datafile}.fits"

    # -------- Multiprocessing --------
    parent_handlers = logging.getLogger("spectraPyle").handlers[:]

    if config.get('multiprocessing', True):
        import multiprocessing
        log_queue = multiprocessing.Queue()
        listener = logging.handlers.QueueListener(
            log_queue, *parent_handlers, respect_handler_level=True
        )
        listener.start()
        try:
            with Pool(
                processes=self.num_cpus,
                initializer=_worker_init,
                initargs=(log_queue, grism_paths)
            ) as pool:
                results = list(
                    tqdm(
                        pool.imap(process_spectrum_parallel, args),
                        total=len(args),
                        desc="Processing Files"
                    )
                )
        finally:
            listener.stop()
    else:
        if grism_paths:
            init_file_handles(grism_paths)
        try:
            results = list(
                tqdm(
                    map(process_spectrum_parallel, args),
                    total=len(args),
                    desc="Processing Files"
                )
            )
        finally:
            if grism_paths:
                close_file_handles()
    
    # Flatten results
    flat_results = [item for sublist in results for item in sublist]

    # -------- Unpack results --------
    specid_result, grism_labels, specResampledArr, errResampledArr, normalization_factors, spectra_not_found = zip(*flat_results)

    # Convert to arrays
    specid_result = np.array(specid_result)
    grism_labels = np.array(grism_labels)

    specResampledArr = np.array(specResampledArr).T
    errResampledArr = np.array(errResampledArr).T

    normalization_factors = np.array(normalization_factors)
    spectra_not_found = np.array(spectra_not_found, dtype=str)

    return (
        specResampledArr,
        errResampledArr,
        normalization_factors,
        spectra_not_found,
        specid_result,
        grism_labels
    )

def process_spectrum_parallel(args):
    """
    Process a single spectrum for stacking using multiprocessing.

    This function:
    - Loads the spectrum using either standard or metadata-based I/O depending on
      config['spectra_datafile'].
    - Applies the selected normalization method.
    - Resamples the spectrum to the stacking wavelength grid.
    - Returns resampled flux, error, normalization factor, and failure flag.

    Parameters
    ----------
    args : tuple
        Contains:
            specid : str or int
                Spectrum identifier.
            z : float
                Source redshift.
            ebv_g : float
                Galactic extinction value.
            norm_param : any
                Custom normalization parameter if using 'custom' normalization.
            metadata_name : str or None
                Metadata filename/path (only used if spectra_datafile='metadata').
            hdu_indx : int or None
                HDU index in metadata FITS file (only used if metadata mode).
            config : dict
                Global configuration dictionary.
            cosmology : astropy.cosmology
                Cosmology object.
            wavelength_stacking_bins : ndarray
                Target wavelength grid for stacking.
            pixelResampling : any
                Resampling configuration (kept for compatibility).
            z_stacking : float
                Stacking redshift reference.
            grismList : list
                List of grisms to process.

    Returns
    -------
    tuple
        (specid_grism, specResampled, errResampled, normalization_factor, spectra_not_found)

    Notes
    -----
    - If spectrum loading or processing fails, returns arrays filled with inf and
      marks the spectrum as not found.
    """
    (
        specid, z, ebv_g, norm_param,
        metadata_name, hdu_indx,
        config, cosmology,
        wavelength_stacking_bins, pixelResampling,
        z_stacking, grismList
    ) = args

    results = []

    for grism in grismList:
        try:
            # -------- Spectrum Loading --------
            wavelength, spec, err = sspec.useSpec(
                config, specid, z, z_stacking, ebv_g, cosmology, grism,
                metadata_name, hdu_indx
            )

            # -------- Quality Check BEFORE Normalization --------
            finite_mask = np.isfinite(spec) & np.isfinite(err)
            median_valid_flux = np.nanmedian(spec[finite_mask])
            
            if not np.isfinite(median_valid_flux) or median_valid_flux <= 0:
                logger.error(
                    f"Spectrum rejected: "
                    f"non-positive median flux ({median_valid_flux}) -> would lead to negative/invalid normalization"
                    )
            
            # -------- Normalization --------
            if config['spectra_normalization'] in ['no_normalization', 'template']:
                normalization_factor = 1.0

            elif config['spectra_normalization'] == 'integral':
                spec, err, normalization_factor = snorm.normSpecIntegrMean(
                    wavelength, spec, err
                )

            elif config['spectra_normalization'] == 'median':
                spec, err, normalization_factor = snorm.normSpecMed(
                    wavelength, spec, err
                )

            elif config['spectra_normalization'] == 'interval':
                z_st = 0 if config['z_type'] == 'observed_frame' else z_stacking

                spec, err, normalization_factor = snorm.normSpecInterv(
                    specid,
                    wavelength, spec, err,
                    config['lambda_norm_rest'][0] * (1 + z_st),
                    config['lambda_norm_rest'][1] * (1 + z_st),
                    config['interval_norm_statistics']
                )

            elif config['spectra_normalization'] == 'custom':
                spec, err, normalization_factor = snorm.normSpecCustom(
                    wavelength, spec, err, norm_param
                )

            else:
                logger.error(f"Normalization type {config['spectra_normalization']} not supported!")

            # -------- Resampling --------
            if config['pixel_resampling_type'] != 'none':
                specResampled, errResampled = sres.resamplingSpecFluxCons(
                    wavelength, spec, err**2,
                    lambdaInterp=wavelength_stacking_bins
                )
            else:
                specResampled = spec
                errResampled = err

            spectra_not_found = np.nan

        except Exception as e:
            logger.error(f"Error processing spectrum {specid} (grism={grism}): {e}")

            specResampled = np.full_like(wavelength_stacking_bins[:-1], np.inf)
            errResampled = np.full_like(wavelength_stacking_bins[:-1], np.inf)
            normalization_factor = np.nan
            spectra_not_found = specid

        # append ONE result per grism
        results.append((
            specid,
            grism,
            specResampled,
            errResampled,
            normalization_factor,
            spectra_not_found
        ))

    return results
        
