Stacking Statistics
===================

SpectraPyle computes six different stacking estimators for each wavelength bin. Each statistic is computed from a distribution of N-spectra flux values after :doc:`resampling` and sigma-clipping.

.. contents::
   :local:
   :depth: 2

---

Overview
--------

All statistics are available in the FITS output with the naming convention:

- **Flux:** ``spec{Statistic}`` — the stacked spectrum value per wavelength bin
- **Dispersion:** ``spec{Statistic}Dispersion`` — intrinsic scatter around the statistic
- **Error:** ``spec{Statistic}Error`` — 1σ uncertainty on the statistic (from bootstrap or analytical formula)

+---------------------+----------------------------+-------------------------------------------+
| Statistic           | FITS columns               | Use case                                  |
+=====================+============================+===========================================+
| Mean                | specMean*                  | Classical average; sensitive to outliers  |
+---------------------+----------------------------+-------------------------------------------+
| Median              | specMedian*                | Robust; insensitive to outliers           |
+---------------------+----------------------------+-------------------------------------------+
| Geometric mean      | specGeometricMean*         | Log-space average (lenient); excludes ≤0  |
| (lenient)           |                            |                                           |
+---------------------+----------------------------+-------------------------------------------+
| Geometric mean      | specStrictGeometricMean*   | Log-space average (strict); NaN if any ≤0 |
| (strict)            |                            |                                           |
+---------------------+----------------------------+-------------------------------------------+
| Mode (HSM)          | specMode*                  | Most common value; parameter-free         |
+---------------------+----------------------------+-------------------------------------------+
| Weighted mean       | specWeightedMean*          | Uses inverse-variance weights             |
+---------------------+----------------------------+-------------------------------------------+

---

Arithmetic Mean
---------------

The classical mean: sum of all flux values divided by count.

**Formula:**

.. math::

   \bar{F} = \frac{1}{N} \sum_{i=1}^{N} F_i

**Dispersion:**
Unbiased sample standard deviation:

.. math::

   \sigma_{\text{mean}} = \sqrt{\frac{1}{N} \sum_{i=1}^{N} (F_i - \bar{F})^2}

**Error:**
From bootstrap resampling (percentile 16–84) or analytic formula:

.. math::

   \delta \bar{F} = \frac{\sigma_{\text{mean}}}{\sqrt{N_{\text{good}}}}

**Characteristics:**
- Least robust to outliers
- Best for distributions without extreme values
- Default choice for symmetric distributions

**FITS columns:** ``specMean``, ``specMeanDispersion``, ``specMeanError``

---

Median
------

The central value separating the upper and lower halves of the distribution.

**Dispersion:**
Robust estimate via Median Absolute Deviation (MAD), scaled to Gaussian σ:

.. math::

   \sigma_{\text{med}} = 1.4826 \times \text{MAD} = 1.4826 \times \text{median}(|F_i - \tilde{F}|)

**Error:**
From bootstrap resampling (percentile 16–84) or analytic formula:

.. math::

   \delta \tilde{F} = \frac{\sigma_{\text{med}}}{\sqrt{N_{\text{good}}}}

**Characteristics:**
- Highly robust to outliers
- Insensitive to extreme values in either tail
- Ideal for distributions with outliers or asymmetry
- Default visible trace in the interactive plot

**FITS columns:** ``specMedian``, ``specMedianDispersion``, ``specMedianError``

---

Geometric Mean (Lenient)
------------------------

Log-space average, computed from **positive-valued spectra only**. Non-positive values are silently excluded per wavelength bin.

**Formula:**

.. math::

   G_{\text{lenient}} = \exp\left( \frac{1}{N_{\text{pos}}} \sum_{F_i > 0} \ln F_i \right)

where :math:`N_{\text{pos}}` is the count of positive values at that wavelength.

**Dispersion:**
Standard deviation in log-space (multiplicative scatter):

.. math::

   \sigma_{\ln G} = \sqrt{\frac{1}{N_{\text{pos}}} \sum_{F_i > 0} (\ln F_i - \ln G)^2}

**Pixel count:**
``geomMeanPixelCount`` — number of positive-finite spectra per bin.

**Error:**
From bootstrap (percentile 16–84) or analytic formula.

**Characteristics:**
- Suitable for ratio-based quantities (e.g., fluxes, SED ratios)
- Gracefully handles partial contributions (missing or zero values)
- Returns finite values even if some spectra have ≤0 flux at a pixel
- Useful when approximate missing data is acceptable

**When to use:**
- Stacking spectra with occasional negative flux artifacts
- Situations where some spectra may have zero/undefined flux at some wavelengths
- Physical quantities that are naturally multiplicative

**FITS columns:** ``specGeometricMean``, ``specGeometricMeanDispersion``, ``specGeometricMeanError``, ``geomMeanPixelCount``

---

Geometric Mean (Strict)
-----------------------

Log-space average that enforces **strict positivity**. Returns NaN for any wavelength bin where **at least one** spectrum has flux ≤ 0.

**Formula:**

.. math::

   G_{\text{strict}} = \begin{cases}
   \exp\left( \frac{1}{N} \sum_{i=1}^{N} \ln F_i \right) & \text{if } \forall i: F_i > 0 \\
   \text{NaN} & \text{otherwise}
   \end{cases}

**Dispersion:**
Identical to lenient (σ_ln) where defined; NaN elsewhere.

**Characteristics:**
- All spectra must contribute positive flux — no partial participation
- Binary mask per wavelength: either all-valid or NaN
- More conservative; fails fast if data quality is heterogeneous

**When to use:**
- Stacking with strict physical assumptions (e.g., ratio-based analyses in log-space)
- When data quality requirements demand 100% positivity
- Identifying wavelength regions contaminated across the sample

**Difference from Lenient:**

The main difference is **handling of non-positive values**:

- **Lenient** (``specGeometricMean``): Omits non-positive values **per wavelength**, allowing partial participation
- **Strict** (``specStrictGeometricMean``): Requires **all spectra positive at that wavelength** or returns NaN

Example: 10 spectra, one has negative flux at pixel i:

- Lenient: Uses 9 positive values → finite result
- Strict: Returns NaN at pixel i

**FITS columns:** ``specStrictGeometricMean``, ``specStrictGeometricMeanDispersion``, ``specStrictGeometricMeanError``

---

Mode (Half-Sample Mode)
-----------------------

The most common value in the distribution, computed via the Half-Sample Mode (HSM) algorithm.

**Algorithm:**
Recursively finds the smallest interval containing at least half the data points. The mode is the midpoint of the final interval (Bickel 2002).

**Advantages over histogram-based mode:**
- Parameter-free: no bin-width selection needed
- Deterministic: no binning artifacts
- Works with continuous data without discretization
- Robust to outliers
- Efficient: O(N log N) per wavelength bin

**Dispersion:**
Median Absolute Deviation (MAD) around the mode, scaled to Gaussian σ:

.. math::

   \sigma_{\text{mode}} = 1.4826 \times \text{MAD}_{\text{mode}} = 1.4826 \times \text{median}(|F_i - M|)

where :math:`M` is the mode.

**Error:**
From bootstrap (percentile 16–84) or analytic formula.

**Characteristics:**
- Robust to outliers
- Best for unimodal or near-unimodal distributions
- Non-parametric (no distribution assumptions)
- Naturally handles discrete or continuous data

**When to use:**
- When the most probable value is scientifically relevant
- Distributions with strong peaks
- As a robustness check against mean and median

**FITS columns:** ``specMode``, ``specModeDispersion``, ``specModeError``

---

Weighted Mean
-------------

Average computed with inverse-variance weights, accounting for per-spectrum uncertainties.

**Formula:**

.. math::

   \bar{F}_w = \frac{\sum_{i=1}^{N} w_i F_i}{\sum_{i=1}^{N} w_i}, \quad w_i = \frac{1}{\sigma_i^2}

**Dispersion:**
Weighted RMS scatter:

.. math::

   \sigma_w = \sqrt{\frac{\sum_{i=1}^{N} w_i (F_i - \bar{F}_w)^2}{\sum_{i=1}^{N} w_i}}

**Error:**
Uncertainty on the weighted mean (not bootstrap):

.. math::

   \delta \bar{F}_w = \sqrt{\frac{1}{\sum_{i=1}^{N} w_i}}

**Characteristics:**
- Accounts for per-spectrum quality
- Downweights noisy spectra
- Optimal if uncertainties are accurate
- No bootstrap; error from weight sum

**When to use:**
- When spectrum uncertainties are reliable
- Heterogeneous data quality
- Maximum-likelihood stacking

**FITS columns:** ``specWeightedMean``, ``specWeightedMeanDispersion``, ``specWeightedMeanError``

---

Percentiles
-----------

Distribution quantiles at fixed levels:

+--------+-------------------------+---------+
| Column | Percentile level        | Alias   |
+========+=========================+=========+
| spec16th    | 15.87th             | −1σ     |
+--------+-------------------------+---------+
| spec84th    | 84.14th             | +1σ     |
+--------+-------------------------+---------+
| spec98th    | 97.73rd             | ~+2σ    |
+--------+-------------------------+---------+
| spec99th    | 99.73rd             | ~+3σ    |
+--------+-------------------------+---------+

**Use:**
- Inspect distribution shape and tails
- Identify outliers or contamination
- Assess asymmetry
- Science analysis (e.g., confidence intervals)

**No uncertainties:** Percentiles are deterministic from the sample.

---

Error Estimation: Bootstrap vs. Analytical
-------------------------------------------

SpectraPyle supports two error estimation methods, controlled by config key ``bootstrapping_R``:

**Bootstrap (``bootstrapping_R > 0``):**

Performs :math:`R` resampling iterations with replacement. For each iteration, recomputes the statistic. Final error is the 16–84th percentile range divided by 2 (equivalent to ±1σ for normal distributions).

- **Pros:** Non-parametric; valid for any distribution
- **Cons:** Computationally expensive; requires tuning :math:`R`

**Analytical (``bootstrapping_R = 0``):**

Uses closed-form formulas based on data dispersion and sample size:

.. math::

   \delta \text{stat} = \frac{\sigma_{\text{stat}}}{\sqrt{N_{\text{good}}}}

- **Pros:** Fast; well-understood for normal distributions
- **Cons:** Assumes specific distribution shape; may underestimate errors for non-normal data

**Recommendation:** Use bootstrap for heterogeneous or non-normal data; analytical for large samples with reliable dispersions.

---

Summary Table: When to Use Each Statistic
------------------------------------------

+---------------------+------------------------------------------+---------------------------------------------+
| Statistic           | Best for                                 | Avoid when                                  |
+=====================+==========================================+=============================================+
| Mean                | Symmetric, outlier-free distributions   | Heavy-tailed or bimodal distributions       |
+---------------------+------------------------------------------+---------------------------------------------+
| Median              | Outliers present; robustness required   | Distribution shape not important            |
+---------------------+------------------------------------------+---------------------------------------------+
| Geom. Mean (lenient)| Ratio quantities; partial positivity OK | Need strict positivity everywhere            |
+---------------------+------------------------------------------+---------------------------------------------+
| Geom. Mean (strict) | Ratio quantities; strict positivity     | Missing/zero values in sample               |
+---------------------+------------------------------------------+---------------------------------------------+
| Mode (HSM)          | Peak-finding; non-parametric estimate  | Highly multimodal distributions             |
+---------------------+------------------------------------------+---------------------------------------------+
| Weighted Mean       | Heterogeneous quality; weights reliable | Weights poorly characterized                 |
+---------------------+------------------------------------------+---------------------------------------------+

---

API Reference
-------------

.. automodule:: spectraPyle.statistic.statistics
   :members:
   :undoc-members:
   :show-inheritance:
