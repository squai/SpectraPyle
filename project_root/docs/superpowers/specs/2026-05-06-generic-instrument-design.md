# Generic Instrument Driver — Design Document

**Date:** 2026-05-06  
**Status:** Approved  
**Scope:** New instrument module for standard astronomical FITS without instrument-specific assumptions

---

## Overview

SpectraPyle v5.x currently supports two instruments: Euclid (NISP) and DESI. Users with other spectrographs (X-Shooter, SDSS, custom pipelines, etc.) must implement their own drivers. The **generic** instrument removes this barrier by reading standard FITS formats directly from the file, enabling rapid stacking analysis for any single-grism spectrograph.

### Goals
- Zero instrument-specific assumptions
- Support standard astronomical FITS: binary tables with wavelength columns, WCS headers
- Auto-detection of wavelength range from first spectrum
- Flux scale factor auto-read from FITS header
- Transparent fallback between data formats

---

## Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Grism support | Single grism: `"default"` | Simplifies config; users with multi-grism data should use specific instrument drivers or stack grisms independently |
| Spectra mode | `individual fits` + `combined fits` | Covers most use cases; `metadata path` deferred (adds complexity for rare workflows) |
| Column names | Fixed alias list, no schema changes | Reuses Euclid/DESI pattern (flux/FLUX/SIGNAL, etc.) without expanding schema |
| Wavelength from binary table | Alias search: `wavelength` → `WAVE` → `LAMBDA` | Covers SDSS, X-Shooter, ESO pipeline conventions |
| Wavelength from WCS header | Three formats: SDSS COEFF → Log → Linear | Handles 90% of public data: SDSS plates, ESO WCS, standard FITS |
| Wavelength range | Auto-detect from first spectrum + WARNING | Transparent for homogeneous catalogs; explicit override via `lambda_edges_rest` for mixed samples |
| Flux scale factor | Auto-read header (BSCALE → FLUXSCAL → FLUX_SCALE) | Respects FITS standard scaling; transparent for non-scaled data |
| Quality filters | None (no pixel_mask, no dithers) | Generic instrument assumes pre-processed data; users apply custom QA upstream |
| spectrum_edges | Applied (from config) | Allows per-instrument pixel trimming if needed |
| Pixel size mode | Manual only | No `reference_lambda` / `R` in JSON, so instrumental mode requires user specification |

---

## Implementation

### Files Created / Modified

| File | Action |
|---|---|
| `instruments/generic.py` | **Create** — main driver module |
| `instruments/instruments_rules.json` | **Modify** — add `"generic"` entry |
| `docs/superpowers/specs/2026-05-06-generic-instrument-design.md` | **Create** — this document |

### `instruments/generic.py` — Module Structure

**Public Functions:**
- `readSpec(config, specid, grism) → (lbd, flux, error)` — read individual or combined FITS
- `readSpec_metadata(config, specid, metadata_name, hdu_indx) → (lbd, flux, error)` — path/HDU-driven read
- `prepare_stacking(config, z_stacking, zMin, zMax, lambda_edges) → (lbd_min, lbd_max, grismList)` — compute wavelength bounds

**Internal Helpers:**
- `_read_wavelength_from_table(table)` — extract wavelength column from binary table
- `_read_wavelength_from_header(header, naxis1)` — reconstruct wavelength from WCS keywords
- `_read_scale_factor(header)` — extract flux scale from FITS header
- `_extract_spectrum(hdul, mode)` — unified extraction logic (table or image mode)

**Wavelength Reconstruction (WCS Header):**

Priority order (each checked only if previous fails):

1. **SDSS-style** (fast-log grids):
   ```
   if COEFF0 in header:
       lbd = 10^(COEFF0 + COEFF1 * arange(naxis1))
   ```

2. **Log-linear WCS** (ESO, some X-Shooter pipelines):
   ```
   if 'LOG' in CTYPE1:
       lbd = 10^(CRVAL1 + (arange - (CRPIX1-1)) * CDELT1)
   ```

3. **Linear WCS** (default, standard FITS):
   ```
   lbd = CRVAL1 + (arange - (CRPIX1-1)) * CDELT1
   ```

Default `CRPIX1 = 1.0` if missing.

**Flux Scale Factor:**

Read in order: `BSCALE` → `FLUXSCAL` → `FLUX_SCALE`. If found and ≠ 1.0, logs WARNING and applies to flux and error arrays. Default: `1.0`.

**Spectrum Edges:**

Applied after all extraction: pixels outside `[spectrum_edges[0], spectrum_edges[1])` are set to NaN in flux and error.

### `instruments_rules.json` Entry

```json
"generic": {
  "constants": {
    "units": "from_header",
    "units_scale_factor": 1.0
  },
  "surveys": {
    "generic": {
      "grisms": ["default"],
      "data_release": ["v1"]
    }
  },
  "defaults": {
    "survey": "generic",
    "grism": "default",
    "data_release": "v1"
  }
}
```

**Notes:**
- No `wavelengths`, `R`, or `reference_lambda` — these are required only for instrumental pixel size (not supported)
- No `quality` block — generic assumes clean, pre-processed data
- `units: "from_header"` signals that flux units are user-determined

### Config Example

```yaml
instrument:
  instrument_name: generic
  survey_name: generic
  grisms: [default]
  data_release: v1

io:
  catalog_dir: /path/to/catalogs
  catalog_fname: my_catalog
  catalog_extension: fits
  
  grism_io:
    default:
      spectra_dir: /path/to/spectra/
      spectra_datafile: null  # for individual FITS
      # or set to filename (without .fits) for combined FITS

catalog_columns:
  ID_column_name: ID

resampling:
  pixel_size_type: manual
  pixel_resampling: 2.0   # Angstroms per pixel — user must set

redshift:
  z_type: column
  z_ref: 0.0
  
# Advanced: override auto-detected wavelength range
# (if omitted, range auto-detected from first spectrum)
# lambda_edges_rest: [3000.0, 10000.0]  # rest-frame Angstroms
```

---

## Verification & Testing

### Unit-level Verification

1. **Import and load:**
   ```bash
   python -c "from spectraPyle.schema.schema import INSTRUMENT_RULES; assert 'generic' in INSTRUMENT_RULES"
   ```

2. **Test wavelength reconstruction (WCS):**
   - Create minimal FITS files with COEFF0/COEFF1 (SDSS), CTYPE1=LOG (ESO), and CRVAL1/CDELT1 (linear)
   - Verify `_read_wavelength_from_header()` produces correct arrays

3. **Test column extraction:**
   - Binary table with flux/FLUX/SIGNAL columns
   - Binary table with error/ERROR/NOISE/VAR columns
   - Verify aliases tried in correct order, VAR → sqrt conversion

4. **Test readSpec:**
   - Individual FITS file → verify correct read
   - Combined FITS with per-spectrum HDU → verify correct read
   - Missing wavelength column → verify fallback to WCS

### Integration Testing

1. **Dry-run with real data:**
   ```bash
   python project_root/src/spectraPyle/stacking/stacking.py --config path/to/generic_config.yaml
   ```
   Expected: full stacking run completes, logs show:
   - `pixel_size_type WARNING` (once, at first `readSpec`)
   - `wavelength range inferred WARNING` (if `lambda_edges_rest` not set)
   - Any `flux scale factor WARNINGs` (if BSCALE/FLUXSCAL/FLUX_SCALE != 1.0)

2. **Verify output FITS:**
   - Header contains original instrument metadata (if any)
   - HDU[1] table has stacked wavelength, flux, error, and statistical columns
   - No NaN bleeding from uncovered wavelength regions

3. **Config validation:**
   ```bash
   python -c "from spectraPyle.runtime.runtime_adapter import load_config; load_config('path/to/generic_config.yaml')"
   ```
   Should complete without errors.

---

## Limitations & Future Work

### Known Limitations

1. **Single grism only** — no multi-grism stacking (design choice for simplicity)
2. **Manual pixel size** — cannot use instrumental `R` / `reference_lambda`
3. **No quality flags** — assumes data is pre-processed; no pixel masking, dithering thresholds
4. **No `metadata path` mode** — wavelength/flux paths must come from config, not catalog columns

### Future Enhancements (if needed)

1. Support for `metadata path` mode (read HDU index from catalog column)
2. Optional quality fields (pixel mask, if file provides one)
3. Estimated `R` from pixel spacing for instrumental mode (fragile, currently deferred)

---

## Code Quality Notes

- **No external dependencies** beyond numpy/astropy (already required)
- **Defensive error messages** — report available columns when lookup fails
- **Warning deduplication** — `pixel_size_type` warning logged only once per session
- **Null handling** — graceful fallback (binary table → WCS header, then image mode)
- **Scale factor logging** — only warn if scale ≠ 1.0 (common case is silent)

---

## Author Notes

The design prioritizes **simplicity** and **transparency** over flexibility:
- Fixed alias lists avoid schema bloat
- Three WCS formats cover ~95% of public data
- Auto-detection + explicit override balance convenience and safety
- Quality flags deferred — generic assumes well-processed inputs

This instrument is intended as an on-ramp for new users and one-off analyses. For repeated work or strict QA requirements, users should implement a dedicated driver (as Euclid/DESI do).
