# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SpectraPyle (v5.x) is an astronomical spectral stacking tool: it reads large samples of galaxy spectra, shifts them to a common rest-frame, normalizes, resamples, sigma-clips, and combines them (median/mean/weighted mean/geometric mean) to produce a stacked spectrum saved as FITS. Supported instruments: **Euclid** (NISP, grisms `red`/`blue`) and **DESI** (grism `merged`).

## Commands

Install (editable, all extras):
```bash
cd project_root
pip install -e ".[all]"
```

Run from CLI:
```bash
python project_root/src/spectraPyle/stacking/stacking.py --config path/to/config.yaml
# or with per-key overrides:
python stacking.py --config config.yaml --instrument.grisms '["red","blue"]'
```

Launch the Voilà GUI (config builder):
```bash
python project_root/notebooks/run_spectraPyle.py
```

Lint / format:
```bash
ruff check project_root/src/
black project_root/src/
```

## Verification & Testing
- **Sanity Check (CLI)**:
  `python project_root/src/spectraPyle/stacking/stacking.py --config path/to/default.yaml`
- **Configuration Test**:
  `python -c "from project_root.src.spectraPyle.runtime.runtime_adapter import load_config; load_config('path/to/default.yaml')"`
  
## Notebook Maintenance
- **Clean Notebook**: Before working on or pushing `notebooks/run_spectraPyle.py` (or related .ipynb), clear all outputs to save context/token space:
  `jupyter nbconvert --clear-output --inplace notebooks/make_config.ipynb`
- **Restart Insight**: Since the Voilà GUI depends on the notebook state, always remind the user to restart the Jupyter kernel after making changes to `runtime_adapter.py` or `schema.py`.

## Architecture

### Config pipeline

All inputs (Jupyter widgets, JSON, YAML, CLI) pass through a strict pipeline:

```
raw flat dict
  → normalize_raw_config()       runtime_adapter.py — empty strings→None, path coercion, grism_io restructure
  → StackingConfig (Pydantic v2) schema/schema.py — typed, immutable, validates field-level constraints
  → StackingConfigResolver       schema/schema.py — cross-field rules, instrument rules from JSON
  → flatten_schema_model()       runtime_adapter.py — back to flat dict (TEMPORARY; to be deprecated)
  → Stacking(flat_dict).run()    stacking/stacking.py
```

`flatten_schema_model()` exists only for backward compatibility with the `Stacking` runtime; downstream code still uses flat keys like `config['grism_io'][grism]['spectra_dir']`.

`flatten_schema_model()` is technical debt. Do not refactor it unless explicitly asked. Always use it when passing data to Stacking().

### Key modules

| Module | Role |
|---|---|
| `schema/schema.py` | Pydantic models: `StackingConfig`, `StackingConfigResolver`. All instrument rules are loaded from `instruments/instruments_rules.json`. |
| `runtime/runtime_adapter.py` | Normalization, `adapt_gui_flat_to_schema()`, `flatten_schema_model()`, JSON/YAML export, version migration. |
| `stacking/stacking.py` | `Stacking` class: orchestrates the full run. Chunks spectra (500/chunk), writes intermediate HDF5 (`*_array.h5`), applies sigma-clipping, computes statistics, saves FITS output. Entry point `main(config)`. |
| `process/processes.py` | `main_parallel()`: multiprocessing loop over spectrum IDs; calls per-spectrum read → shift → resample → normalize. |
| `instruments/euclid.py` | `readSpec()` / `readSpec_metadata()`: per-grism file path resolution via `_resolve_filepath()` (per data-release filename patterns). `prepare_stacking()`: returns wavelength range and grism list. |
| `instruments/desi.py` | DESI equivalent. |
| `instruments/instruments_rules.json` | Authoritative source for per-instrument constants, quality defaults, allowed grisms per survey, allowed data releases. |
| `io/IO.py` | Catalog reading (npz/fits/csv), wavelength grid builder, z-stack, output FITS writer. |
| `io/filename_builder.py` | Auto-generates `filename_out` from config fields. |
| `spectrum/` | `spectra.py` (read + shift), `resampling.py`, `normalization.py` (including `francis1991_normalize` for template mode). |
| `statistic/statistics.py` | `stack_statistics()` + `bootstrStack()` for bootstrap uncertainty. |
| `plot/plot.py` | Plotly-based interactive plot of the final stack. |
| `physics/extinction.py` | Galactic extinction correction (Gordon+23 via `dust_extinction`). |

### Instrument rules

`instruments/instruments_rules.json` drives validation in `StackingConfigResolver`. When adding a new instrument or data release:
1. Add an entry to `instruments_rules.json` (constants, quality, surveys, grisms).
2. Add a module under `instruments/<name>.py` implementing `readSpec()`, `readSpec_metadata()`, and `prepare_stacking()`.
3. Add filename patterns in `_resolve_filepath()` inside the new module.

### Multi-grism support

`config['grisms']` is a `List[str]`. Per-grism I/O lives in `config['grism_io']`:
```python
config['grism_io'] = {
    "red":  {"spectra_dir": Path(...), "spectra_datafile": None},
    "blue": {"spectra_dir": Path(...), "spectra_datafile": None},
}
```
Old single-grism configs (with `grism_type: str`) are auto-migrated by `migrate_v1_to_v2()` in `runtime_adapter.py`.

### Spectra modes

`spectra_mode` controls how individual spectra are located:
- `"individual fits"` — one FITS file per object, resolved by `_resolve_filepath()`
- `"combined fits"` — all spectra in a single FITS, indexed by `spectra_datafile`
- `"metadata path"` — path/filename/index come from catalog columns

### Output format

FITS file with two HDUs:
- `HDU[0]` header: `REDSHIFT`, instrument metadata
- `HDU[1]` table: `wavelength`, `specMean/Median/GeometricMean/WeightedMean` + `Dispersion`/`Error` variants, `initialPixelCount`, `goodPixelCount`, `badPixelCount`, `sigmaClippedCount`

## GUI & Notebooks
- **Entry Point**: `notebooks/run_spectraPyle.py` is the main launcher for the Voilà GUI.
- **How to Run**: Use `python notebooks/run_spectraPyle.py`. This starts a local web server (Voilà).
- **Behavior**: It is a wrapper around `notebooks/make_config.ipynb`. Do not expect CLI output; it opens a browser tab.
- **Workflow**: If you modify `schema.py` or `runtime_adapter.py`, the Voilà server/kernel must be manually restarted to reflect changes in the GUI widgets.


## Configuration

Configs are YAML or JSON, loaded via `main(config)` in `stacking.py`. Use `make_config.ipynb` / Voilà GUI to build configs interactively. The schema is fully documented in `schema/schema.py`.

Key config blocks: `instrument`, `io` (with `grism_io`), `cosmology`, `redshift`, `norm`, `resampling`, `catalog_columns`, `bootstrap`, `sigmaclip`, `parallel`, `plot`.

## Development Patterns
- **Memory Management**: When modifying `stacking.py` or `processes.py`, do NOT read the entire file if only one method needs changes. Use `grep` or partial reading.
- **Workflow**: 1. Plan change -> 2. Review `schema.py` impact -> 3. Implement -> 4. Manual check via `stacking.py --config`.
- **Avoid Loops**: Do not attempt to run `pytest` as it is currently a placeholder. Verify logic via dry-runs or by inspecting Pydantic models.

