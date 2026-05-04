"""
Flux normalization for stacking.

Provides multiple normalization strategies controlled by ``config['norm_type']``,
including median-flux normalization over a wavelength range, and the
:func:`francis1991_normalize` template-based method (Francis et al. 1991).
"""

import numpy as np

from spectraPyle.utils.log import get_logger

logger = get_logger(__name__)

def normSpecInterv(specid, lbd, flux, error, lambdamin_norm, lambdamax_norm, norm_stat):
    """Normalize spectrum over a wavelength interval.

    Parameters
    ----------
    specid : str or int
        Spectrum identifier (for error messages).
    lbd : ndarray
        Wavelength array.
    flux : ndarray
        Flux array.
    error : ndarray
        Flux error array.
    lambdamin_norm : float
        Minimum wavelength of normalization interval (Å).
    lambdamax_norm : float
        Maximum wavelength of normalization interval (Å).
    norm_stat : {'median', 'mean', 'maximum', 'minimum'}
        Statistic to compute over the interval.

    Returns
    -------
    tuple
        - fluxNorm : ndarray
            Normalized flux
        - errNorm : ndarray
            Normalized error
        - norm : float
            Normalization value used

    Raises
    ------
    ValueError
        If normalization interval is outside wavelength range or contains no valid data.
    """

    vecnorm = flux[(lbd >= lambdamin_norm) & (lbd <= lambdamax_norm)]

    if (lambdamin_norm < np.nanmin(lbd)) or (lambdamax_norm > np.nanmax(lbd)):
        print (f"WARNING normalization interval [{lambdamin_norm}, {lambdamax_norm}] [$\AA$] partially outside the wavelength range of the spectrum [{np.round(lbd[0],2)},{np.round(lbd[-1],2)}] [$\AA$].")

    if len(vecnorm) == 0:
        raise ValueError(fr"Normalization failure for {str(specid)}: normalization interval [{lambdamin_norm}, {lambdamax_norm}] [$\AA$] outside the wavelength range of the spectrum [{np.round(lbd[0],2)},{np.round(lbd[-1],2)}] [$\AA$].")

    if np.all(np.isnan(vecnorm)):
        raise ValueError(fr"Normalization failure for {str(specid)}: no valid flux values in the normalization interval [ {lambdamin_norm}, {lambdamax_norm}] [$\AA$].")
    if norm_stat == 'median':
        norm = np.nanmedian(vecnorm)
    elif norm_stat == 'mean':
        norm = np.nanmean(vecnorm)
    elif norm_stat == 'maximum':
        norm = np.nanmax(vecnorm)
    elif norm_stat == 'minimum':
        norm = np.nanmin(vecnorm)
    else:
        raise ValueError(f"Normalization failure: statistics '{norm_stat}' to be applied to the normalization interval not understood or implemented yet.")

    if (not np.isfinite(norm)) or (norm <= 0):
        raise ValueError(
            fr"Normalization failure: invalid normalization value ({norm}) "
            fr"in interval [{lambdamin_norm}, {lambdamax_norm}] [$\AA$]."
        )

    fluxNorm = flux / norm
    errNorm = error / norm
    return fluxNorm, errNorm, norm


def normSpecMed(lbd, flux, error):
    """Normalize spectrum by median flux.

    Parameters
    ----------
    lbd : ndarray
        Wavelength array (unused, for API consistency).
    flux : ndarray
        Flux array.
    error : ndarray
        Flux error array.

    Returns
    -------
    tuple
        - fluxNorm : ndarray
            Normalized flux
        - errNorm : ndarray
            Normalized error
        - norm : float
            Median flux value used for normalization
    """
    norm = np.nanmedian(flux)

    if (not np.isfinite(norm)) or (norm <= 0):
        raise ValueError(
            fr"Normalization failure: invalid normalization value ({norm}) "
            )

    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm

def normSpecIntegrMean(lbd, flux, error):
    """Normalize spectrum by integrated mean flux.

    Parameters
    ----------
    lbd : ndarray
        Wavelength array.
    flux : ndarray
        Flux array.
    error : ndarray
        Flux error array.

    Returns
    -------
    tuple
        - fluxNorm : ndarray
            Normalized flux
        - errNorm : ndarray
            Normalized error
        - norm : float
            Integrated mean flux value
    """
    diff = np.full_like(lbd, 0, dtype=float)
    diff[:-1] = np.diff(lbd)
    diff[-1] = diff[-2]
    norm = np.nansum(flux*diff) / (lbd[-1]-lbd[0]) ## option n.1
    #norm = np.nansum(flux) / len(lbd) ## option n.2 equivalent to option n1

    if (not np.isfinite(norm)) or (norm <= 0):
        raise ValueError(
            fr"Normalization failure: invalid normalization value ({norm}) "
            )

    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm

def normSpecCustom(lbd, flux, error, norm):
    """Normalize a spectrum by a caller-supplied scalar value.

    The normalization scalar ``norm`` is typically read from a catalog column
    (e.g. a photometric flux in a reference band). Use
    ``spectra_normalization: "custom"`` in the configuration and set
    ``catalog_columns.custom_normalization.custom_column_name`` to the column name.

    Parameters
    ----------
    lbd : array-like
        Wavelength array (Å). Accepted for API consistency but not used.
    flux : ndarray
        Flux array.
    error : ndarray
        Error (1-sigma) array.
    norm : float
        Normalization scalar. Must be finite and > 0.

    Returns
    -------
    fluxNorm : ndarray
        Normalized flux array.
    errorNorm : ndarray
        Normalized error array.
    norm : float
        The normalization value applied.

    Raises
    ------
    ValueError
        If ``norm`` is not finite or is ≤ 0.
    """
    if (not np.isfinite(norm)) or (norm <= 0):
        raise ValueError(
            fr"Normalization failure: invalid normalization value ({norm}) "
            )

    fluxNorm = flux / norm
    errorNorm = error / norm
    return fluxNorm, errorNorm, norm

def francis1991_normalize(
    stackArr,
    stackArrErr,
    min_overlap=50,
    norm_stat="median",
    sigma_clip=3.0,
    max_iter_clip=3,
    feature_mask=None,
    eps=1e-10,
):
    """
    Robust Francis-style normalization with sigma-clipped overlap scaling.

    Parameters
    ----------
    stackArr : ndarray (Npix, Nspec)
        Flux array
    stackArrErr : ndarray (Npix, Nspec)
        1-sigma errors
    min_overlap : int
        Minimum overlap for normalization
    norm_stat : {'median', 'mean'}
        Statistic used after clipping
    feature_mask : ndarray (Npix,) or None
        True = exclude from normalization
    sigma_clip : float
        Sigma clipping threshold (default: 3)
    max_iter_clip : int
        Max iterations for clipping
    eps : float
        Small value to avoid division issues

    Returns
    -------
    norm_flux : ndarray
    norm_err : ndarray
    """

    print("\nStarting stacking Francis 1991-like", flush=True)

    stat_func = np.nanmedian if norm_stat == "median" else np.nanmean

    Npix, Nspec = stackArr.shape

    norm_flux = np.full_like(stackArr, np.nan)
    norm_err = np.full_like(stackArrErr, np.nan)

    # --------------------------------------------------
    # Feature mask
    # --------------------------------------------------
    if feature_mask is None:
        feature_mask = np.zeros(Npix, dtype=bool)

    usable = (
        np.isfinite(stackArr)
        & np.isfinite(stackArrErr)
        & (~feature_mask[:, None])
    )

    counts = usable.sum(axis=0)

    # --------------------------------------------------
    # anchor = first (lowest-z) spectrum with enough pixels
    # --------------------------------------------------
    anchor = None
    for i in range(Nspec):
        if counts[i] >= min_overlap:
            anchor = i
            break

    if anchor is None:
        raise ValueError("No valid anchor spectrum found")

    print(f"Francis 1991-like stacked: Anchor spectrum index: {anchor}", flush=True)

    # --------------------------------------------------
    # Initialize reference
    # --------------------------------------------------
    f0 = stackArr[:, anchor]
    e0 = stackArrErr[:, anchor]

    valid0 = usable[:, anchor]

    alpha0 = stat_func(f0[valid0])

    norm_flux[:, anchor] = f0 / alpha0
    norm_err[:, anchor] = e0 / alpha0

    ref_flux = norm_flux[:, anchor].copy()

    ref_count = np.zeros(Npix)
    ref_count[np.isfinite(ref_flux)] = 1

    # --------------------------------------------------
    # Robust alpha estimator
    # --------------------------------------------------

    def sig_clip_alpha(vals):
        for _ in range(max_iter_clip):
            mu = np.nanmedian(vals)
            std = np.nanstd(vals)

            if std == 0 or not np.isfinite(std):
                break

            good = np.abs(vals - mu) < sigma_clip * std

            if good.sum() == len(vals):
                break

            vals = vals[good]

            if vals.size < min_overlap:
                return np.nan
        return vals

    def robust_alpha(ref_vals, cur_vals):

        mask = (
            np.isfinite(ref_vals)
            & np.isfinite(cur_vals)
            & (np.abs(cur_vals) > eps)
        )

        if mask.sum() < min_overlap:
            return np.nan

        ## median of ratio
        #ratio = ref_vals[mask] / cur_vals[mask]
        #vals = ratio.copy()
        #vals = sig_clip_alpha(vals)
        #return stat_func(vals)

        ## ratio of medians
        ref_vals_sc = sig_clip_alpha(ref_vals[mask])
        cur_vals_sc = sig_clip_alpha(cur_vals[mask])

        ## with sigma clipping
        #return stat_func(ref_vals_sc) / stat_func(cur_vals_sc)

        ## no sigma clipping
        return stat_func(ref_vals[mask]) / stat_func(cur_vals[mask])

    # --------------------------------------------------
    # Incremental normalization
    # --------------------------------------------------
    for i in range(anchor + 1, Nspec):

        fi = stackArr[:, i]
        ei = stackArrErr[:, i]

        valid_i = np.isfinite(fi) & np.isfinite(ei)
        valid_r = np.isfinite(ref_flux)

        overlap = valid_i & valid_r & (~feature_mask)

        if overlap.sum() < min_overlap:
            continue

        ref_vals = ref_flux[overlap]
        cur_vals = fi[overlap]

        alpha = robust_alpha(ref_vals, cur_vals)

        if not np.isfinite(alpha) or (alpha < 0) or (alpha > 1000):
            print (fr"Normalization failure for spectrum N.{str(i)}: invalid normalization value ({alpha}).", flush=True)
            continue

        # normalize
        norm_flux[:, i] = alpha * fi
        norm_err[:, i] = alpha * ei

        # update reference (count-weighted)
        both = overlap

        ref_flux[both] = (
            ref_flux[both] * ref_count[both] + norm_flux[both, i]
        ) / (ref_count[both] + 1)

        ref_count[both] += 1

        # add new pixels
        new_only = valid_i & (~valid_r)

        ref_flux[new_only] = norm_flux[new_only, i]
        ref_count[new_only] = 1

    return norm_flux, norm_err
