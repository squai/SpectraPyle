import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy import units as u
import sys
from pathlib import Path        

def prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges):
    
    grism_type=config['grism_type']
    wavelengths_grism=config['wavelengths']
    
    if config['z_type'] == 'observed_frame':
        z_stacking = zMax = zMin = 0 # so that lbd_min and lbd_max are equal to 
                                     # wavelengths_grism[0] and 
                                     # wavelengths_grism[1], rispectively.
    
    if lambda_edges is None:
        ## defining the wavelength array of the stacked spectrum:
        if (grism_type == 'merged'):
            lbd_min = wavelengths_grism[0] * (1 + z_stacking) / (1 + zMax)
            lbd_max = wavelengths_grism[1] * (1 + z_stacking) / (1 + zMin)
        else:
            raise NameError('grism_type "', grism_type, '" not supported!')
    else:
        lbd_min = lambda_edges[0] * (1 + z_stacking)
        lbd_max = lambda_edges[1] * (1 + z_stacking)

    if (grism_type == 'merged'):
        grismList = [grism_type]
    else:
        raise NameError('grism type not understood')
        
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

def readSpec(config, specid, grism):
    """
    Reads spectrum data from FITS files. Supports single-spectrum FITS files or 
    multi-spectrum FITS files where spectra are stored in different HDUs.

    Args:
        config (dict): Configuration dictionary with keys:
                       - 'pixel_mask': Pixel mask configuration (bool or list of bits to mask).
                       - 'n_min_dithers': Minimum number of dithers for valid data.
        specid (str): Name of the spectrum to extract.
        grism (str): Name of the grism 

    Returns:
        tuple: Wavelengths (lbd), flux, and error arrays.

    Raises:
        NameError: If required data columns are not found or if the file format is not recognized.
    """
    #pixel_mask = config['pixel_mask']
    #n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']
    
    if config['spectra_datafile'] is not None:
        # Handle multi-spectrum FITS file
        filepath = config['spectra_dir'] / f"{config['spectra_datafile']}.fits"
        with fits.open(filepath) as hdul:
            for hdu in hdul:
                if hdu.name == str(specid):
                    table1 = Table(hdu.data)
                    break
            else:
                raise NameError(f"Spectral data for '{specid}' not found in {config['spectra_datafile']}.fits.")
                sys.exit(1)
    else:
        # Handle single-spectrum FITS file
        filepath = config['spectra_dir'] / f"{str(specid)}.fits"
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
    
    #pixel_mask = config['pixel_mask']
    #n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']

    path_name = metadata_name
    
    hdul = fits.open(path_name)
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
