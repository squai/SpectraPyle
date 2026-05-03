"""
Catalog I/O, wavelength grid construction, and FITS output writer.

Key functions:

- :func:`read_catalog` — loads npz/fits/csv catalogs
- :func:`build_wavelength_grid` — constructs the target resampling grid
- :func:`save_to_file` — writes the stacked spectra to a FITS file
"""

import os
import os.path
import numpy as np
import pandas as pd
from astropy.io import fits
from multiprocessing import Pool

from spectraPyle.utils.log import get_logger

logger = get_logger(__name__)

import spectraPyle.spectrum.spectra as sspec
import spectraPyle.spectrum.normalization as snorm
import spectraPyle.spectrum.resampling as sres

from tqdm import tqdm

'''
def get_incremental_dir(base_path):
    """
    Incremental output directory

    Args:
        base_path: output directory from the configuration file

    Returns: 
        new_path: incremental {base_path}_i (i=1,2,...), if base_path exists. 
    """
    if not os.path.exists(base_path):
        return base_path

    i = 1
    while True:
        new_path = f"{base_path}_{i}"
        if not os.path.exists(new_path):
            return new_path
        i += 1
''' 

def read_catalog(dirIn, fname, extension, mandatory_keys):
    """Load a catalog file and extract mandatory columns.

    Parameters
    ----------
    dirIn : str
        Directory containing the catalog file.
    fname : str
        Filename without extension.
    extension : {"npz", "fits", "csv"}
        File format.
    mandatory_keys : list of str
        Column names that must be present.

    Returns
    -------
    dict
        Keys are column names, values are arrays.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at ``dirIn/fname.extension``.
    ValueError
        If a mandatory key is missing or the format is unsupported.
    """
    supported_extensions = ['npz', 'fits', 'csv']
    if extension not in supported_extensions:
        raise ValueError(
            f"Unsupported file extension: {extension}. Supported extensions are: {supported_extensions}."
        )

    file_path = os.path.join(dirIn, f"{fname}.{extension}")
    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"File '{fname}.{extension}' not found in directory '{dirIn}'."
        )

    # Initialize the result dictionary
    data = {}

    # Read the file based on its extension
    try:
        if extension == 'npz':
            with np.load(file_path, allow_pickle=True) as stackFiles:
                for key in mandatory_keys:
                    if key not in stackFiles:
                        raise ValueError(f"Mandatory key '{key}' is missing in '{fname}.{extension}'.")
                    data[key] = stackFiles[key]
        
        elif extension == 'fits':
            with fits.open(file_path) as hdul:
                table_data = hdul[1].data  # Assuming the data is in the first extension
                all_keys = table_data.columns.names
                for key in mandatory_keys:
                    if key not in all_keys:
                        raise ValueError(f"Mandatory key '{key}' is missing in '{fname}.{extension}'.")
                    data[key] = table_data[key]
        
        elif extension == 'csv':
            csv_data = pd.read_csv(file_path)
            all_keys = csv_data.columns
            for key in mandatory_keys:
                if key not in all_keys:
                    raise ValueError(f"Mandatory key '{key}' is missing in '{fname}.{extension}'.")
                data[key] = csv_data[key].values

        else:
            raise ValueError(f"Unsupported file extension: {extension}")

    except Exception as e:
        raise ValueError(f"Error reading file '{file_path}': {e}")

    print(f"File successfully read: {file_path}")
    return data

def z_stack(redshift, z_type, conservation):
    """Determine the redshift of the stacked spectrum.

    Parameters
    ----------
    redshift : ndarray
        Redshifts of the spectra to be stacked.
    z_type : str, int, or float
        Keyword for stacking redshift. One of:
        - 'median_z': median of redshift array
        - 'minimum_z': minimum of redshift array
        - 'maximum_z': maximum of redshift array
        - 'rest_frame': z=0
        - float/int: user-defined redshift value
    conservation : str
        Spectral quantity to conserve: 'luminosity' or 'flux'.

    Returns
    -------
    tuple
        - z_min : float
            Minimum redshift of the array
        - z_max : float
            Maximum redshift of the array
        - z_stacking : float
            Redshift of the stacking frame
    """
        
            z_min, z_max, z_med = np.nanmin(redshift), np.nanmax(redshift), np.nanmedian(redshift)
            print (f"Minimum z: {np.round(z_min,4)}, Median z: {np.round(z_med,4)}, Maximum z: {np.round(z_max,4)}")
        
            if z_type == 'median_z':
                z_stacking = z_med ## median redshift
            elif z_type == 'minimum_z':
                z_stacking = z_min ## minimum redshift
            elif z_type == 'maximum_z':
                z_stacking = z_max ## maximum redshift
            elif z_type == 'rest_frame':
                z_stacking = 0.0 ## restframe
                if conservation == 'luminosity':
                    print (f"\n NOTE: When 'conservation'=='luminosity', and the stack is done at restframe, the output will be the restframe stacked LUMINOSITY spectra, in units [erg/s/AA]\n")
            elif type(z_type) == int or type(z_type) == float:
                z_stacking = float(z_type) ## redshift defined by the user
                print (f"Common redshift of the stacked spectrum defined by user: z={z_stacking}")
            else:
                raise NameError('z_type ', z_type, ' not supported!')
            
            return z_min, z_max, z_stacking
        
def z_sort(z_column_name, data_input):
    """Sort the input catalog by redshift.

    Parameters
    ----------
    z_column_name : str
        Name of the column containing redshifts.
    data_input : dict
        Input catalog (keys=column names, values=arrays).

    Returns
    -------
    dict
        Input catalog sorted by increasing redshift.
    """
    
    z_key = z_column_name
    z = np.asarray(data_input[z_key])

    # permutation that sorts by increasing redshift
    sort_idx = np.argsort(z)

    # apply permutation to all entries
    for key, value in data_input.items():
        data_input[key] = np.asarray(value)[sort_idx]
    
    return data_input


def build_wavelength_grid(wavelMin, wavelMax, config, z_stacking):
    """
    Build wavelength grid (centers and bin edges) for stacking.

    Parameters
    ----------
    wavelMin, wavelMax : float
        Wavelength range (Å)
    config : dict
        Configuration dictionary containing:
        - pixel_resampling_type : 'lambda', 'lambda_shifted', or 'log_lambda'
        - pixel_resampling      : Δλ (Å) or Δlog10(λ)
    z_stacking : float
        Reference redshift for stacking

    Returns
    -------
    wavelength_centers : ndarray
    wavelength_bins    : ndarray
    pixel_size         : float
        Δλ (Å) or Δlog10(λ), depending on sampling
    """

    pixel_type = config['pixel_resampling_type']

    if pixel_type in ['lambda', 'lambda_shifted']:
        
        if config['pixel_size_type'] == 'manual':
            pixel_size = config['pixel_resampling']
        else:
            pixel_size = sres.dlam_from_R(R=config['R'], lambda_ref=config['reference_lambda'], nsamp=config['nyquist_sampling'])

        if pixel_type == 'lambda_shifted':
            pixel_size /= (1.0 + z_stacking)

        npix = int(np.round((wavelMax - wavelMin) / pixel_size))
        wavelMax = wavelMin + npix * pixel_size

        wavelength_bins = wavelMin + np.arange(npix + 1) * pixel_size
        wavelength_centers = wavelength_bins[:-1] + 0.5 * pixel_size

    elif pixel_type == 'log_lambda':
        
        if config['pixel_size_type'] == 'manual':
            dloglam = sres.dloglam_from_dlam(dlam=config['pixel_resampling'], lambda_ref=config['reference_lambda'])
        else:
            dloglam = sres.dloglam_from_R(R=config['R'], nsamp=config['nyquist_sampling'])

        loglam_min = np.log10(wavelMin)
        loglam_max = np.log10(wavelMax)

        npix = int(np.round((loglam_max - loglam_min) / dloglam))
        loglam_max = loglam_min + npix * dloglam

        loglam_bins = loglam_min + np.arange(npix + 1) * dloglam
        loglam_centers = loglam_bins[:-1] + 0.5 * dloglam

        wavelength_bins = 10.0 ** loglam_bins
        wavelength_centers = 10.0 ** loglam_centers

        pixel_size = dloglam

    else:
        raise ValueError(f"Unknown pixel_resampling_type: {pixel_type}")

    return wavelength_centers, wavelength_bins, pixel_size


'''
def get_effective_cpu_limit():
    """
    Returns the number of CPUs effectively available to this process,
    accounting for cgroup limits (useful in containerized or scheduled environments).
    """
    try:
        with open('/sys/fs/cgroup/cpu/cpu.cfs_quota_us', 'r') as f:
            quota = int(f.read())
        with open('/sys/fs/cgroup/cpu/cpu.cfs_period_us', 'r') as f:
            period = int(f.read())

        if quota > 0 and period > 0:
            return max(1, quota // period)
        else:
            return os.cpu_count()  # No CPU limit set
    except Exception:
        return os.cpu_count()  # Default to full count if detection fails
'''


def get_effective_cpu_limit():
    """Return the effective CPU count considering cgroup and affinity limits.

    Accounts for cgroup v1 (cpu.cfs_quota_us/period), cgroup v2 (cpu.max),
    and CPU affinity settings. Useful in containerized/scheduled environments.

    Returns
    -------
    int
        Number of effectively available CPUs (at least 1).
    """
    import os
    # 1. Affinity
    try:
        affinity_count = len(os.sched_getaffinity(0))
    except (AttributeError, Exception):
        affinity_count = os.cpu_count() or 1

    limit = float('inf')

    # 2. check cgroup v2 (cpu.max)
    try:
        with open('/sys/fs/cgroup/cpu.max', 'r') as f:
            data = f.read().split()
            if len(data) == 2:
                max_val, period = data
                if max_val != 'max':
                    limit = int(max_val) / int(period)
    except (FileNotFoundError, ValueError, ZeroDivisionError):
        pass

    # 3. check cgroup v1 (quota/period)
    try:
        with open('/sys/fs/cgroup/cpu/cpu.cfs_quota_us', 'r') as q, \
             open('/sys/fs/cgroup/cpu/cpu.cfs_period_us', 'r') as p:
            quota = int(q.read())
            period = int(p.read())
            if quota > 0 and period > 0:
                limit = min(limit, quota / period)
    except (FileNotFoundError, ValueError):
        pass

    # Result: minimum between cgroup limit, affinity and physical total available
    final_cpus = min(limit, affinity_count)
    
    # Returns at least one core
    return max(1, int(final_cpus))



def output_units(config):
    """Determine output physical units from configuration.

    Parameters
    ----------
    config : dict
        Configuration dictionary.

    Returns
    -------
    tuple
        - out_unit : str
            Output unit string
        - out_unit_scale_factor : float
            Scaling factor for units
    """
    if config['spectra_normalization'] == 'no_normalization':
        if config['conservation'] == 'luminosity':
            out_unit = 'erg/s/cm2'
            out_unit_scale_factor = 1
        elif config['conservation'] == 'flux':
            out_unit = config['units']
            out_unit_scale_factor = config['units_scale_factor']
    else:
        out_unit = 'arbitrary units'
        out_unit_scale_factor = 1
    return out_unit, out_unit_scale_factor
        
def save_to_file(config, data_dict):
    """Save stacked spectra and metadata to a FITS file.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing output paths, normalization type, etc.
    data_dict : dict
        Dictionary containing stacking results: wavelengths, fluxes, dispersions,
        pixel counts, etc.

    Returns
    -------
    str
        Path to the generated FITS file.
    """
    # Prepare the stacking parameters metadata
    if config['spectra_normalization'] == 'interval':
        norm_interv_out = config['lambda_norm_rest']
    else:
        norm_interv_out = 'NOT APPLIED'
    
    out_unit, out_unit_scale_factor = output_units(config)
    
    # Primary HDU: metadata only
    primary_hdu = fits.PrimaryHDU()
    primary_hdu.header['INSTR'] = config['instrument_name']
    primary_hdu.header['SURVEY'] = config['survey_name']
    primary_hdu.header['GRISM'] = ','.join(config.get('grisms', []))
    primary_hdu.header['REDSHIFT'] = (data_dict['z_stacking'], 'z of the stacked spectrum')
    primary_hdu.header['NORMTYPE'] = (config['spectra_normalization'], 'type of spectra normalization')
    primary_hdu.header['NORMINTR'] = (f"{norm_interv_out}", 'lamda normalization')
    primary_hdu.header['RES_PIX'] = (data_dict['pixelResampling'], 'pixel size [Angstrom]')
    primary_hdu.header['R_BOOT'] = (config['bootstrapping_R'], 'R bootstrapping samples for err spec.')
    primary_hdu.header['UNITS'] = (out_unit,'physical unit of field')
    primary_hdu.header['FSCALE'] = (out_unit_scale_factor, 'Scaling factor')
    
    # Stacking results table
    cols = fits.ColDefs([
        fits.Column(name='wavelength', format='D', array=data_dict['wavelength_stacking']),
        fits.Column(name='spec16th', format='D', array=data_dict['stackPERC16th']),
        fits.Column(name='spec84th', format='D', array=data_dict['stackPERC84th']),
        fits.Column(name='spec98th', format='D', array=data_dict['stackPERC98th']),
        fits.Column(name='spec99th', format='D', array=data_dict['stackPERC99th']),
        fits.Column(name='specMedian', format='D', array=data_dict['stackSPmed']),
        fits.Column(name='specMedianDispersion', format='D', array=data_dict['stackDISPmed']),
        fits.Column(name='specMedianError', format='D', array=data_dict['stackERmed']),
        fits.Column(name='specMean', format='D', array=data_dict['stackSPmean']),
        fits.Column(name='specMeanDispersion', format='D', array=data_dict['stackDISPmean']),
        fits.Column(name='specMeanError', format='D', array=data_dict['stackERmean']),
        fits.Column(name='specGeometricMean', format='D', array=data_dict['stackSPgeomMean']),
        fits.Column(name='specGeometricMeanDispersion', format='D', array=data_dict['stackDISPgeomMean']),
        fits.Column(name='specGeometricMeanError', format='D', array=data_dict['stackERgeomMean']),
        fits.Column(name='specWeightedMean', format='D', array=data_dict['stackSPmeanWeighted']),
        fits.Column(name='specWeightedMeanDispersion', format='D', array=data_dict['stackDISPmeanWeighted']),
        fits.Column(name='specWeightedMeanError', format='D', array=data_dict['stackERmeanWeighted']),
        fits.Column(name='initialPixelCount', format='K', array=data_dict['initialPixelCount']),
        fits.Column(name='goodPixelCount', format='K', array=data_dict['goodPixelCount']),
        fits.Column(name='badPixelCount', format='K', array=data_dict['badPixelCount']),
        fits.Column(name='sigmaClippedCount', format='K', array=data_dict['sigmaClippedCount']),
    ])

    stacking_results_hdu = fits.BinTableHDU.from_columns(cols, name="STACKING_RESULTS")
    # Save to FITS file
    print (f"config['output_dir']: {config['output_dir']}, config['filename_out']:{config['filename_out']}")
    output_filename = f"{config['output_dir']}/{config['filename_out']}.fits"
    hdul = fits.HDUList([primary_hdu, stacking_results_hdu])
    hdul.writeto(output_filename, overwrite=True)

    print(f"FITS file '{output_filename}' has been saved.")
    
    return output_filename

