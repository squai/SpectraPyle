#############################################################################
## HISTORY:
## v3.1 normalization.py: returning the normalization factor used
#############################################################################

import numpy as np

"""
def normSpecInterv (specid, z, lbd, flux, error, lambdamin_norm, lambdamax_norm):
    vecnorm = flux[(lbd>=lambdamin_norm)*(lbd<=lambdamax_norm)] ## Calculate normalization and normalize individual spectra
    norm=np.nanmedian(vecnorm)
    if np.isnan(norm):
        norm = np.nanmedian(flux)
        print (f"WARNING: normalization failure for {str(specid)} at z {np.round(z,3)}: Normaliz. factor = NaN. USING norm=median(flux) instead!")
        
    fluxNorm = flux / norm
    errNorm = error / norm
    return fluxNorm, errNorm, norm
"""

def normSpecInterv(specid, lbd, flux, error, lambdamin_norm, lambdamax_norm, norm_stat):
        
    vecnorm = flux[(lbd >= lambdamin_norm) & (lbd <= lambdamax_norm)]
    
    if (lambdamin_norm < np.nanmin(lbd)) or (lambdamax_norm > np.nanmax(lbd)):
        print (f"WARNING normalization interval [{lambdamin_norm}, {lambdamax_norm}] [$\AA$] partially outside the wavelength range of the spectrum [{np.round(lbd[0],2)},{np.round(lbd[-1],2)}] [$\AA$].")

    if len(vecnorm) == 0:
        raise ValueError(fr"Normalization failure for {str(specid)}: normalization interval [{lambdamin_norm}, {lambdamax_norm}] [$\AA$] outside the wavelength range of the spectrum [{np.round(lbd[0],2)},{np.round(lbd[-1],2)}] [$\AA$]. Skipping this spectrum.")
    
    if np.all(np.isnan(vecnorm)):
        raise ValueError(fr"Normalization failure for {str(specid)}: no valid flux values in the normalization interval [ {lambdamin_norm}, {lambdamax_norm}] [$\AA$]. Skipping this spectrum.")
    if norm_stat == 'median':
        norm = np.nanmedian(vecnorm)
    elif norm_stat == 'mean':
        norm = np.nanmean(vecnorm)
    elif norm_stat == 'maximum':
        norm = np.nanmax(vecnorm)
    elif norm_stat == 'minimum':
        norm = np.nanmax(vecnorm)
    else:
        raise ValueError('Normalization failure: statistics {norm_stat} to be applied to the normalization interval not understood or implemented yet.')
        

    if np.isnan(norm):
        raise ValueError(fr"Normalization failure for {str(specid)}: median flux is NaN in the normalization interval [ {lambdamin_norm}, {lambdamax_norm}] [$\AA$]. Skipping this spectrum")

    fluxNorm = flux / norm
    errNorm = error / norm
    return fluxNorm, errNorm, norm


def normSpecMed (lbd, flux, error):
    norm = np.nanmedian(flux)
    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm

def normSpecIntegrMean (lbd, flux, error):
    diff = np.full_like(lbd, 0, dtype=float)
    diff[:-1] = np.diff(lbd)
    diff[-1] = diff[-2]
    norm = np.nansum(flux*diff) / (lbd[-1]-lbd[0]) ## option n.1 
    #norm = np.nansum(flux) / len(lbd) ## option n.2 equivalent to option n1
    
    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm
    
def normSpecCustom (lbd, flux, error, norm):
    ## it requires a custom normalization parameter to be provided in the catalogue datafile
    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm


def francis1991_normalize(
    stackArr,
    stackArrErr,
    min_overlap=50,
    norm_stat="median",
):
    """
    Francis+1991 incremental normalization of fully assembled spectra.

    Parameters
    ----------
    stackArr : ndarray (Npix, Nspec)
        Flux density array (NaN = invalid)
    stackArrErr : ndarray (Npix, Nspec)
        1-sigma error array (NaN = invalid)
    min_overlap : int
        Minimum number of overlapping pixels for normalization
    norm_stat : {'median', 'mean'}
        Statistic used for normalization (default: median)

    Returns
    -------
    norm_flux : ndarray (Npix, Nspec)
        Normalized flux array
    norm_err : ndarray (Npix, Nspec)
        Normalized 1-sigma error array
    """

    stat_func = np.nanmedian if norm_stat == "median" else np.nanmean

    Npix, Nspec = stackArr.shape

    norm_flux = np.full_like(stackArr, np.nan)
    norm_err = np.full_like(stackArrErr, np.nan)

    # --------------------------------------------------
    # Initialize reference composite using first spectrum
    # --------------------------------------------------
    f0 = stackArr[:, 0]
    e0 = stackArrErr[:, 0]

    valid0 = np.isfinite(f0) & np.isfinite(e0)
    if valid0.sum() == 0:
        raise ValueError("First spectrum has no valid pixels")

    alpha0 = stat_func(f0[valid0])

    norm_flux[:, 0] = f0 / alpha0
    norm_err[:, 0] = e0 / alpha0

    ref_flux = norm_flux[:, 0].copy()
    ref_var = norm_err[:, 0] ** 2

    # --------------------------------------------------
    # Incremental normalization
    # --------------------------------------------------
    for i in range(1, Nspec):

        fi = stackArr[:, i]
        ei = stackArrErr[:, i]

        valid_i = np.isfinite(fi) & np.isfinite(ei)
        valid_r = np.isfinite(ref_flux) & np.isfinite(ref_var)

        overlap = valid_i & valid_r

        if overlap.sum() < min_overlap:
            continue

        ref_stat = stat_func(ref_flux[overlap])
        cur_stat = stat_func(fi[overlap])

        alpha = ref_stat / cur_stat

        norm_flux[:, i] = alpha * fi
        norm_err[:, i] = alpha * ei

        # --- update reference composite ---
        vi = norm_err[:, i] ** 2
        both = overlap

        w_old = 1.0 / ref_var[both]
        w_new = 1.0 / vi[both]

        ref_flux[both] = (
            ref_flux[both] * w_old + norm_flux[both, i] * w_new
        ) / (w_old + w_new)

        ref_var[both] = 1.0 / (w_old + w_new)

        # add new-only pixels
        new_only = valid_i & ~valid_r
        ref_flux[new_only] = norm_flux[new_only, i]
        ref_var[new_only] = vi[new_only]

    return norm_flux, norm_err
