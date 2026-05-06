Interactive Plotting & Visualization
====================================

SpectraPyle generates an **interactive Plotly figure** showing the stacked spectrum with all six stacking estimators overlaid, pixel counts, percentile bands, and astrophysical features (emission lines, absorption features).

---

Overview
--------

The plot is a **two-panel Plotly figure** that opens in a browser or Jupyter notebook:

1. **Top panel:** Pixel counts over wavelength (good, bad, sigma-clipped, etc.)
2. **Bottom panel:** Stacked spectra with error/dispersion bands, percentile envelopes, and emission/absorption markers

All traces are **interactive and toggleable** via the legend. Hover for exact values.

---

Layout & Structure
-------------------

**Top panel (row 1):**
   - 15% of figure height
   - Line traces for pixel counts (good, bad, sigma-clipped, geometric-mean-specific)
   - Shared x-axis with bottom panel (wavelength)

**Bottom panel (row 2):**
   - 85% of figure height
   - Main stacked spectra + error/dispersion bands
   - Percentile bands (16th–84th, 98th, 99th)
   - Emission line and absorption feature markers
   - Shared x-axis with top panel

---

Pixel Count Traces (Top Panel)
------------------------------

The top panel displays **four mandatory counts** and **one optional count**:

+------------------------+----------+---------------------+--------+
| Trace                  | Color    | Default visibility  | Toggle |
+========================+==========+=====================+========+
| All spectra            | black    | Visible             | ✓      |
+------------------------+----------+---------------------+--------+
| Used spectra (good)    | blue     | Visible             | ✓      |
+------------------------+----------+---------------------+--------+
| Bad pixels             | red      | Hidden (legendonly) | ✓      |
+------------------------+----------+---------------------+--------+
| Sigma-clipped pixels   | grey     | Hidden (legendonly) | ✓      |
+------------------------+----------+---------------------+--------+
| Geom. mean pixels      | orange   | Hidden (legendonly) | ✓      |
+------------------------+----------+---------------------+--------+

**"Geom. mean pixels" trace:**
   - Shows how many spectra had **positive flux** at each wavelength (used for geometric mean computation)
   - Shares legend group with ``specGeometricMean`` spectrum trace
   - Clicking the spectrum in legend also toggles this pixel count
   - Useful to diagnose non-positive flux contamination

---

Main Spectrum Traces (Bottom Panel)
-----------------------------------

Six stacking estimators are displayed with consistent visual structure:

For **each statistic** (:math:`S \in \{\text{Mean, Median, Geom. Mean, Strict Geom. Mean, Mode, Weighted Mean}\}`):

1. **Error band** (lower invisible bound)
2. **Error band** (upper visible bound + fill) — labeled ``S ± 1σ``
3. **Dispersion band** (lower invisible bound)
4. **Dispersion band** (upper visible bound + fill) — labeled ``S ± dispers.``
5. **Main flux line** — the statistic itself

Each trace is **toggleable independently** by clicking the legend entry.

**Default visibility:**
   - ``specMedian`` — **visible by default**
   - All others — **hidden by default** (``legendonly``)

**Colors (chosen for accessibility):**

+---------------------+--------+
| Statistic           | Color  |
+=====================+========+
| Mean                | Orange |
+---------------------+--------+
| Median              | Cyan   |
+---------------------+--------+
| Weighted Mean       | Purple |
+---------------------+--------+
| Geometric Mean      | Green  |
+---------------------+--------+
| Strict Geom. Mean   | Lime   |
+---------------------+--------+
| Mode (HSM)          | Red    |
+---------------------+--------+

---

Percentile Bands
----------------

**Four percentile traces** are plotted as optional, hidden-by-default bands:

+--------+----------------------------------+------+
| Trace  | Representation                   | Style|
+========+==================================+======+
| 16th–84th | Filled band (±1σ envelope)  | Solid|
+--------+----------------------------------+------+
| 98th   | Line (≈2σ upper tail)            | Dashed|
+--------+----------------------------------+------+
| 99th   | Line (≈3σ upper tail)            | Dotted|
+--------+----------------------------------+------+

**16th–84th percentile band:**
   - Single legend entry: ``±1σ envelope (16th–84th)``
   - Centered filled region (light blue)
   - Represents the central 68% of the flux distribution
   - Similar to error band, but **non-parametric** (no distribution assumptions)
   - Share ``legendgroup='percentile_1sigma'`` for grouped toggling

**98th and 99th percentiles:**
   - Separate independent traces
   - Dashed (98th) and dotted (99th) line styles
   - Use case: identify high-flux outliers or contamination in the tails
   - Not error estimates; rather, quantiles for inspection

---

Astrophysical Markers
---------------------

If the stacking is **not in observed frame** (i.e., ``z_type != 'observed_frame'``):

**Emission lines** (from ``tables/emission_lines_vacuum_table.csv``):
   - Vertical markers at rest-frame wavelengths redshifted to stacking frame
   - Labels for common lines: Hα, Hβ, [OIII], Lyman-α, etc.
   - Color and y-position chosen for visibility against the spectrum

**Absorption features** (from ``tables/absorptions_table.csv``):
   - Similar markers for absorption lines/bands (e.g., Balmer, Ca H&K)
   - Coordinated with emission line placement to avoid label overlap

**In observed frame:**
   - No automatic markers (static rest-frame lines are not applicable)

---

Legend & Interactivity
----------------------

**Legend location:** Right of plot area (``x=1.02``)

**Legend features:**
   - **Grouping:** Traces are grouped by statistic and type (error, dispersion, flux)
   - **Clicking:** Click a legend item to toggle that trace's visibility
   - **Double-click:** Double-click a legend item to isolate it (hide all others)
   - **Grouped toggles:** For percentiles and some traces, clicking one entry in a group toggles all traces in that group

**Hover information:**
   - Wavelength (nm), flux value, uncertainty
   - Pixel count values (top panel)

**Toolbar (top-right of figure):**
   - Download plot as PNG
   - Zoom, pan, reset axes
   - Show/hide legend
   - Box select, lasso select

---

When to Use Each Trace
----------------------

+---------+-------------------+----------------------------------------------+
| Trace   | Best for          | Interpretation                               |
+=========+===================+==============================================+
| Median  | Robust estimate   | Central value, unaffected by outliers        |
+---------+-------------------+----------------------------------------------+
| Mean    | Reference         | Classical average; compare with median       |
+---------+-------------------+----------------------------------------------+
| Geom.   | Log-space         | Geometric average                            |
| Mean    | stacking          |                                              |
+---------+-------------------+----------------------------------------------+
| Strict  | Strict            | Check for wavelength regions with ≤0 flux   |
| Geom.   | positivity        | (will be NaN if present)                    |
| Mean    |                   |                                              |
+---------+-------------------+----------------------------------------------+
| Mode    | Peak detection    | Most common flux value                       |
+---------+-------------------+----------------------------------------------+
| Weighted| Quality-weighted  | Downweights noisy spectra                    |
| Mean    | stacking          |                                              |
+---------+-------------------+----------------------------------------------+
| ±1σ env | Distribution      | Central 68% (non-parametric)                 |
| (16–84) | inspection        |                                              |
+---------+-------------------+----------------------------------------------+
| 98th,   | Tail inspection   | High-flux outliers or contamination          |
| 99th    |                   |                                              |
+---------+-------------------+----------------------------------------------+

---

Error vs. Dispersion Bands
--------------------------

Two types of **uncertainty bands** are shown for each statistic:

**Error band (`` ± 1σ Uncertainty``):**
   - Represents the **statistical uncertainty on the stacked value**
   - Computed from bootstrap resampling (percentile 16–84) or analytical formula
   - Smaller for larger samples (decreases as 1/√N)

**Dispersion band (`` ± Dispersion``):**
   - Represents the **intrinsic scatter of spectra around the statistic**
   - Computed as RMS (mean/median) or log-RMS (geometric mean)
   - Independent of sample size
   - **Interpretation:** How much individual spectra deviate from the stack; measure of diversity in the sample

**Example:**
   - **Error band narrows** as more spectra are added (smaller uncertainty on mean)
   - **Dispersion band stays roughly constant** (scatter among spectra unchanged)

To compare:
   - **Want tight error?** Add more spectra
   - **Want to reduce dispersion?** Improve data quality or apply stricter selection

---

Configuration
-----------

Plot appearance is controlled by the ``plot`` section in the config:

.. code-block:: yaml

   plot:
     plot_results: true  # if false, skips plot generation

**Size tuning (in Python):**

.. code-block:: python

   from spectraPyle.plot.plot import plotting

   fig = plotting('result.fits', width=1200, height=700)  # default 950 x 550

---

Example: Interpreting a Stack
------------------------------

A typical stacked spectrum tells you:

1. **Median (cyan, main focus):**
   - Central spectrum; robust to outliers
   - Use as your primary result

2. **Mean (orange, dashed):**
   - If mean and median differ significantly → sample contains outliers

3. **Geom. Mean (green) vs. Strict Geom. Mean (lime):**
   - If Strict is NaN at some wavelengths → non-positive flux present at those wavelengths

4. **Dispersion bands (wider = more heterogeneous sample):**
   - Reflects diversity in the galaxy population
   - Useful for downstream uncertainty propagation

5. **Percentile bands (16th–84th):**
   - Shows the central 68% of the distribution without distributional assumptions
   - Compare with ±1σ error band to assess non-normality

6. **98th/99th percentiles (red dashed/dotted):**
   - If they deviate far from median → presence of high-flux outliers
   - May show contamination from misclassified redshift due to misinterpreted emission lines (see Euclid Collaboration, Quai S., Pozzetti L., et al. 2025, Astronomy & Astrophysics, DOI: 10.1051/0004-6361/202557329)

7. **Geom. mean pixels (green, top panel):**
   - If this count drops → some wavelengths have non-positive flux
   - Indicates noisiy spectra or calibration artifacts

---

2D Flux Distribution Viewer
----------------------------

After a stacking run, SpectraPyle writes an intermediate HDF5 file (``*_array.h5``)
containing the full matrix of individual resampled spectra before combination.
The :func:`plot_h5_heatmap` function and the companion notebook ``notebooks/plot_helper.ipynb``
let you explore this matrix as a 2D flux distribution.

**How to open:**

Open ``notebooks/plot_helper.ipynb`` in JupyterLab after setting ``name_stack`` to the
path of your stacked FITS file. The notebook derives the companion H5 path automatically
and exposes all parameters as interactive widgets.

**Modes:**

- **heatmap** — 2D density map: each cell counts how many spectra have a given flux at a
  given wavelength. The selected stacked statistic (e.g. ``specMedian``) is overlaid as a
  cyan line for reference.
- **lines** — individual spectra as thin, translucent overlapping traces normalized to
  their own peak; useful for identifying outliers or non-standard spectral shapes.

**Widgets (``plot_helper.ipynb``):**

+-------------------+--------------------------+-----------------------------------------------------+
| Widget            | Default                  | Description                                         |
+===================+==========================+=====================================================+
| Mode              | heatmap                  | Switch between heatmap and lines                    |
+-------------------+--------------------------+-----------------------------------------------------+
| Array             | original                 | Raw array or template-normalized array (if present) |
+-------------------+--------------------------+-----------------------------------------------------+
| Metric            | specMedian               | Stacked statistic to overlay on the heatmap         |
+-------------------+--------------------------+-----------------------------------------------------+
| Norm factors      | off                      | Overlay per-spectrum normalization factors           |
|                   |                          | as scatter on a right axis                          |
+-------------------+--------------------------+-----------------------------------------------------+
| Max spectra       | 0 (all)                  | Subsample N random spectra (useful for large stacks)|
+-------------------+--------------------------+-----------------------------------------------------+
| Line alpha        | 0.05                     | Opacity per trace in lines mode                     |
+-------------------+--------------------------+-----------------------------------------------------+
| X bins            | n_pixels                 | Wavelength bins; default = one bin per original     |
|                   |                          | pixel (pixel-exact, no redistribution)              |
+-------------------+--------------------------+-----------------------------------------------------+
| Y bins            | 200                      | Flux bins                                           |
+-------------------+--------------------------+-----------------------------------------------------+

**Binning and physical correctness:**

The heatmap is computed with ``numpy.histogram2d`` using deterministic bin edges, avoiding
rendering artefacts that Plotly's internal ``Histogram2d`` binning can introduce on
non-uniform wavelength grids.

- **X bins = n_pixels (default):** pixel-exact half-pixel edges are used. Each histogram
  column maps one-to-one to one original wavelength pixel. No flux redistribution — physically
  unbiased for both linear and log-linear grids.
- **X bins < n_pixels:** uniform bin edges are applied over ``[λ_min, λ_max]``. A warning
  is printed in the notebook output because flux is redistributed across bins on non-uniform
  grids. Use this only for faster rendering when the exact per-pixel distribution is not needed.

Cells with zero count are rendered transparent rather than white, so real gaps in the data
(chip gaps between grisms, masked sky-line regions, or fully rejected spectra) remain visible
and are distinguishable from rendering artefacts.

**Python API:**

.. code-block:: python

   from spectraPyle.plot.plot import plot_h5_heatmap

   fig = plot_h5_heatmap(
       h5_path        = 'result_array.h5',
       fits_path      = 'result_STACKING.fits',
       template_array = 'original',   # 'norm' to use template-normalized array
       metric         = 'specMedian',
       mode           = 'heatmap',    # or 'lines'
       nbinsx         = None,         # None → n_pixels (pixel-exact edges)
       nbinsy         = 200,
       max_spectra    = None,         # int to subsample randomly
       line_alpha     = 0.05,
   )
   fig.show()

.. note::
   ``plot_h5_heatmap`` requires both the FITS output (``*_STACKING.fits``) and the
   companion HDF5 file (``*_array.h5``) produced during the same stacking run.
   The H5 file is written automatically when ``stacking.py`` runs.

---

API Reference
-------------

.. automodule:: spectraPyle.plot.plot
   :members: plotting, plot_h5_heatmap, read_fits_and_select_columns, get_header
   :undoc-members:
   :show-inheritance:
