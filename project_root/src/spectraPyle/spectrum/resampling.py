"""
Wavelength grid resampling.

Resamples individual spectra onto the common stacking wavelength grid using
linear or logarithmic binning, as configured by ``config['pixel_resampling_type']``.
"""

import numpy as np
from scipy.stats import binned_statistic
import warnings

from spectraPyle.utils.log import get_logger

logger = get_logger(__name__)

def resamplingSpecFluxCons_v0(lbd, flux, lambdaInterp):
    """Resample a step-function spectrum while conserving flux.

    Parameters
    ----------
    lbd : ndarray
        Original wavelength array (pixel centers).
    flux : ndarray
        Original flux array.
    lambdaInterp : ndarray
        New wavelength grid (bin edges, length N+1).

    Returns
    -------
    ndarray
        Resampled flux array (length N).
    """
    
    # Step 1: Compute pixel edges from pixel centers
    lbd_edges = np.zeros(len(lbd) + 1)
    lbd_edges[1:-1] = 0.5 * (lbd[1:] + lbd[:-1])
    lbd_edges[0] = lbd[0] - 0.5 * (lbd[1] - lbd[0])
    lbd_edges[-1] = lbd[-1] + 0.5 * (lbd[-1] - lbd[-2])
    
    # Step 2: Construct fine sampling within each original pixel
    fine_dx = 0.01  # 0.01 Angstrom resolution

    x_fine = []
    y_fine = []

    for i in range(len(flux)):
        start, end = lbd_edges[i], lbd_edges[i+1]
        x_seg = np.arange(start, end, fine_dx)
        if len(x_seg) == 0:
            x_seg = np.array([(start + end) / 2])  # fallback
        x_fine.append(x_seg)
        y_fine.append(np.full_like(x_seg, flux[i]))

    x_fine = np.concatenate(x_fine)
    y_fine = np.concatenate(y_fine)
    
    # Step 3: Integrate within new bins
    flux_integrated, _, _ = binned_statistic(x_fine, y_fine, statistic="sum", bins=lambdaInterp)
    dx_fine = np.mean(np.diff(x_fine))
    
    # Step 4: Normalize to step function
    bin_widths = np.diff(lambdaInterp)
    flux_resampled = flux_integrated * dx_fine / bin_widths

    # Optional: Mask out bins outside original range
    min_lbd = lbd_edges[0]
    max_lbd = lbd_edges[-1]
    flux_resampled[(lambdaInterp[:-1] < min_lbd) | (lambdaInterp[:-1] > max_lbd)] = np.inf
    
    #print (f"OLD flux_out shape: {flux_resampled.shape}, flux_out: {flux_resampled}")
    
    return flux_resampled



def resamplingSpecFluxCons(lbd, flux, var, lambdaInterp):
    """
    Fully vectorized 1D resampling with variance propagation. Adapted from Fruchter & Hook 2002
    Produces flux density per unit wavelength.

    Parameters
    ----------
    lbd : (N_in,) array
        Input wavelength pixel centers
    flux : (N_in,) array
        Flux density per input pixel
    var : (N_in,) array
        Variance per input pixel
    lambdaInterp : (N_out+1,) array
        Output wavelength bin edges

    Returns
    -------
    flux_out : (N_out,) array
        flux density (per unit wavelength) over the new common wavelength grid
    err_out : (N_out,) array
        error density (per unit wavelength) over the new common wavelength grid
    """
    
    # --- sanity checks ---
    '''
    if not np.all(np.isfinite(flux)):
        warnings.warn("Input flux contains NaNs; they will be ignored", RuntimeWarning)

    if not np.all(np.isfinite(var)):
        warnings.warn("Input variance contains NaNs; they will be ignored", RuntimeWarning)
    '''

    # --- Input pixel edges ---
    lbd_edges = np.zeros(len(lbd) + 1)
    lbd_edges[1:-1] = 0.5 * (lbd[1:] + lbd[:-1])
    lbd_edges[0] = lbd[0] - 0.5 * (lbd[1] - lbd[0])
    lbd_edges[-1] = lbd[-1] + 0.5 * (lbd[-1] - lbd[-2])

    delta_p = np.diff(lbd_edges)                      # Width of input pixels
    p_lo = lbd_edges[:-1][None, :]                    # Shape (1, N_in)
    p_hi = lbd_edges[1:][None, :]                     # Shape (1, N_in)

    # --- Output bins ---
    j_lo = lambdaInterp[:-1][:, None]                 # Shape (N_out, 1)
    j_hi = lambdaInterp[1:][:, None]                  # Shape (N_out, 1)
    delta_j = (j_hi - j_lo).flatten()                # Output bin widths, shape (N_out,)
    
    # --- Cleaning from NaN values  ---
    good = np.isfinite(flux) & np.isfinite(var)

    flux_clean = np.where(good, flux, 0.0)
    var_clean  = np.where(good, var,  0.0)
    
    # --- Fractional overlaps ---
    overlap = np.maximum(0.0, np.minimum(p_hi, j_hi) - np.maximum(p_lo, j_lo))  # (N_out, N_in)
    
    # --- Weighted sums ---
    flux_sum = overlap @ flux_clean                          # (N_out,)
    var_sum  = (overlap**2) @ var_clean                     # (N_out,)
    
    # --- by construction, bad pixels are those with flux = 0, converting them to NaN for a correct bad pixel count  ---
    var_sum = np.where(flux_sum == 0.0, np.nan, var_sum)
    flux_sum = np.where(flux_sum == 0.0, np.nan, flux_sum)

    # --- Divide by output bin width to get flux density per unit wavelength ---
    flux_out = flux_sum / delta_j
    err_out  = np.sqrt(var_sum) / delta_j
    
    # Optional: Mask out bins outside original range
    min_lbd = lbd_edges[0]
    max_lbd = lbd_edges[-1]
    flux_out[(lambdaInterp[:-1] < min_lbd) | (lambdaInterp[:-1] > max_lbd)] = np.inf
    err_out[(lambdaInterp[:-1] < min_lbd) | (lambdaInterp[:-1] > max_lbd)] = np.inf
    
    #print (f"NEW flux_out shape: {flux_out.shape}, flux_out: {flux_out}")
    return flux_out, err_out


def dloglam_from_R(R, nsamp=5):
    """
    Compute logarithmic wavelength step Δlog10(λ) from resolving power.

    Parameters
    ----------
    R : float
        Spectral resolving power (λ / Δλ_FWHM)
    nsamp : float, optional
        Number of pixels per resolution element (default: 5)

    Returns
    -------
    dloglam : float
        Logarithmic wavelength step Δlog10(λ)
    """
    if R <= 0:
        raise ValueError("R must be positive")
    if nsamp <= 0:
        raise ValueError("nsamp must be positive")

    return 1.0 / (R * nsamp * np.log(10.0))

def dloglam_from_dlam(dlam, lambda_ref):
    """
    Compute logarithmic wavelength step Δlog10(λ) from resolving power.
    
    Δlog10𝜆=Δ𝜆/𝜆_ref*ln10
     
    Parameters
    ----------
    dlam : float
           Linear wavelength step (Å)
    lambda_ref : float
        Reference wavelength (Å)

    Returns
    -------
    dloglam : float
        Logarithmic wavelength step Δlog10(λ)
    """
    if dlam <= 0:
        raise ValueError("dlam must be positive")
    

    return dlam / (lambda_ref * np.log(10.0))


def dlam_from_R(R, lambda_ref, nsamp=5):
    """
    Δλ (Å) from resolving power at a reference wavelength.

    Parameters
    ----------
    R : float
        Spectral resolving power (λ / Δλ_FWHM)
    lambda_ref : float
        Reference wavelength (Å)
    nsamp : float, optional
        Number of pixels per resolution element (default: 5)

    Returns
    -------
    dlam : float
        Linear wavelength step (Å)
    """
    if R <= 0:
        raise ValueError("R must be positive")
    if nsamp <= 0:
        raise ValueError("nsamp must be positive")
    if lambda_ref <= 0:
        raise ValueError("lambda_ref must be positive")

    return lambda_ref / (R * nsamp)



