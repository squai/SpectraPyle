"""
Stacking statistics: mean, median, geometric mean, weighted mean, and bootstrap.

:func:`stack_statistics` computes all four stacking estimators and their
dispersions/errors from the sigma-clipped resampled array.
:func:`bootstrStack` estimates uncertainties via bootstrap resampling.
"""

import numpy as np
from multiprocessing import Pool
from functools import partial
import warnings
from tqdm import tqdm

from spectraPyle.utils.log import get_logger

logger = get_logger(__name__)
def stack_statistics(stackArr, stackArrErr):
    """
    Compute a suite of stacking statistics for spectra.

    Parameters
    ----------
    stackArr : ndarray
        Array of shape (N_pixels, N_spectra) containing the spectra
        to be stacked. NaNs are allowed and ignored where appropriate.
    stackArrErr : ndarray
        Array of the same shape containing 1-sigma uncertainties
        associated with `stackArr`. Used for weighted statistics.

    Returns
    -------
    stackSPmean : ndarray
        Arithmetic mean spectrum (NaN-ignoring).
    stackDISPmean : ndarray
        RMS scatter of spectra around the arithmetic mean.
    stackSPmed : ndarray
        Median spectrum.
    stackDISPmed : ndarray
        Robust scatter estimate based on MAD, scaled to Gaussian sigma
        (1.4826 * MAD).
    stackSPgeomMean : ndarray
        Geometric mean spectrum (computed only where all values are positive).
    stackDISPgeomMean : ndarray
        Intrinsic dispersion around the geometric mean (log-space RMS).
    stackSPmeanWeighted : ndarray
        Weighted mean spectrum (weights = 1 / err^2).
    stackDISPmeanWeighted : ndarray
        Intrinsic weighted dispersion (scatter of spectra around the
        weighted mean).
    stackERmeanWeighted : ndarray
        1-sigma uncertainty on the weighted mean spectrum.
    stackPERC16th : ndarray
        16th percentile of the distribution at each pixel.
    stackPERC84th : ndarray
        84th percentile of the distribution at each pixel.
    stackPERC98th : ndarray
        97.73th percentile (~2 sigma for a Gaussian).
    stackPERC99th : ndarray
        99.73th percentile (~3 sigma for a Gaussian).
    """

    # ---------- Arithmetic statistics ----------
    stackSPmean = np.nanmean(stackArr, axis=1)
    stackDISPmean = np.nanstd(stackArr, axis=1)

    # ---------- Median and robust dispersion ----------
    stackSPmed = np.nanmedian(stackArr, axis=1)
    MAD = np.nanmedian(np.abs(stackArr - stackSPmed[:, None]), axis=1)
    stackDISPmed = 1.4826 * MAD  # Gaussian-equivalent sigma

    # ---------- Geometric mean ----------
    stackSPgeomMean, stackDISPgeomMean = geomMean(stackArr)

    # ---------- Weighted mean ----------
    (stackSPmeanWeighted,
     stackDISPmeanWeighted,
     stackERmeanWeighted) = weighted_average(stackArr, stackArrErr)

    # ---------- Percentiles ----------
    stackPERC16th = np.nanpercentile(stackArr, 15.87, axis=1)
    stackPERC84th = np.nanpercentile(stackArr, 84.14, axis=1)
    stackPERC98th = np.nanpercentile(stackArr, 97.73, axis=1)
    stackPERC99th = np.nanpercentile(stackArr, 99.73, axis=1)

    return (
        stackSPmean,
        stackDISPmean,
        stackSPmed,
        stackDISPmed,
        stackSPgeomMean,
        stackDISPgeomMean,
        stackSPmeanWeighted,
        stackDISPmeanWeighted,
        stackERmeanWeighted,
        stackPERC16th,
        stackPERC84th,
        stackPERC98th,
        stackPERC99th,
    )

'''
def geomMean(arr, axis=1):
    """
    Compute geometric mean and intrinsic scatter (log-space RMS).

    Parameters
    ----------
    arr : array_like
        Input array. Must be strictly positive.
    axis : int or None
        Axis along which to compute the statistics.

    Returns
    -------
    meanGeo : ndarray
        Geometric mean.
    sigma_ln : ndarray
        RMS scatter in ln-space (intrinsic dispersion).
    """

    arr = np.asarray(arr)

    # pixels where all spectra are positive
    good = np.all(arr > 0, axis=1)

    meanGeo = np.full(arr.shape[0], np.nan)
    sigma_ln = np.full(arr.shape[0], np.nan)

    if not np.any(good):
        return meanGeo, sigma_ln

    log_arr = np.log(arr[good, :])

    mean_log = np.mean(log_arr, axis=1)
    meanGeo[good] = np.exp(mean_log)

    sigma_ln[good] = np.sqrt(
        np.mean((log_arr - mean_log[:, None])**2, axis=1)
    )

    return meanGeo, sigma_ln
'''

def geomMean(arr, axis=1):
    """Compute robust geometric mean and log-space scatter.

    Parameters
    ----------
    arr : ndarray
        Input array (can contain NaN, zero, and negative values).
    axis : int, optional
        Axis along which to compute (default: 1).

    Returns
    -------
    gm : ndarray
        Geometric mean.
    sigma_ln : ndarray
        Log-space RMS scatter (intrinsic dispersion).
    """

    arr = np.asarray(arr)

    # Valid values only
    valid = (arr > 0) & np.isfinite(arr)

    # Replace invalid with NaN
    safe = np.where(valid, arr, np.nan)

    # Log transform
    log_arr = np.log(safe)

    # Mean log
    mean_log = np.nanmean(log_arr, axis=axis)

    # Scatter in log space
    sigma_ln = np.nanstd(log_arr, axis=axis)

    # Back to linear space
    gm = np.exp(mean_log)

    return gm, sigma_ln
    
    
def weighted_average(stackArr, stackArrErr):
    """Compute weighted mean, dispersion, and 1-sigma uncertainty.

    Parameters
    ----------
    stackArr : ndarray (N_pixels, N_spectra)
        Spectra array.
    stackArrErr : ndarray (N_pixels, N_spectra)
        Error spectra array (weights = 1/err^2).

    Returns
    -------
    mean_w : ndarray
        Weighted mean spectrum.
    disp_w : ndarray
        Intrinsic weighted dispersion.
    err_mean_w : ndarray
        1-sigma uncertainty on the weighted mean.
    """

    arr = np.asarray(stackArr)
    err = np.asarray(stackArrErr)

    # mask invalid values
    mask = ~np.isfinite(arr) | ~np.isfinite(err) | (err <= 0)

    ma = np.ma.MaskedArray(arr, mask=mask)
    w = np.ma.MaskedArray(1.0 / err**2, mask=mask)

    # weighted mean
    mean_w = np.ma.average(ma, weights=w, axis=1).filled(np.nan)

    # intrinsic weighted dispersion
    diff = ma - mean_w[:, None]
    disp_w = np.sqrt(
        np.ma.average(diff**2, weights=w, axis=1)
    ).filled(np.nan)

    # uncertainty on the mean
    err_mean_w = np.sqrt(1.0 / np.ma.sum(w, axis=1)).filled(np.nan)

    return mean_w, disp_w, err_mean_w

'''
def bootstrap_iteration(args):
    """Single iteration of the bootstrap."""
    arr, M, repl, weight = args
    sample = np.random.choice(a=M, size=M, replace=repl, p=weight)
    arrSample = arr[:, sample]
    sumArr = np.nansum(arrSample, axis=1)
    meanArr = np.nanmean(arrSample, axis=1)
    medArr = np.nanmedian(arrSample, axis=1)
    geometricMeanArr, _ = geomMean(arrSample)
    return sumArr, meanArr, medArr, geometricMeanArr

def bootstrStack(arr, R=250, repl=True, weight=None, n_processes=None):
    """
    Bootstrapping function with multiprocessing.
    """
    print(f'Running bootstrap ({R} times) with multiprocessing...')
    N, M = np.size(arr, 0), np.size(arr, 1)
    
    # Prepare arguments for each bootstrap iteration
    args = [(arr, M, repl, weight) for _ in range(R)]
    
    # Use multiprocessing Pool
    with Pool(processes=n_processes) as pool:
        results = list(tqdm(pool.imap(bootstrap_iteration, args), 
                            total=R, desc="Bootstrap sampled"))
    
    # Combine results
    sumArr = np.array([result[0] for result in results]).T
    meanArr = np.array([result[1] for result in results]).T
    medArr = np.array([result[2] for result in results]).T
    geometricMeanArr = np.array([result[3] for result in results]).T

    # Calculate statistics
    bootstrMeanSpec = np.nanmean(meanArr, axis=1)
    bootstrMeanSpecSig = np.nanstd(meanArr, axis=1)

    bootstrMedSpec = np.nanmedian(medArr, axis=1)
    MAD = np.nanmedian(np.abs((medArr.T - bootstrMedSpec).T), axis=1)
    bootstrMedSpecSig = 1.482 * MAD

    bootstrGeomMeanSpec, bootstrGeomMeanSpecSig = geomMean(geometricMeanArr)

    print('Bootstrap completed!')
    return bootstrMeanSpec, bootstrMeanSpecSig, bootstrMedSpec, bootstrMedSpecSig, bootstrGeomMeanSpec, bootstrGeomMeanSpecSig
'''



# =========================================================
# SINGLE BOOTSTRAP ITERATION
# =========================================================

def bootstrap_iteration(idx_sample, arr):
    """Perform a single bootstrap resampling iteration.

    Parameters
    ----------
    idx_sample : ndarray
        Indices of selected spectra (size M).
    arr : ndarray (Npix, Nspec)
        Input spectra array.

    Returns
    -------
    tuple
        Four arrays: (sum_arr, mean_arr, med_arr, geom_arr)

        - sum_arr : ndarray
            Sum of resampled spectra
        - mean_arr : ndarray
            Mean of resampled spectra
        - med_arr : ndarray
            Median of resampled spectra
        - geom_arr : ndarray
            Geometric mean of resampled spectra
    """

    arr_sample = arr[:, idx_sample]

    sum_arr = np.nansum(arr_sample, axis=1)
    mean_arr = np.nanmean(arr_sample, axis=1)
    med_arr = np.nanmedian(arr_sample, axis=1)
    geom_arr, _ = geomMean(arr_sample)

    return sum_arr, mean_arr, med_arr, geom_arr


# =========================================================
# MAIN BOOTSTRAP FUNCTION
# =========================================================

def bootstrStack(
    arr,
    R=250,
    replace=True,
    weights=None,
    n_processes=None,
    random_state=None,
):
    """Bootstrap resampling of stacked spectra.

    Parameters
    ----------
    arr : ndarray (Npix, Nspec)
        Input spectra array.
    R : int, optional
        Number of bootstrap realizations (default: 250).
    replace : bool, optional
        Sampling with replacement (default: True).
    weights : ndarray or None, optional
        Sampling probabilities for each spectrum.
    n_processes : int or None, optional
        Number of processes for parallelization (None = serial).
    random_state : int or None, optional
        Seed for reproducibility.

    Returns
    -------
    tuple
        Six arrays: (mean_spec, mean_err, med_spec, med_err, geom_spec, geom_err)

        - mean_spec : ndarray
            Mean spectrum from bootstrap samples
        - mean_err : ndarray
            Uncertainty on mean spectrum
        - med_spec : ndarray
            Median spectrum from bootstrap samples
        - med_err : ndarray
            Uncertainty on median spectrum
        - geom_spec : ndarray
            Geometric mean spectrum from bootstrap samples
        - geom_err : ndarray
            Uncertainty on geometric mean spectrum
    """

    print(f"Running bootstrap (R={R})")

    arr = np.asarray(arr)
    Npix, Nspec = arr.shape

    rng = np.random.default_rng(random_state)

    # -----------------------------------------------------
    # Generate bootstrap indices ONCE (important!)
    # -----------------------------------------------------
    indices = [
        rng.choice(Nspec, size=Nspec, replace=replace, p=weights)
        for _ in range(R)
    ]

    # -----------------------------------------------------
    # Run iterations
    # -----------------------------------------------------
    if n_processes and n_processes > 1:
        print(f"Using multiprocessing ({n_processes} CPUs)")

        with Pool(n_processes) as pool:
            results = list(
                tqdm(
                    pool.imap(partial(bootstrap_iteration, arr=arr), indices),
                    total=R,
                    desc="Bootstrap",
                )
            )
    else:
        results = [
            bootstrap_iteration(idx, arr)
            for idx in tqdm(indices, desc="Bootstrap")
        ]

    # -----------------------------------------------------
    # Collect results
    # -----------------------------------------------------
    sumArr = np.array([r[0] for r in results]).T
    meanArr = np.array([r[1] for r in results]).T
    medArr = np.array([r[2] for r in results]).T
    geomArr = np.array([r[3] for r in results]).T

    # -----------------------------------------------------
    # Final statistics
    # -----------------------------------------------------

    # ---- MEAN ----
    mean_spec = np.nanmean(meanArr, axis=1)
    mean_err = np.nanstd(meanArr, axis=1)

    # ---- MEDIAN ----
    med_spec = np.nanmedian(medArr, axis=1)

    med_p16 = np.nanpercentile(medArr, 16, axis=1)
    med_p84 = np.nanpercentile(medArr, 84, axis=1)

    #med_err_low = med_spec - med_p16
    #med_err_high = med_p84 - med_spec
    
    med_err = 0.5 * (med_p84 - med_p16)
    
    # ---- GEOMETRIC MEAN ----
    geom_p16 = np.nanpercentile(geomArr, 16, axis=1)
    geom_p84 = np.nanpercentile(geomArr, 84, axis=1)

    geom_spec = np.nanmedian(geomArr, axis=1)
    #geom_err_low = geom_spec - geom_p16
    #geom_err_high = geom_p84 - geom_spec
    
    geom_err = 0.5 * (geom_p84 - geom_p16)

    print("Bootstrap completed")

    return mean_spec,mean_err,med_spec,med_err,geom_spec,geom_err


