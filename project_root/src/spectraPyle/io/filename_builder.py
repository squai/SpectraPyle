"""
Auto-generation of output FITS filenames from configuration.

Provides :func:`build_filename` which constructs a short, structured filename::

    <SURVEY>_<GRISMS>_<DR>_<CATALOG>_<ZCOL>_<NORM>[_<L0>-<L1>]_s<SIGMA>_<PXTOKEN>_<HASH8>

``<PXTOKEN>`` encodes resampling mode and value:

- ``pixel_resampling`` set   → ``px<value>lin`` / ``px<value>log``
- ``pixel_resampling`` None  → ``pxLin<nyq>Nyq`` / ``pxLog<nyq>Nyq``

Examples::

    EWS_red_Q1_targets_Z_SPEC_intv_7000-8000_s3_px5lin_3f8a2b1c
    DESI_merged_DR1_catalog_spe_z_med_s3_pxLin5Nyq_70958031
"""

import hashlib
import json
from pathlib import Path

_NORM_CODE = {
    "no_normalization": "nonorm",
    "median": "med",
    "mean": "mean",
    "interval": "intv",
    "custom": "cust",
    "template": "tmpl",
}

_HASH_FIELDS = [
    "instrument_name", "survey_name", "grisms", "data_release",
    "filename_in", "redshift_column_name",
    "spectra_normalization", "lambda_norm_min", "lambda_norm_max",
    "sigma_clipping_conditions",
    "pixel_resampling", "pixel_resampling_type", "nyquist_sampling",
    "bootstrapping_R",
    "pixel_mask", "n_min_dithers",
]


def _config_hash(cfg):
    """Return the first 8 hex chars of SHA-256 over science-relevant config fields."""
    science = {k: cfg.get(k) for k in _HASH_FIELDS}
    serialised = json.dumps(science, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()[:8]


def build_filename(cfg):
    """Auto-generate the output FITS filename stem from config fields.

    Parameters
    ----------
    cfg : dict
        Flat stacking config dict (produced by ``flatten_schema_model``).

    Returns
    -------
    str
        Filename stem (without ``.fits`` extension).
    """
    parts = []

    # instrument context
    parts.append(cfg["survey_name"])
    parts.append("-".join(cfg["grisms"]))
    parts.append(cfg["data_release"])

    # catalog
    parts.append(Path(cfg["filename_in"]).stem)

    # redshift column (omit if not set)
    zcol = cfg.get("redshift_column_name")
    if zcol:
        parts.append(zcol)

    # normalization
    norm = cfg["spectra_normalization"]
    parts.append(_NORM_CODE.get(norm, norm))

    if norm == "interval":
        l0, l1 = cfg["lambda_norm_rest"]
        parts.append(f"{int(l0)}-{int(l1)}")

    # sigma clipping
    sigma = cfg["sigma_clipping_conditions"]
    parts.append(f"s{sigma:g}")

    # resampling (always present)
    px = cfg.get("pixel_resampling")
    restype_key = cfg.get("pixel_resampling_type")
    if px is not None:
        restype = "log" if restype_key == "log" else "lin"
        parts.append(f"px{px:g}{restype}")
    else:
        nyq = cfg.get("nyquist_sampling", 5)
        restype = "Log" if restype_key == "log" else "Lin"
        parts.append(f"px{restype}{nyq:g}Nyq")

    # 8-char config hash
    parts.append(_config_hash(cfg))

    return "_".join(parts)
