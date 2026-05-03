---
title: SpectraPyle — README rewrite + Sphinx documentation
date: 2026-05-03
status: approved
---

# Design: README rewrite + Sphinx documentation

## Context

The current `project_root/README.md` is outdated: it references removed scripts (`stackingEuclid.py`), non-existent notebooks, and the old single-grism CLI interface. It completely omits the v5.x architecture (Pydantic config pipeline, multi-grism support, Voilà GUI, DESI instrument, sigma-clipping, bootstrap). The codebase also lacks structured documentation: most modules have no docstrings, `__init__.py` files are empty, and there is no Sphinx setup. Goal: a modern README and a full Sphinx-based documentation site ready for ReadTheDocs.

---

## Part 1 — README rewrite (`project_root/README.md`)

**Audience:** both scientific users (quick start, output format) and developers (architecture, contribution).

### Sections

1. **Header** — project name, one-line tagline, version/instrument badges
2. **Quick Start** — `pip install -e ".[all]"`, CLI invocation, Voilà GUI launch, minimal YAML config example
3. **Configuration** — key config blocks (`instrument`, `grism_io`, `redshift`, `norm`, `resampling`, `sigmaclip`, `bootstrap`, `parallel`, `plot`); multi-grism `grism_io` structure; CLI overrides; link to Voilà GUI
4. **Output Format** — FITS HDUs table (all fields: `specMean/Median/GeometricMean/WeightedMean` + `Dispersion`/`Error` variants, pixel count columns); Python snippets to read header and data; note that geometric mean excludes flux ≤ 0 per pixel (NaN if all pixels non-positive)
5. **Supported Instruments** — Euclid (NISP, grisms `red`/`blue`) and DESI (`merged`)
6. **Architecture** (dev section) — config pipeline ASCII diagram, key modules table with relative paths, multi-grism note + `migrate_v1_to_v2()` for legacy configs
7. **Development** — dev install, lint (`ruff`), format (`black`), adding a new instrument (3 steps), Voilà kernel restart note
8. **License & Contact** — TBD license, salvatore.quai@gmail.com

---

## Part 2 — Sphinx documentation

**Stack:** Sphinx + `sphinx.ext.autodoc` + `sphinx.ext.napoleon` (NumPy docstrings) + `furo` theme.

**Directory layout:**
```
project_root/docs/
├── conf.py
├── index.rst
├── quickstart.rst
├── api/
│   ├── stacking.rst
│   ├── schema.rst
│   ├── processes.rst
│   ├── instruments.rst
│   ├── io.rst
│   ├── spectrum.rst
│   ├── statistic.rst
│   └── utils.rst
└── _static/
```

**Docstring style:** NumPy (already used in `spectra.py::useSpec`). Every public module, class, and function gets: one-line summary, extended description where non-obvious, Parameters/Returns/Raises sections.

**Docstring writing order (top-down, entry-point first):**
1. `stacking/stacking.py` — `Stacking` class + `run()`, `main()`
2. `process/processes.py` — `main_parallel()`
3. `schema/schema.py` — all Pydantic models + `StackingConfigResolver`
4. `runtime/runtime_adapter.py` — `normalize_raw_config()`, `adapt_gui_flat_to_schema()`, `flatten_schema_model()`, `migrate_v1_to_v2()`
5. `instruments/euclid.py` — `readSpec()`, `readSpec_metadata()`, `prepare_stacking()`, `_resolve_filepath()`
6. `instruments/desi.py` — same interface as Euclid
7. `io/IO.py` — catalog readers, wavelength grid builder, FITS writer
8. `io/filename_builder.py`
9. `spectrum/spectra.py` — `useSpec()` (already documented, review only)
10. `spectrum/normalization.py`, `spectrum/resampling.py`
11. `statistic/statistics.py` — `stack_statistics()`, `bootstrStack()`
12. `plot/plot.py`
13. `physics/extinction.py`
14. `utils/log.py`
15. All `__init__.py` — add `__all__` and one-line package docstring

**ReadTheDocs deploy:** `.readthedocs.yaml` at repo root; account creation deferred until after local build passes (`make html`).

---

## Division of work

| Task | Who |
|---|---|
| Rewrite README | Claude writes, user reviews |
| Sphinx project setup (`conf.py`, `.rst` files, `pyproject.toml` extras) | Claude |
| All docstrings (NumPy style, all modules) | Claude writes, user reviews/corrects |
| `.readthedocs.yaml` | Claude |
| ReadTheDocs account + repo connection | User (after local build passes) |
