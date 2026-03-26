import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy import units as u
import sys
from pathlib import Path
        
def prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges):
    
    grism_type=config['grism_type']
    wavelengths_grism_1=config['wavelengths_blue']
    wavelengths_grism_2=config['wavelengths_red']
    
    if config['z_type'] == 'observed_frame':
        z_stacking = zMax = zMin = 0 # so that lbd_min and lbd_max are equal to 
                                     # wavelengths_grism[0] and 
                                     # wavelengths_grism[1], rispectively.
    if lambda_edges is None:
        ## defining the wavelength array of the stacked spectrum:
        if (grism_type == 'red'):
            lbd_min = wavelengths_grism_2[0] * (1 + z_stacking) / (1 + zMax)
            lbd_max = wavelengths_grism_2[1] * (1 + z_stacking) / (1 + zMin)
        elif (grism_type == 'blue'):
            lbd_min = wavelengths_grism_1[0] * (1 + z_stacking) / (1 + zMax)
            lbd_max = wavelengths_grism_1[1] * (1 + z_stacking) / (1 + zMin)
        elif (grism_type == 'all'): 
            lbd_min = wavelengths_grism_1[0] * (1 + z_stacking) / (1 + zMax)
            lbd_max = wavelengths_grism_2[1] * (1 + z_stacking) / (1 + zMin)
        else:
            raise NameError('grism_type "', grism_type, '" not supported!')
    else:
        lbd_min = lambda_edges[0] * (1 + z_stacking)
        lbd_max = lambda_edges[1] * (1 + z_stacking)

    if (grism_type == 'red') or (grism_type == 'blue'):
        grismList = [grism_type]
    elif (grism_type == 'all'):
        grismList = ['blue', 'red']
    else:
        raise NameError('grism type not understood')
        
    return lbd_min, lbd_max, grismList


def int_to_bin7(mask_spec, list_bits_to_be_masked=[0, 2, 6]):

    mask_spec = np.asarray(mask_spec)

    if mask_spec.ndim != 1:
        raise ValueError(
            f"mask_spec must be 1D array of ints, got shape {mask_spec.shape}"
        )

    masked_array = np.zeros(mask_spec.shape, dtype=bool)

    for k, n in enumerate(mask_spec):
        nb = f'{int(n):07b}'[::-1]
        list_bits = [i for i, b in enumerate(nb) if b == '1']
        masked_array[k] = any(x in list_bits_to_be_masked for x in list_bits)

    return masked_array

'''
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


def readSpec(config, specid):
    """
    Reads spectrum data from FITS files. Supports single-spectrum FITS files or 
    multi-spectrum FITS files where spectra are stored in different HDUs.

    Args:
        config (dict): Configuration dictionary with keys:
                       - 'pixel_mask': Pixel mask configuration (bool or list of bits to mask).
                       - 'n_min_dithers': Minimum number of dithers for valid data.
        specid (str): Name of the spectrum to extract.

    Returns:
        tuple: Wavelengths (lbd), flux, and error arrays.

    Raises:
        NameError: If required data columns are not found or if the file format is not recognized.
    """
    pixel_mask = config['pixel_mask']
    n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']
    
    if config['spectra_datafile'] is not None:
        # Handle multi-spectrum FITS file
        with fits.open(config['spectra_dir']+config['spectra_datafile']+'.fits') as hdul:
            for hdu in hdul:
                if hdu.name == str(specid):
                    table1 = Table(hdu.data)
                    break
            else:
                raise NameError(f"Spectral data for '{specid}' not found in {config['spectra_datafile']}.fits.")
                sys.exit(1)
    else:
        # Handle single-spectrum FITS file
        with fits.open(config['spectra_dir']+str(specid)+'.fits') as hdulist:
            table1 = Table(hdulist[1].data)

    # Extract flux
    if 'flux' in table1.colnames:
        flux = table1['flux']
    elif 'SIGNAL' in table1.colnames:
        flux = table1['SIGNAL']
    else:
        raise NameError('Data model of the input fluxes *.fits file not recognized.')

    # Extract error
    if 'error' in table1.colnames:
        error = table1['error']
    elif 'VAR' in table1.colnames:
        error = np.sqrt(table1['VAR'])
    else:
        raise NameError('Data model of the input errors *.fits file not recognized.')

    # Extract wavelength
    if 'wave' in table1.colnames:
        lbd = table1['wave']
    elif 'WAVELENGTH' in table1.colnames:
        lbd = table1['WAVELENGTH']
    else:
        raise NameError('Data model of the input wavelengths *.fits file not recognized.')

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
    
    if spectrum_edges is not False:
        flux[:spectrum_edges[0]] = np.nan
        error[:spectrum_edges[0]] = np.nan
        
        flux[spectrum_edges[1]:] = np.nan
        error[spectrum_edges[1]:] = np.nan
    
        
    return lbd, flux, error
'''

def build_spectrum_filename(specid, config, grism):
    """
    Build spectrum filename depending on instrument/data release.

    Parameters
    ----------
    specid : int or str
    config : dict
    grism : str ("red" | "blue")

    Returns
    -------
    str
    """

    data_release = config.get("data_release")

    # ---------------- DR1 ----------------
    if data_release == "DR1":
        prefix_map = {
            "red": "RGS",
            "blue": "BGS",
        }

        prefix = prefix_map.get(grism)
        if prefix is None:
            raise ValueError(f"Unknown grism: {grism}")

        return f"SPECTRA_{prefix}-sedm {specid}.fits"

    # ---------------- DEFAULT ----------------
    return f"{specid}.fits"

def readSpec(config, specid, grism):
    """
    Reads spectrum data from FITS files. Supports single-spectrum FITS files or 
    multi-spectrum FITS files where spectra are stored in different HDUs, or all in an HDU called 'SPECTRA'.

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
    
    pixel_mask = config['pixel_mask']
    n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']

    data_release = config['data_release']
    
    if config['spectra_datafile'] is not None:
        # Multi-spectrum FITS file
        filepath = config['spectra_dir'] / f"{config['spectra_datafile']}.fits"
        
        with fits.open(filepath, memmap=True) as hdul:

            # --------------------------------------------------
            # Case 1: one spectrum per HDU, HDU name == specid
            # --------------------------------------------------
            if str(specid) in hdul:
                table1 = Table(hdul[str(specid)].data)

            # --------------------------------------------------
            # Case 2: all spectra in a single table HDU
            # --------------------------------------------------
            elif 'SPECTRA' in hdul:
                hdu = hdul['SPECTRA']
                data = hdu.data

                id_col = config['ID_column_name']
                
                if id_col not in hdu.columns.names:
                    raise NameError(
                        f"ID column '{id_col}' not found in HDU "
                        f"{'SPECTRA'}"
                    )
                
                ids = data[id_col]               
                mask_id = ids == int(specid) 
                
                
                if not np.any(mask_id):
                    raise NameError(
                        f"Spectral data for '{specid}' not found in "
                        f"{config['spectra_datafile']}.fits."
                    )
                
                table1 = Table(data[mask_id])

            # --------------------------------------------------
            # Unknown format
            # --------------------------------------------------
            
            else:
                raise NameError(
                    f"Unrecognized FITS structure in "
                    f"{config['spectra_datafile']}.fits."
                )
            
    else:
        # --------------------------------------------------
        # Case 3: one FITS file per spectrum
        # --------------------------------------------------
        #filepath = config['spectra_dir'] / f"{str(specid)}.fits"
        #filepath = f"{config['spectra_dir']}/{str(specid)}.fits"

        filename = build_spectrum_filename(specid, config, grism)
        filepath = config['spectra_dir'] / filename
        

        with fits.open(filepath, memmap=True) as hdul:
            table1 = Table(hdul[1].data)
    
    # Extract flux
    if 'flux' in table1.colnames:
        flux = table1['flux']
    elif 'SIGNAL' in table1.colnames:
        flux = table1['SIGNAL']
    else:
        raise NameError('Data model of the input fluxes *.fits file not recognized.')
    
    flux = ravel_array(arr=flux, name='flux')
        
    # Extract error
    if 'error' in table1.colnames:
        error = table1['error']
    elif 'VAR' in table1.colnames:
        error = np.sqrt(table1['VAR'])
    else:
        raise NameError('Data model of the input errors *.fits file not recognized.')
    
    error = ravel_array(arr=error, name='error spectrum')
        
    # Extract wavelength
    if 'wave' in table1.colnames:
        lbd = table1['wave']
    elif 'WAVELENGTH' in table1.colnames:
        lbd = table1['WAVELENGTH']
    else:
        raise NameError('Data model of the input wavelengths *.fits file not recognized.')
    
    lbd = ravel_array(arr=lbd, name='wavelength') 
    
    # Optional extra data
    mask = table1['mask'] if 'mask' in table1.colnames else table1['MASK'] if 'MASK' in table1.colnames else None
    mask = ravel_array(arr=mask, name='mask spectrum')
    
    ndith = table1['NDith'] if 'NDith' in table1.colnames else table1['NDITH'] if 'NDITH' in table1.colnames else None
    ndith = ravel_array(arr=ndith, name='ndith (N. dithers)')
    
    quality = table1['Quality'] if 'Quality' in table1.colnames else table1['QUALITY'] if 'QUALITY' in table1.colnames else None
    quality = ravel_array(arr=quality, name='quality')
    
    # Apply pixel bitmask
    if pixel_mask and mask is not None:
        indxBadPixels = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
        flux[indxBadPixels] = np.nan
        error[indxBadPixels] = np.nan
    
    # Apply dithers filter
    if n_min_dithers > 0 and ndith is not None:
        flux = np.where(ndith < n_min_dithers, np.nan, flux)
        error = np.where(ndith < n_min_dithers, np.nan, error)
    if spectrum_edges is not None:
        flux[:spectrum_edges[0]] = np.nan
        error[:spectrum_edges[0]] = np.nan
        
        flux[spectrum_edges[1]:] = np.nan
        error[spectrum_edges[1]:] = np.nan
    return lbd, flux, error


def readSpec_metadata(config, specid, metadata_name, hdu_indx):
    
    pixel_mask = config['pixel_mask']
    n_min_dithers = config['n_min_dithers']
    spectrum_edges = config['spectrum_edges']

    path_name = metadata_name
    
    hdul = fits.open(path_name)
    data = hdul[hdu_indx].data

    lbd = data.field('WAVELENGTH')
    flux = data.field('SIGNAL')
    var = data.field('VAR')
    mask = data.field('MASK')
    ndith = data.field('NDITH')
    
    error = np.sqrt(var)
    
    # Apply pixel bitmask:
    if pixel_mask and mask is not None:
        indxBadPixels = int_to_bin7(mask, list_bits_to_be_masked=pixel_mask)
        flux[indxBadPixels] = np.nan
        error[indxBadPixels] = np.nan
        
    # Apply dithers filter:
    if n_min_dithers > 0 and ndith is not None:
        flux = np.where(ndith < n_min_dithers, np.nan, flux)
        error = np.where(ndith < n_min_dithers, np.nan, error)
        
    if spectrum_edges is not None:
        flux[:spectrum_edges[0]] = np.nan
        error[:spectrum_edges[0]] = np.nan
        
        flux[spectrum_edges[1]:] = np.nan
        error[spectrum_edges[1]:] = np.nan

    return lbd, flux, error

def ravel_array(arr, name):
    """
    Ensure that an array representing a single spectrum is 1D.

    This helper is used to normalize arrays that may come from different
    FITS storage layouts:
      - a true 1D array of length N (expected case)
      - a 2D array with shape (1, N), e.g. when extracting a single row
        from a table where each row contains array-valued columns

    Any other shape indicates an unexpected or ambiguous data structure
    and results in an error.

    Parameters
    ----------
    arr : array-like
        Input array to be flattened if needed.
    name : str
        Name of the quantity being processed (used for informative
        error messages).

    Returns
    -------
    arr : numpy.ndarray
        One-dimensional NumPy array.

    Raises
    ------
    ValueError
        If the input array does not represent a single 1D spectrum.
    """
    arr = np.asarray(arr)
    if arr.ndim == 2 and arr.shape[0] == 1:
        arr = arr[0]
    elif arr.ndim != 1:
        raise ValueError(f"Unexpected {name} shape: {arr.shape}")
    
    return arr