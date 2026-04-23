import os
import os.path
import numpy as np
import pandas as pd
from astropy.io import fits
from multiprocessing import Pool


import spectraPyle.spectrum.spectra as sspec
import spectraPyle.spectrum.normalization as snorm
import spectraPyle.spectrum.resampling as sres

from tqdm import tqdm

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
    use_metadata = config.get('spectra_datafile', '') == 'metadata'

    # -------- Metadata preparation --------
    if use_metadata:
        if data_input is None:
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

    # -------- Multiprocessing --------
    with Pool(processes=self.num_cpus) as pool:
        results = list(
            tqdm(
                pool.imap(process_spectrum_parallel, args),
                total=len(args),
                desc="Processing Files"
            )
        )

    # -------- Unpack results --------
    specid, specResampledArr, errResampledArr, normalization_factors, spectra_not_found = zip(*results)

    specid = np.array(specid)
    specResampledArr = np.array(specResampledArr).squeeze().T
    errResampledArr = np.array(errResampledArr).squeeze().T
    normalization_factors = np.array(normalization_factors).squeeze()
    spectra_not_found = np.array(spectra_not_found, dtype=str).squeeze()

    return (
        specResampledArr,
        errResampledArr,
        normalization_factors,
        spectra_not_found,
        specid
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
        (specid, specResampled, errResampled, normalization_factor, spectra_not_found)

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

    use_metadata = config.get('spectra_datafile', '') == 'metadata'
    
    for grism in grismList:
        try:
            # -------- Spectrum Loading --------
            # Note: the spectrum will be shifted at redshift=z_stacking
            wavelength, spec, err = sspec.useSpec(
                config, specid, z, z_stacking, ebv_g, cosmology, grism, 
                    metadata_name, hdu_indx
            )
            
        
            # -------- Spectra Normalization --------
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
                if config['z_type'] == 'observed_frame':
                    z_st = 0
                else:
                    z_st = z_stacking
                    
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
                raise NameError(
                    f"Normalization type {config['spectra_normalization']} not supported!"
                )

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

            return (
                specid,
                specResampled,
                errResampled,
                normalization_factor,
                spectra_not_found
            )

        except Exception as e:
            print(f"Skipping spectrum {specid}: {e} ")

            normalization_factor = np.nan
            skip_spectrum = specid

            return (
                specid,
                np.full_like(wavelength_stacking_bins[:-1], np.inf),
                np.full_like(wavelength_stacking_bins[:-1], np.inf),
                normalization_factor,
                skip_spectrum
            )

        
