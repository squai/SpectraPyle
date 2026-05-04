# SpectraPyle Documentation Overhaul — Design Spec

**Date:** 2026-05-04
**Status:** Approved

## Context

SpectraPyle v5.x has a Sphinx/ReadTheDocs setup (`furo` theme) but lacks narrative concept pages for its core algorithms (normalization, resampling), has no citation/acknowledgment guidance for users, and has no GUI documentation. Users of the tool — primarily astronomers — need:

- A clear reference for choosing normalization and resampling modes (with the math)
- Copy-pasteable citation and ELSA acknowledgment text
- A visual guided tour of the Voilà config GUI for first-time users
- Complete API docstrings (a few gaps remain)

## Scope

Four new Sphinx pages + one Playwright capture script + targeted docstring fixes. No changes to existing pages or the package runtime.

---

## 1. Sphinx Structure

Reorganize `project_root/docs/index.rst` into three labeled toctree sections:

```
User Guide
  quickstart        (existing — minor additions only)
  gui-tour          (NEW)
  citation          (NEW)

Concepts
  normalization     (NEW)
  resampling        (NEW)

API Reference
  api/schema        (existing, unchanged)
  api/stacking      (existing, unchanged)
  api/processes     (existing, unchanged)
  api/instruments   (existing, unchanged)
  api/io            (existing, unchanged)
  api/spectrum      (existing, unchanged)
  api/statistic     (existing, unchanged)
  api/plot          (existing, unchanged)
  api/utils         (existing, unchanged)
```

**Files modified:** `project_root/docs/index.rst`
**Files added:** `gui-tour.rst`, `citation.rst`, `normalization.rst`, `resampling.rst` (all in `project_root/docs/`)

---

## 2. `normalization.rst` — Concept Guide

Structure:
1. Intro paragraph: why per-spectrum normalization matters before stacking
2. Comparison table: config value | function | description | typical use case
3. One subsection per method with `.. math::` formula:
   - `no_norm` — identity; use with `francis1991` template normalization
   - `median` → `normSpecMed`: divide by `nanmedian(flux)`
   - `interval` → `normSpecInterv`: divide by statistic over `[λ_min, λ_max]`; statistic = median/mean/max/min
   - `integrated_mean` → `normSpecIntegrMean`: divide by `∫flux dλ / Δλ`
   - `custom` → `normSpecCustom`: divide by a user-supplied catalog column value
4. Cross-links to `api/spectrum` for parameter details

**File:** `project_root/docs/normalization.rst`

---

## 3. `resampling.rst` — Concept Guide

Structure:
1. Intro: why flux-conservative resampling is required for stacking spectra with different wavelength grids
2. Algorithm section: Fruchter & Hook (2002) fractional pixel overlap matrix; reference to `resamplingSpecFluxCons` in `spectrum/resampling.py`
3. Grid modes table (`pixel_resampling_type` × `pixel_size_type`):

   | | `manual` (fixed pixel) | `instrumental` (Nyquist) |
   |---|---|---|
   | `linear` | user sets Δλ [Å] | Δλ = λ_ref / (R × n_nyq) via `dlam_from_R` |
   | `logarithmic` | user sets Δlog₁₀λ | Δlog₁₀λ = 1/(R × n_nyq × ln10) via `dloglam_from_R` |

4. Note on velocity-constant pixel size of logarithmic grids (constant Δv/c = ln(10) × Δlog₁₀λ)
5. Config keys: `pixel_resampling_type`, `pixel_size_type`, `pixel_resampling`, `nyquist_sampling`
6. Cross-links to `api/spectrum` and `api/io` (wavelength grid builder)

**File:** `project_root/docs/resampling.rst`

---

## 4. `citation.rst` — Citation & Acknowledgments

Structure:
1. **How to cite** — primary reference is the paper (arXiv:2509.16120); three copy-pasteable blocks:
   - BibTeX entry
   - APA/author-year format
   - ADS-style
2. **Acknowledgment text** — verbatim ELSA Horizon Europe grant text from the paper's Acknowledgments section; users must include this when publishing results obtained with SpectraPyle
3. **Instrument-specific notes** — note that Euclid users must additionally follow Euclid Consortium acknowledgment guidelines

The exact BibTeX and ELSA grant text are fetched from arXiv:2509.16120 during implementation.

**File:** `project_root/docs/citation.rst`

---

## 5. `gui-tour.rst` — Guided Tour

Structure (5 sections, one screenshot each):
1. **Launching the GUI** — full browser screenshot after `python notebooks/run_spectraPyle.py`
2. **Instrument tab** — instrument/survey/grisms/data-release; QC advanced section
3. **Input/Output tab** — catalogue chooser, spectra format, per-grism paths
4. **Catalogue tab** — ID/redshift column dropdowns, metadata mode, extinction, custom norm
5. **Stack Parameters tab** — normalization, resampling, wavelength range, sigma-clip, bootstrap, cosmology

Each section: `.. figure::` directive → short paragraph → bullet list of key widgets.

Screenshot filenames: `docs/_static/screenshots/gui_launch.png`, `gui_instrument.png`, `gui_io.png`, `gui_catalogue.png`, `gui_stack_params.png`.

**File:** `project_root/docs/gui-tour.rst`

### Playwright Capture Script

**File:** `project_root/docs/tools/capture_gui.py`

Behavior:
1. Launch Voilà via subprocess (`python notebooks/run_spectraPyle.py`)
2. Wait for full page render (poll for widget visibility)
3. Click each tab in sequence; wait for widgets; save screenshot
4. Exit cleanly; kill Voilà subprocess

Dependency: `playwright` (`pip install playwright && playwright install chromium`) — docs-only dev tool, not added to `pyproject.toml`.

---

## 6. Docstring Fixes

Targeted — no broad refactor:

| File | Target | Fix |
|---|---|---|
| `project_root/src/spectraPyle/spectrum/normalization.py` | `normSpecCustom` | Add NumPy-style docstring |
| `project_root/src/spectraPyle/schema/schema.py` | `CatalogColumnsConfig`, `GalacticExtinctionConfig`, `MetadataColumnsConfig`, `CustomNormalizationColumnsConfig`, `GrismIOConfig` | Add class-level NumPy docstrings |
| `project_root/src/spectraPyle/stacking/stacking.py` | Module level | Add one-paragraph module docstring |

---

## 7. Verification

1. `cd project_root/docs && make html` — build must complete with 0 errors, 0 warnings (RTD has `fail_on_warning: false` but aim for clean)
2. Open `_build/html/index.html` — confirm three toctree sections appear in furo sidebar
3. Check each new page renders correctly: equations display, figures load (or show alt text if screenshots not yet captured)
4. Run `python project_root/docs/tools/capture_gui.py` — confirm 5 PNG files appear in `docs/_static/screenshots/`
5. Rebuild docs after screenshots added — confirm figures render in `gui-tour.html`
6. Spot-check autodoc pages: `api/spectrum.html` should now show `normSpecCustom` docstring
