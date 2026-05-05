"""
Stacking statistics: mean, median, geometric mean (lenient & strict), mode, weighted mean, and bootstrap.

:func:`stack_statistics` computes six stacking estimators and their dispersions/errors from the
sigma-clipped resampled array:

- **Arithmetic mean** — classical average, sensitive to outliers
- **Median** — robust estimator, dispersion via MAD × 1.4826
- **Geometric mean (lenient)** — silently excludes non-positive flux; uses positive values per pixel
- **Geometric mean (strict)** — requires all positive; returns NaN if any value ≤ 0 per pixel
- **Mode (HSM)** — Half-Sample Mode estimator (Bickel 2002), parameter-free, robust
- **Weighted mean** — inverse-variance weights; accounts for per-spectrum uncertainties
- **Percentiles** — 16th, 84th (±1σ), 98th (≈2σ), 99th (≈3σ) for distribution inspection

:func:`bootstrStack` estimates uncertainties via bootstrap resampling (percentile 16–84).
All statistics support bootstrap error estimation or analytical formulas.
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
    geomMeanPixelCount : ndarray
        Number of pixels with positive finite flux that entered the
        geometric mean computation, per wavelength bin.
    stackSPmode : ndarray
        Mode spectrum (Half-Sample Mode estimator, parameter-free).
    stackDISPmode : ndarray
        Dispersion around the mode (MAD × 1.4826).
    stackSPgeomMeanStrict : ndarray
        Strict geometric mean (NaN if any finite value ≤ 0 per bin).
    stackDISPgeomMeanStrict : ndarray
        Log-space dispersion for strict geometric mean (σ_ln).
    """

    # ---------- Arithmetic statistics ----------
    stackSPmean = np.nanmean(stackArr, axis=1)
    stackDISPmean = np.nanstd(stackArr, axis=1)

    # ---------- Median and robust dispersion ----------
    stackSPmed = np.nanmedian(stackArr, axis=1)
    MAD = np.nanmedian(np.abs(stackArr - stackSPmed[:, None]), axis=1)
    stackDISPmed = 1.4826 * MAD  # Gaussian-equivalent sigma

    # ---------- Geometric mean ----------
    stackSPgeomMean, stackDISPgeomMean, geomMeanPixelCount = geomMean(stackArr)

    # ---------- Weighted mean ----------
    (stackSPmeanWeighted,
     stackDISPmeanWeighted,
     stackERmeanWeighted) = weighted_average(stackArr, stackArrErr)

    # ---------- Percentiles ----------
    stackPERC16th = np.nanpercentile(stackArr, 15.87, axis=1)
    stackPERC84th = np.nanpercentile(stackArr, 84.14, axis=1)
    stackPERC98th = np.nanpercentile(stackArr, 97.73, axis=1)
    stackPERC99th = np.nanpercentile(stackArr, 99.73, axis=1)

    # ---------- Mode (HSM) ----------
    stackSPmode, stackDISPmode = half_sample_mode(stackArr)

    # ---------- Strict geometric mean ----------
    stackSPgeomMeanStrict, stackDISPgeomMeanStrict = geomMeanStrict(stackArr)

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
        geomMeanPixelCount,
        stackSPmode,
        stackDISPmode,
        stackSPgeomMeanStrict,
        stackDISPgeomMeanStrict,
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
    pixel_count : ndarray
        Number of pixels with positive finite flux that entered the
        geometric mean computation, per wavelength bin.
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

    pixel_count = np.sum(valid, axis=axis)

    return gm, sigma_ln, pixel_count


def geomMeanStrict(arr, axis=1):
    """Strict geometric mean: returns NaN if any finite value ≤ 0.

    Contrast with geomMean() (lenient): that function silently drops values
    <= 0 and computes the geometric mean of the remaining positive values,
    tracking how many were used via pixel_count. This function makes the
    opposite choice — if the distribution contains any non-positive flux,
    the geometric mean is undefined and NaN is returned for that bin.

    Science rationale: use geomMeanStrict when the physical interpretation
    requires all spectra to contribute (e.g., ratio-based analyses, log-space
    stacking with strict positivity). Use geomMean when partial participation
    is acceptable (e.g., noisy spectra with occasional negative flux artifacts).

    Dispersion: standard deviation of log(flux) for valid bins, i.e. σ_ln,
    same convention as geomMean(). Represents multiplicative scatter.

    No separate pixel count column: for valid bins all goodPixelCount spectra
    contribute; for NaN bins the count is implicitly zero.

    Parameters
    ----------
    arr : ndarray
        Input array (can contain NaN, but positive values required for success).
    axis : int, optional
        Axis along which to compute (default: 1).

    Returns
    -------
    gm_strict : ndarray
        Geometric mean (NaN where any finite value ≤ 0).
    disp_strict : ndarray
        σ_ln (std of log), NaN same mask as gm_strict.
    """

    arr = np.asarray(arr)

    # Identify finite mask
    finite_mask = np.isfinite(arr)

    # For each bin, check if any finite value is non-positive
    has_nonpositive = np.any((arr <= 0) & finite_mask, axis=axis)

    # Compute log array, replacing invalid with NaN
    log_arr = np.log(np.where(finite_mask, arr, np.nan))

    # Compute mean and std in log space
    mean_log = np.nanmean(log_arr, axis=axis)
    sigma_ln = np.nanstd(log_arr, axis=axis)

    # Back to linear space
    gm_strict = np.where(has_nonpositive, np.nan, np.exp(mean_log))
    disp_strict = np.where(has_nonpositive, np.nan, sigma_ln)

    return gm_strict, disp_strict


def half_sample_mode(arr, axis=1):
    """Half-Sample Mode (HSM) estimator for continuous data.

    Operates on axis=1 (wavelength bins × spectra). For each bin, applies the
    Bickel (2002) HSM algorithm: finds the smallest interval containing at
    least half the non-NaN values, recursively, until 1-2 values remain.
    The mode is the midpoint of the final interval.

    No binning or bandwidth parameter required — deterministic and parameter-free.

    Dispersion: MAD × 1.4826 around the modal value (same convention as
    specMedianDispersion, giving a Gaussian-equivalent σ for symmetric
    unimodal distributions).

    Parameters
    ----------
    arr : ndarray
        Input array. Can contain NaN and inf (ignored).
    axis : int, optional
        Axis along which to compute (default: 1).

    Returns
    -------
    mode_arr : ndarray
        Half-sample mode for each bin.
    disp_arr : ndarray
        MAD × 1.4826 around the modal value.
    """

    def _hsm_1d(x):
        """Compute HSM for a single 1D array (after NaN removal)."""
        x_clean = x[~np.isnan(x)]
        if len(x_clean) == 0:
            return np.nan, np.nan
        if len(x_clean) <= 1:
            return x_clean[0] if len(x_clean) == 1 else np.nan, np.nan

        x_sorted = np.sort(x_clean)
        n = len(x_sorted)

        while n > 2:
            half_n = (n + 1) // 2
            ranges = x_sorted[half_n:] - x_sorted[:-half_n]
            min_idx = np.argmin(ranges)
            x_sorted = x_sorted[min_idx : min_idx + half_n]
            n = len(x_sorted)

        mode_val = 0.5 * (x_sorted[0] + x_sorted[-1])
        return mode_val, x_clean

    arr = np.asarray(arr)

    if axis == 1:
        mode_arr = np.zeros(arr.shape[0])
        disp_arr = np.zeros(arr.shape[0])

        for i in range(arr.shape[0]):
            mode_val, x_clean = _hsm_1d(arr[i, :])
            mode_arr[i] = mode_val

            if not np.isnan(mode_val) and len(x_clean) > 0:
                mad = np.median(np.abs(x_clean - mode_val))
                disp_arr[i] = 1.4826 * mad
            else:
                disp_arr[i] = np.nan

        return mode_arr, disp_arr
    else:
        raise NotImplementedError("axis != 1 not implemented for half_sample_mode")


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
        Six arrays: (sum_arr, mean_arr, med_arr, geom_arr, mode_arr, gms_arr)

        - sum_arr : ndarray
            Sum of resampled spectra
        - mean_arr : ndarray
            Mean of resampled spectra
        - med_arr : ndarray
            Median of resampled spectra
        - geom_arr : ndarray
            Geometric mean of resampled spectra
        - mode_arr : ndarray
            Mode of resampled spectra (HSM)
        - gms_arr : ndarray
            Strict geometric mean of resampled spectra
    """

    arr_sample = arr[:, idx_sample]

    sum_arr = np.nansum(arr_sample, axis=1)
    mean_arr = np.nanmean(arr_sample, axis=1)
    med_arr = np.nanmedian(arr_sample, axis=1)
    geom_arr, _, _ = geomMean(arr_sample)
    mode_arr, _ = half_sample_mode(arr_sample)
    gms_arr, _ = geomMeanStrict(arr_sample)

    return sum_arr, mean_arr, med_arr, geom_arr, mode_arr, gms_arr


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
        Ten arrays: (mean_spec, mean_err, med_spec, med_err, geom_spec, geom_err,
                     mode_spec, mode_err, gms_spec, gms_err)

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
        - mode_spec : ndarray
            Mode spectrum from bootstrap samples
        - mode_err : ndarray
            Uncertainty on mode spectrum
        - gms_spec : ndarray
            Strict geometric mean spectrum from bootstrap samples
        - gms_err : ndarray
            Uncertainty on strict geometric mean spectrum
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
    modeArr = np.array([r[4] for r in results]).T
    gmsArr = np.array([r[5] for r in results]).T

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

    # ---- MODE ----
    mode_p16 = np.nanpercentile(modeArr, 16, axis=1)
    mode_p84 = np.nanpercentile(modeArr, 84, axis=1)

    mode_spec = np.nanmedian(modeArr, axis=1)
    mode_err = 0.5 * (mode_p84 - mode_p16)

    # ---- STRICT GEOMETRIC MEAN ----
    gms_p16 = np.nanpercentile(gmsArr, 16, axis=1)
    gms_p84 = np.nanpercentile(gmsArr, 84, axis=1)

    gms_spec = np.nanmedian(gmsArr, axis=1)
    gms_err = 0.5 * (gms_p84 - gms_p16)

    print("Bootstrap completed")

    return mean_spec, mean_err, med_spec, med_err, geom_spec, geom_err, mode_spec, mode_err, gms_spec, gms_err


