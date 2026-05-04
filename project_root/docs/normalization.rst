Normalization Methods
=====================

Before stacking spectra from multiple galaxies, individual spectra must be normalized to a common scale. This ensures that the stacked spectrum reflects the underlying ensemble properties rather than the varying flux levels of individual sources. SpectraPyle offers six normalization strategies, controlled by the ``spectra_normalization`` configuration field.

Comparison Table
----------------

.. list-table::
   :header-rows: 1
   :widths: 20, 25, 30, 25

   * - Config Value
     - Function
     - Typical Use Case
     - Conserves
   * - ``"no_normalization"``
     - identity (with conservation mode)
     - Pre-normalized spectra or template stacking
     - Flux or luminosity
   * - ``"median"`` (default)
     - :func:`~spectraPyle.spectrum.normalization.normSpecMed`
     - General-purpose stacking
     - Flux
   * - ``"interval"``
     - :func:`~spectraPyle.spectrum.normalization.normSpecInterv`
     - Normalizing over a rest-frame wavelength range
     - Flux
   * - ``"integral"``
     - :func:`~spectraPyle.spectrum.normalization.normSpecIntegrMean`
     - Integrating over entire spectrum or region
     - Flux (integrated)
   * - ``"custom"``
     - :func:`~spectraPyle.spectrum.normalization.normSpecCustom`
     - Using external catalog values (e.g., photometry)
     - Flux (catalog-driven)
   * - ``"template"``
     - :func:`~spectraPyle.spectrum.normalization.francis1991_normalize`
     - Multi-spectrum normalization via iterative reference scaling
     - Flux (relative)

.. note::

   All normalization functions return a tuple of three values:

   1. **normalized flux** — the flux array after normalization
   2. **normalized error** — the 1-sigma error array after normalization (scaled by the same normalization value)
   3. **normalization value** — the scalar used to normalize (median, interval statistic, integral, catalog value, or scaling factor)

No Normalization
----------------

**Config value:** ``"no_normalization"``

**Use case:** When spectra are already normalized externally, or when physical information must be preserved (e.g., measuring emission line fluxes) or when applying Francis et al. (1991) method (spectra are normalized following a dedicated algorithm).

This is a pure identity operation. Each spectrum stays unchanged. The ``conservation`` field must specify whether the user wants to **conserve the flux** (e.g., simpler but optimal for conserving emission line ratios) or to **conserve luminosity** (e.g., to preserve the intrinsic luminosity of the spectral features, for instance to estimate intrinsic properties from emission lines, such as star formation rates from the Hα line)  

.. code-block:: yaml

   norm:
     spectra_normalization: "no_normalization"
     conservation: "flux"

Median Normalization
--------------------

**Config value:** ``"median"`` (default)

**Function:** :func:`~spectraPyle.spectrum.normalization.normSpecMed`

**Formula:**

.. math::

   f_{\mathrm{norm}} = \frac{f}{\mathrm{median}(f)}

Each spectrum is divided by the median of its flux array:

.. math::

   \mathrm{median} = \mathrm{nanmedian}(f_{\lambda})

**Use case:** General-purpose stacking of spectra with widely varying flux levels. Median normalization is robust to outliers and provides a representative normalization for most spectroscopic surveys.

**YAML Example:**

.. code-block:: yaml

   norm:
     spectra_normalization: "median"

Interval Normalization
----------------------

**Config value:** ``"interval"``

**Function:** :func:`~spectraPyle.spectrum.normalization.normSpecInterv`

**Formula:**

.. math::

   f_{\mathrm{norm}} = \frac{f}{S}

where :math:`S` is one of four statistics computed on the flux over a rest-frame wavelength range :math:`[\lambda_{\mathrm{min}}, \lambda_{\mathrm{max}}]`:

.. math::

   S \in \{\mathrm{median}, \mathrm{mean}, \mathrm{maximum}, \mathrm{minimum}\}

**Use case:** Normalizing over a specific rest-frame wavelength interval where the continuum is expected to be well-defined and free of strong emission or absorption features. 

**YAML Example:**

.. code-block:: yaml

   norm:
     spectra_normalization: "interval"
     lambda_norm_min: 1400.0
     lambda_norm_max: 1600.0
     interval_norm_statistics: "median"

The allowed values for ``interval_norm_statistics`` are ``"median"``, ``"mean"``, ``"maximum"``, and ``"minimum"``.

Integral (Integrated Mean) Normalization
-----------------------------------------

**Config value:** ``"integral"``

**Function:** :func:`~spectraPyle.spectrum.normalization.normSpecIntegrMean`

**Formula:**

.. math::

   f_{\mathrm{norm}} = \frac{f}{\langle f \rangle_{\lambda}}

where the integrated mean flux is:

.. math::

   \langle f \rangle_{\lambda} = \frac{\sum_{i} f_i \Delta\lambda_i}{\lambda_{\mathrm{max}} - \lambda_{\mathrm{min}}}

This is the total integrated flux divided by the wavelength span, equivalent to averaging all flux values.

**Use case:** When you want a normalization that accounts for the entire spectrum's flux content rather than a single point or interval. Useful for broadband stacking where the average flux level is more meaningful than the median.

**YAML Example:**

.. code-block:: yaml

   norm:
     spectra_normalization: "integral"

Custom Normalization
---------------------

**Config value:** ``"custom"``

**Function:** :func:`~spectraPyle.spectrum.normalization.normSpecCustom`

**Formula:**

.. math::

   f_{\mathrm{norm}} = \frac{f}{N_{\mathrm{custom}}}

where :math:`N_{\mathrm{custom}}` is a per-spectrum scalar read from a catalog column.

**Use case:** When you have external reference fluxes (e.g., photometric measurements in a fixed band) that you want to use as the normalization reference. This is particularly useful for samples with heterogeneous data or when normalizing to a common photometric standard.

**YAML Example:**

.. code-block:: yaml

   norm:
     spectra_normalization: "custom"
   catalog_columns:
     custom_normalization:
       custom_column_name: "ref_flux_band_mag"

The catalog must include the column specified by ``custom_column_name``. Each value should be finite and positive.

Template Normalization (Francis et al. 1991)
---------------------------------------------

**Config value:** ``"template"``

**Function:** :func:`~spectraPyle.spectrum.normalization.francis1991_normalize`

**Method Overview:**

The Francis et al. (1991) method normalizes a set of spectra iteratively against a consensus reference spectrum. This is fundamentally different from per-spectrum normalization: instead of dividing each spectrum by a statistic computed from its own flux, each spectrum is scaled to match a shared reference.

**Algorithm:**

1. **Select an anchor spectrum** — the first spectrum with sufficient valid pixels (default: ≥ 50 pixels) is designated as the reference.

2. **Initialize the reference** — the anchor is normalized by its own median, and becomes the initial reference flux.

3. **Iterative scaling** — for each subsequent spectrum:

   - Compute the overlap region with the current reference (pixels with finite flux in both).
   - Estimate a scaling factor :math:`\alpha` by computing the median (or mean) of the ratio :math:`f_{\mathrm{ref}} / f_i` in the overlap region, with optional sigma-clipping.
   - Scale the spectrum: :math:`f_{\mathrm{norm}} = \alpha \cdot f_i`.
   - Update the reference using a count-weighted average: :math:`f_{\mathrm{ref,new}} = \frac{f_{\mathrm{ref}} \cdot c + f_{\mathrm{norm}}}{c + 1}` (where :math:`c` is the overlap count).
   - Add any new pixels from the current spectrum to the reference.

4. **Output** — normalized flux and error for all spectra.

**Use case:** Producing spectral templates of homogeneous sources. The iterative approach ensures that all spectra are mutually consistent while preserving the relative flux levels within overlapping regions. Also used when you need relative flux conservation across a heterogeneous sample.

**YAML Example:**

.. code-block:: yaml

   norm:
     spectra_normalization: "template"

.. seealso::

   - :func:`~spectraPyle.spectrum.normalization.francis1991_normalize` — full function documentation with parameters for sigma-clipping and overlap control.
   - **Francis, P. J., Hewett, P. C., Foltz, C. B., Chaffee, F. H., Weymann, R. J., & Morris, S. L.** (1991), *ApJ*, **373**, 465. Composite quasar spectra from the Hubble Space Telescope Faint Object Spectrograph.
