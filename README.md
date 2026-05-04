# SpectraPyle

**Stack thousands of astronomical spectra, uncover hidden signals.**

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-5.0.2-orange)

SpectraPyle is a flexible, scalable tool for stacking galaxy spectra. It shifts spectra
to a common rest frame, normalizes, resamples, sigma-clips, and combines them using median,
mean, weighted mean, or geometric mean statistics. Output is a FITS file ready for
scientific analysis.

**Supported instruments:** Euclid (NISP, grisms `red`/`blue`) · DESI (`merged`)

---

## Quick Start

### Install

```bash
pip install -e ".[all]"
```

### Run via CLI

```bash
python project_root/src/spectraPyle/stacking/stacking.py --config path/to/config.yaml
```

Override individual config keys at runtime:

```bash
python stacking.py --config config.yaml --instrument.grisms '["red","blue"]'
```

### Run via Voilà GUI (config builder)

```bash
python project_root/notebooks/run_gui.py
```

Opens a browser tab with an interactive config builder. No CLI output is expected.

### Minimal YAML config example

```yaml
instrument_name: euclid
  survey_name: wide
  grisms:
  - red
  data_release: Q1

io:
  input_dir: /path/to/catalog
  filename_in: my_catalog
  filename_in_extention: fits
  output_dir: /path/to/output
  grism_io:
    red:
      spectra_dir: /path/to/spectra

redshift:
  z_type: rest_frame

norm:
  norm_type: interval
  norm_range: [5100, 5500]

resampling:
  pixel_resampling_type: lambda
  pixel_size_type: instrumental
  nyquist_sampling: 5.0

sigmaclip:
  sigma_clipping_conditions: 3.0
```

---

## Configuration

Configs are YAML or JSON. All inputs pass through a strict validation pipeline:

```
Widgets / JSON / YAML / CLI
    ↓
normalize_raw_config()        runtime/runtime_adapter.py  — empty strings→None, path coercion
    ↓
StackingConfig (Pydantic v2)  schema/schema.py             — typed field-level validation
    ↓
StackingConfigResolver        schema/schema.py             — cross-field rules, instrument defaults
    ↓
flatten_schema_model()        runtime/runtime_adapter.py  — back to flat dict (legacy shim)
    ↓
Stacking(flat_dict).run()     stacking/stacking.py
```

### Key config blocks

| Block | Purpose |
|---|---|
| `instrument` | `instrument_name` (`euclid`/`desi`), `grisms` list |
| `io` / `grism_io` | Input catalog, output dir, per-grism spectra paths |
| `redshift` | `z_type` (`rest_frame`, `observed_frame`, `custom`, …), `z_value` |
| `norm` | Normalization method and wavelength range |
| `resampling` | Pixel grid type and size |
| `sigmaclip` | Sigma-clipping thresholds |
| `bootstrap` | Bootstrap uncertainty estimation |
| `parallel` | Multiprocessing CPU fraction |
| `plot` | Plotly output options |

### Multi-grism

```yaml
instrument:
  grisms: ["red", "blue"]

io:
  grism_io:
    red:
      spectra_dir: /path/to/red_spectra
    blue:
      spectra_dir: /path/to/blue_spectra
```

Old single-grism configs (`grism_type: str`) are auto-migrated by `migrate_v1_to_v2()` in
`runtime/runtime_adapter.py`.

---

## Output Format

SpectraPyle writes a `.fits` file to `output_dir`.

### HDU[0] — metadata header

```python
from astropy.io import fits

with fits.open("result.fits") as hdu:
    redshift = hdu[0].header["REDSHIFT"]
```

### HDU[1] — stacked spectra table

```python
with fits.open("result.fits") as hdu:
    data = hdu[1].data
    wave = data.field("wavelength")
    spec = data.field("specMean")
```

| Column | Description |
|---|---|
| `wavelength` | Wavelength array (Å) |
| `specMean` / `specMeanDispersion` / `specMeanError` | Mean stack + 1σ dispersion + 1σ uncertainty |
| `specMedian` / `specMedianDispersion` / `specMedianError` | Median stack |
| `specGeometricMean` / `specGeometricMeanDispersion` / `specGeometricMeanError` | Geometric mean — non-positive flux values are excluded per pixel; result is NaN if all pixels have non-positive flux |
| `specWeightedMean` / `specWeightedMeanDispersion` / `specWeightedMeanError` | Inverse-variance weighted mean |
| `initialPixelCount` | Total spectra submitted to the stack |
| `goodPixelCount` | Good flux values used per pixel |
| `badPixelCount` | Bad (masked) pixels per pixel |
| `sigmaClippedCount` | Values removed by sigma-clipping per pixel |

---

## Supported Instruments

| Instrument | Grisms | Spectra modes |
|---|---|---|
| Euclid (NISP) | `red`, `blue` | `individual fits`, `combined fits`, `metadata path` |
| DESI | `merged` | `individual fits`, `combined fits`, `metadata path` |

---

## Architecture

### Config pipeline

```
Widgets / JSON / YAML / CLI
    ↓
normalize_raw_config()        runtime/runtime_adapter.py
    ↓
StackingConfig (Pydantic v2)  schema/schema.py
    ↓
StackingConfigResolver        schema/schema.py
    ↓
flatten_schema_model()        runtime/runtime_adapter.py  ← legacy shim, to be deprecated
    ↓
Stacking(flat_dict).run()     stacking/stacking.py
```

### Key modules

| Module | Responsibility |
|---|---|
| `schema/schema.py` | Pydantic models: `StackingConfig`, `StackingConfigResolver`. Instrument rules from `instruments_rules.json`. |
| `runtime/runtime_adapter.py` | Input normalization, GUI→schema adapter, JSON/YAML loaders, version migration. |
| `stacking/stacking.py` | `Stacking` class: orchestrates the full run. Chunks spectra (500/chunk), writes HDF5, sigma-clips, computes statistics, saves FITS. |
| `process/processes.py` | `main_parallel()`: multiprocessing loop — read → shift → resample → normalize. |
| `instruments/euclid.py` | `readSpec()`, `readSpec_metadata()`, `prepare_stacking()`, `_resolve_filepath()`. |
| `instruments/desi.py` | DESI equivalent of `euclid.py`. |
| `instruments/instruments_rules.json` | Authoritative per-instrument constants, quality defaults, grisms, data releases. |
| `io/IO.py` | Catalog reader, wavelength grid builder, FITS output writer. |
| `io/filename_builder.py` | Auto-generates `filename_out` from config fields. |
| `spectrum/spectra.py` | Per-spectrum read, redshift shift, extinction correction. |
| `spectrum/resampling.py` | Wavelength grid resampling. |
| `spectrum/normalization.py` | Flux normalization; `francis1991_normalize` for template mode. |
| `statistic/statistics.py` | `stack_statistics()`, `bootstrStack()` for bootstrap uncertainties. |
| `plot/plot.py` | Plotly interactive plot of the final stack. |
| `physics/extinction.py` | Galactic extinction correction (Gordon+23, `dust_extinction`). |
| `utils/log.py` | Unified logging for CLI and Voilà GUI. |

### Adding a new instrument

1. Add an entry to `instruments/instruments_rules.json` (constants, quality defaults, surveys, grisms, data releases)
2. Create `instruments/<name>.py` implementing `readSpec()`, `readSpec_metadata()`, `prepare_stacking()`, `_resolve_filepath()`
3. Register per-release filename patterns inside `_resolve_filepath()`

---

## Development

### Install (editable, all extras)

```bash
pip install -e ".[all]"
```

### Lint and format

```bash
ruff check project_root/src/
black project_root/src/
```

### Sanity check (CLI)

```bash
python project_root/src/spectraPyle/stacking/stacking.py --config path/to/default.yaml
```

### Voilà GUI — important note

After modifying `schema.py` or `runtime_adapter.py`, restart the Jupyter kernel for changes to appear in the GUI.

### Generate documentation locally

```bash
cd project_root/docs
make html
# Output: project_root/docs/_build/html/index.html
```

---

## License

MIT — see `LICENSE`.

## Contact

Salvatore Quai — salvatore.quai@gmail.com
