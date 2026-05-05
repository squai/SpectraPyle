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
   - User can manually overlay reference spectra if needed

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
| Geom.   | Log-space         | Geometric average for ratios                 |
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
   - **Interpretation:** Expected scatter in the stacked value if the stacking were repeated

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
   - May indicate contamination or rare blue objects in the sample

7. **Geom. mean pixels (orange, top panel):**
   - If this count drops → some wavelengths have non-positive flux
   - Indicates data quality issues or calibration artifacts

---

API Reference
-------------

.. automodule:: spectraPyle.plot.plot
   :members: plotting, read_fits_and_select_columns, get_header
   :undoc-members:
   :show-inheritance:
