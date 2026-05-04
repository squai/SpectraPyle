Resampling Modes
================

Every spectrum in SpectraPyle is resampled onto a common wavelength grid before stacking. This is a critical step because individual spectra from the survey typically have different wavelength coverage and pixel scales. SpectraPyle implements a flux-conservative resampling algorithm based on the Drizzle method of Fruchter & Hook (2002), which ensures that the total flux and its uncertainty are properly propagated during the transformation to the stacking grid.

The ``resampling`` configuration block controls how this wavelength grid is constructed and how spectra are mapped onto it.

Grid Modes
----------

SpectraPyle supports three main resampling modes: **linear** (``"lambda"``), **logarithmic** (``"log_lambda"``), and **none** (``"none"``). Within each mode, you can choose between **manual** pixel sizing (fixed wavelength step) or **instrumental** pixel sizing (Nyquist-sampled based on spectral resolution).

.. list-table:: Resampling Grid Modes
   :header-rows: 1
   :widths: 20, 20, 30, 30

   * - Grid Type
     - Manual (fixed step)
     - Instrumental (Nyquist)
     - Use Case
   * - ``"lambda"`` (linear)
     - User sets Δλ (Å)
     - Δλ = λ_ref / (R × n_nyq)
     - Fixed pixel scale across wavelength
   * - ``"log_lambda"`` (logarithmic)
     - User sets Δlog₁₀λ
     - Δlog₁₀λ = 1 / (R × n_nyq × ln 10)
     - Constant velocity resolution
   * - ``"none"``
     - N/A
     - N/A
     - All spectra already on same grid

**Config Fields:**

``pixel_resampling_type``
  Literal[``"lambda"``, ``"log_lambda"``, ``"lambda_shifted"``, ``"none"``]. Default: ``"lambda"``.

``pixel_size_type``
  Literal[``"manual"``, ``"instrumental"``]. Default: ``"instrumental"``.

``pixel_resampling``
  float, optional. Manual step size (Å for linear, Δlog₁₀λ for logarithmic). Required if ``pixel_size_type = "manual"``.

``nyquist_sampling``
  float, optional. Number of pixels per resolution element. Default: ``5``. Required if ``pixel_size_type = "instrumental"``.

Linear Grid
-----------

**Config value:** ``pixel_resampling_type: "lambda"``

The linear (or constant-wavelength) grid spaces pixels uniformly in wavelength. This is the simplest and most intuitive grid type, suitable when wavelength resolution is not a primary concern or when stacking broadband spectra.

Manual Pixel Size
~~~~~~~~~~~~~~~~~

When ``pixel_size_type: "manual"``, the user directly specifies the wavelength step Δλ (in Ångströms):

.. math::

   \lambda_{\mathrm{grid}} = \lambda_{\mathrm{min}}, \lambda_{\mathrm{min}} + \Delta\lambda, \lambda_{\mathrm{min}} + 2\Delta\lambda, \ldots

**YAML Example:**

.. code-block:: yaml

   resampling:
     pixel_resampling_type: "lambda"
     pixel_size_type: "manual"
     pixel_resampling: 4

This creates a grid with 4 Å steps, suitable for low-resolution or moderate-resolution spectra where oversampling is not needed.

Instrumental (Nyquist-Sampled) Pixel Size
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``pixel_size_type: "instrumental"``, SpectraPyle computes Δλ from the instrument's spectral resolving power R and the Nyquist sampling factor n_nyq:

.. math::

   \Delta\lambda = \frac{\lambda_{\mathrm{ref}}}{R \times n_{\mathrm{nyq}}}

where

- **R** is the spectral resolving power (λ / Δλ_FWHM) from the instrument rules
- **λ_ref** is a reference wavelength (typically the midpoint of the stacking window)
- **n_nyq** is the number of pixels per resolution element (default: 5)

For example, with Euclid NISP red grism (R ≈ 600) at λ = 16000 Å and n_nyq = 5:

.. math::

   \Delta\lambda = \frac{16000}{600 \times 5} \approx 5.33 \text{ Å}

**YAML Example:**

.. code-block:: yaml

   resampling:
     pixel_resampling_type: "lambda"
     pixel_size_type: "instrumental"
     nyquist_sampling: 5

Logarithmic Grid
----------------

**Config value:** ``pixel_resampling_type: "log_lambda"``

The logarithmic (or log-wavelength) grid spaces pixels uniformly in :math:`\log_{10}(\lambda)`. This is particularly valuable for high-redshift studies because equal spacing in log-wavelength corresponds to equal velocity spacing, providing constant spectral resolution in velocity space.

**Velocity equivalence:**

A logarithmic wavelength step Δlog₁₀λ translates to a constant velocity width:

.. math::

   \frac{\Delta v}{c} = \ln(10) \times \Delta\log_{10}\lambda

For example, Δlog₁₀λ = 0.0001 corresponds to Δv ≈ 230 km/s.

Manual Pixel Size
~~~~~~~~~~~~~~~~~

When ``pixel_size_type: "manual"``, the user specifies Δlog₁₀λ directly:

.. math::

   \lambda_{\mathrm{grid}} = 10^{\log_{10}\lambda_{\mathrm{min}}}, 10^{\log_{10}\lambda_{\mathrm{min}} + \Delta\log_{10}\lambda}, 10^{\log_{10}\lambda_{\mathrm{min}} + 2\Delta\log_{10}\lambda}, \ldots

**YAML Example:**

.. code-block:: yaml

   resampling:
     pixel_resampling_type: "log_lambda"
     pixel_size_type: "manual"
     pixel_resampling: 0.0001

This creates a logarithmic grid with Δlog₁₀λ = 0.0001, corresponding to a constant velocity step of:

.. math::

   \Delta v = c \times \ln(10) \times 0.0001 \approx 231 \text{ km/s}

Instrumental (Nyquist-Sampled) Pixel Size
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``pixel_size_type: "instrumental"``, the step is computed from resolving power:

.. math::

   \Delta\log_{10}\lambda = \frac{1}{R \times n_{\mathrm{nyq}} \times \ln(10)}

where **R** and **n_nyq** are as defined for linear grids.

For Euclid NISP red (R ≈ 600) with n_nyq = 5:

.. math::

   \Delta\log_{10}\lambda = \frac{1}{600 \times 5 \times \ln(10)} \approx 0.000144

**YAML Example:**

.. code-block:: yaml

   resampling:
     pixel_resampling_type: "log_lambda"
     pixel_size_type: "instrumental"
     nyquist_sampling: 5

No Resampling
-------------

**Config value:** ``pixel_resampling_type: "none"``

When ``pixel_resampling_type: "none"``, SpectraPyle **skips wavelength resampling entirely**. All input spectra must already be on an identical wavelength grid. This mode is useful when:

- Spectra come from a single instrument/pipeline with a fixed wavelength solution
- You have pre-processed spectra that are already aligned
- You want to preserve the original instrument's pixel structure

.. warning::

   With ``pixel_resampling_type: "none"``, if spectra have different wavelength grids, they will **not** be aligned before stacking. The first spectrum's wavelength grid is used as the reference. This typically results in incorrect or meaningless stacking.

**YAML Example:**

.. code-block:: yaml

   resampling:
     pixel_resampling_type: "none"

Algorithm: Fruchter & Hook (2002) Drizzle
------------------------------------------

SpectraPyle implements the flux-conserving resampling algorithm described by Fruchter & Hook (2002). This method computes the fractional overlap between each input pixel and each output bin, then combines contributions weighted by their overlap.

**Flux Conservation:**

For each output pixel j, the resampled flux is a weighted sum of all overlapping input pixels:

.. math::

   f_j^{\mathrm{out}} = \frac{\sum_{i} w_{ij} \times f_i^{\mathrm{in}}}{\sum_{i} w_{ij}}

where

- **f_i^in** is the flux in input pixel i
- **w_ij** is the fractional overlap (0 ≤ w_ij ≤ 1) between input pixel i and output bin j
- The sum runs over all input pixels that overlap output bin j

**Variance Propagation:**

Errors are propagated using the standard rule for weighted sums:

.. math::

   \sigma_j^{2} = \frac{\sum_{i} w_{ij}^2 \times \sigma_i^{2}}{(\sum_{i} w_{ij})^2}

or equivalently:

.. math::

   \sigma_j = \frac{\sqrt{\sum_{i} w_{ij}^2 \times \sigma_i^{2}}}{\sum_{i} w_{ij}}

This ensures that the error is properly attenuated when multiple input pixels contribute to a single output pixel (signal stacking reduces noise).

**Fractional Overlap Calculation:**

The overlap fraction w_ij is computed geometrically as:

.. math::

   w_{ij} = \frac{\max(0, \min(\lambda_i^{\mathrm{hi}}, \lambda_j^{\mathrm{hi}}) - \max(\lambda_i^{\mathrm{lo}}, \lambda_j^{\mathrm{lo}}))}{\Delta\lambda_i}

where

- **λ_i^lo, λ_i^hi** are the lower and upper edges of input pixel i
- **λ_j^lo, λ_j^hi** are the lower and upper edges of output bin j
- **Δλ_i** is the width of input pixel i

**NaN and Bad Pixel Handling:**

Input pixels with finite=False (NaN, inf, etc.) are masked out before resampling:

.. math::

   f_i^{\mathrm{in}} \to 0 \text{ if } \overline{f_i}, \quad \sigma_i^2 \to 0 \text{ if } \overline{\sigma_i}

Output pixels that receive no valid input data (all overlapping input pixels are bad) are marked as NaN.

**Reference:**

Fruchter, A. S., & Hook, R. N. (2002). *Drizzle: A Method for the Linear Reconstruction of Undersampled Images*. *PASP*, **114**, 144–152.

.. seealso::

   - :func:`~spectraPyle.spectrum.resampling.resamplingSpecFluxCons` — main resampling function (flux-conservative, with variance propagation)
   - :func:`~spectraPyle.spectrum.resampling.dlam_from_R` — compute linear wavelength step from resolving power
   - :func:`~spectraPyle.spectrum.resampling.dloglam_from_R` — compute logarithmic wavelength step from resolving power
   - :class:`~spectraPyle.schema.schema.ResamplingConfig` — configuration schema with validation
