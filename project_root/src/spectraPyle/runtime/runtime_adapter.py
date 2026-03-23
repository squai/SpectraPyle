"""
spectraPyle Runtime Adapter

Central boundary layer between external inputs (UI, JSON, API, CLI)
and the validated internal Pydantic schema.

Design goals:
-------------
- UI agnostic
- Version migration support
- Backward compatibility
- Central normalization layer
- Single source of config building truth
"""

from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Any, Dict, Callable
from pydantic import BaseModel

from spectraPyle.schema.schema import StackingConfig

# =========================================================
# INSTRUMENT RULES
# =========================================================

INSTRUMENT_RULES_PATH = Path(__file__).parent.parent / "instruments" / "instruments_rules.json"

with open(INSTRUMENT_RULES_PATH, "r") as f:
    INSTRUMENT_RULES: Dict[str, Any] = json.load(f)


# =========================================================
# PUBLIC API
# =========================================================

def build_config_from_widgets(collector_func: Callable[[], Dict[str, Any]]) -> StackingConfig:
    """
    Build validated config from widgets.

    Parameters
    ----------
    collector_func : callable
        Function returning raw dict config from widgets.

    Returns
    -------
    StackingConfig
    """
    raw = collector_func()
    raw = normalize_raw_config(raw)
    return build_config_from_dict(raw)


def build_config_from_json(path: str | Path) -> StackingConfig:
    """
    Load config from JSON file and validate.
    """
    path = Path(path)

    with open(path, "r") as f:
        raw = json.load(f)

    return build_config_from_dict(raw)

def build_config_from_yaml(path: str | Path) -> StackingConfig:

    path = Path(path)

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    return build_config_from_dict(raw)


def build_config_from_dict(raw: Dict[str, Any]) -> StackingConfig:
    """
    Core config builder used everywhere.
    """

    raw = normalize_raw_config(raw)

    #return StackingConfig(**raw)
    return StackingConfig.model_validate(raw)

# =========================================================
# NORMALIZATION PIPELINE
# =========================================================

def normalize_raw_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    
    raw = normalize_empty_strings(raw)
    raw = normalize_paths(raw)
    raw = unpack_lambda_norm(raw)
    raw = adapt_gui_flat_to_schema(raw)
    raw = inject_missing_blocks(raw)
    #raw = apply_version_migration(raw)
    
    return raw


# =========================================================
# SCHEMA ADAPTER (flat dictionary from widget to nested of schema.py
# =========================================================
def adapt_gui_flat_to_schema(raw: Dict[str, Any]) -> Dict[str, Any]:
    if "instrument" in raw:
        return raw
    
    inst_name = raw.get("instrument_name")
    rules = INSTRUMENT_RULES.get(inst_name, {})
    
    #out = dict(raw)  # Preserve ALL top-level fields!
    
    out = dict()
    
    # ---------------- INSTRUMENT ----------------
    out["instrument"] = dict(
        instrument_name=raw.get("instrument_name"),
        survey_name=raw.get("survey_name"),
        grism_type=raw.get("grism_type"),
        data_release=raw.get("data_release"),
    )
    
    """
    out["instrument"]["quality"] = dict(
        pixel_mask=raw.get("pixel_mask"),
        n_min_dithers=raw.get("n_min_dithers"),
    )
    """
    
    quality_rules = rules.get("quality", {})

    quality = {
        key: raw[key]
        for key in quality_rules.keys()
        if raw.get(key) is not None and quality_rules is not None
    }

    out["instrument"]["quality"] = quality or None
    
    # ---------------- IO --------------------
    out["io"] = dict(
        spectra_mode=raw.get("spectra_mode"),
        input_dir=raw.get("input_dir"),
        filename_in=raw.get("filename_in"),
        filename_in_extention=raw.get("filename_in_extention"),
        output_dir=raw.get("output_dir"),
        spectra_dir=raw.get("spectra_dir"),
        spectra_datafile=raw.get("spectra_datafile"),
        filename_out=raw.get("filename_out"),
    )
    
    # ------- COSMOLOGY -----------
    out["cosmology"] = dict(
        cosmo_H0=raw.get("cosmo_H0"),
        cosmo_Om0=raw.get("cosmo_Om0"),
    )
    
    # ------ Redshift ----------
    out["redshift"] = dict(
        z_type=raw.get("z_type"),
        z_value=raw.get("z_value"),
    )
    
    # ------- Normalization ----------
    out["norm"] = dict(
        spectra_normalization=raw.get("spectra_normalization"),
        conservation=raw.get("conservation"),
        lambda_norm_min=raw.get("lambda_norm_min"),
        lambda_norm_max=raw.get("lambda_norm_max"),
        interval_norm_statistics=raw.get("interval_norm_statistics"),
    )
    
    # ----------- Catalogue -----------
    catalog = dict(
        ID_column_name=raw.get("ID_column_name"),
        redshift_column_name=raw.get("redshift_column_name"),
    )
    
    # === metadata ===
    metadata_path = raw.get("metadata_path_column_name")
    metadata_file = raw.get("metadata_file_column_name")
    metadata_indx = raw.get("metadata_indx_column_name")

    if any([metadata_path, metadata_file, metadata_indx]):
        catalog["metadata"] = dict(
            metadata_path_column_name = metadata_path,
            metadata_file_column_name = metadata_file,
            metadata_indx_column_name = metadata_indx,
        )
    else:
        catalog["metadata"] = None

    # --- galactic extinction ---
    catalog["galactic_extinction_parameters"] = dict(
        galactic_extinction = raw.get("galactic_extinction", False),
        gal_ext_column_name = raw.get("gal_ext_column_name"),
    )

    # --- custom normalization ---
    custom_col = raw.get("custom_column_name")
    catalog["custom_normalization"] = (
        dict(custom_column_name=custom_col)
        if custom_col else None
    )

    out["catalog_columns"] = catalog
    
    # ------- Resampling ------------
    out["resampling"] = dict(
        pixel_resampling_type=raw.get("pixel_resampling_type"),
        pixel_size_type=raw.get("pixel_size_type"),
        pixel_resampling=raw.get("pixel_resampling"),
        nyquist_sampling=raw.get("nyquist_sampling"),
    )
    
    # ---------------- False → None Fix ----------------
    
    val = raw.get("lambda_edges_rest")
    out["lambda_edges_rest"] = tuple(val) if val else None
    
    val = raw.get("spectrum_edges")
    out["spectrum_edges"] = tuple(val) if val else None
    
    """
    if raw.get("lambda_edges_rest") in [False, "", None]:
        out["lambda_edges_rest"] = None
    else:
        out["lambda_edges_rest"]=raw.get("lambda_edges_rest")

    if raw.get("spectrum_edges") in [False, "", None]:
        out["spectrum_edges"] = None
    else:
        out["spectrum_edges"]=raw.get("spectrum_edges")
    """
        
    # ---------- bootstrap ---------
    out["bootstrap"] = dict(
        bootstrapping_R=raw.get("bootstrapping_R")
    )
    
    # ---------- sigmaclip ------------
    out["sigmaclip"] = dict(
        sigma_clipping_conditions=raw.get("sigma_clipping_conditions"),
    )
    
    # ---------- parallel ------------
    out["parallel"] = dict(
        multiprocessing=raw.get("multiprocessing"),
        max_cpu_fraction=raw.get("max_cpu_fraction"),
    )
    
    
    # ----------- plot --------------
    out["plot"] = dict(
        plot_results=raw.get("plot_results")
    )
    
    return out



# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def normalize_empty_strings(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert "" → None recursively.
    """

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(val) for k, val in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if v == "":
            return None
        return v

    return walk(raw)


def normalize_paths(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert string paths → Path objects where expected.
    """

    PATH_KEYS = {
        "input_dir",
        "output_dir",
        "spectra_dir",
    }

    def walk(d):
        if not isinstance(d, dict):
            return d

        out = {}

        for k, v in d.items():
            if k in PATH_KEYS and isinstance(v, str):
                out[k] = Path(v)
            elif isinstance(v, dict):
                out[k] = walk(v)
            else:
                out[k] = v

        return out

    return walk(raw)

def unpack_lambda_norm(raw: dict) -> dict:

    lam = raw.pop("lambda_norm_rest", None)

    if lam is None:
        raw["lambda_norm_min"] = None
        raw["lambda_norm_max"] = None
        return raw

    if isinstance(lam, (list, tuple)) and len(lam) == 2:
        raw["lambda_norm_min"] = lam[0]
        raw["lambda_norm_max"] = lam[1]
        return raw

    raise ValueError("lambda_norm_rest must be length 2 or None")


def inject_missing_blocks(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure optional top-level blocks exist so schema defaults apply cleanly.
    """

    raw.setdefault("cosmology", {})
    raw.setdefault("bootstrap", {})
    raw.setdefault("sigmaclip", {})
    raw.setdefault("parallel", {})
    raw.setdefault("output", {})
    raw.setdefault("resampling", {})
    raw.setdefault("norm", {})
    raw.setdefault("redshift", {})
    raw.setdefault("io", {})

    return raw


# =========================================================
# VERSIONING
# =========================================================

CURRENT_CONFIG_VERSION = "1.0.0"  # String!

def apply_version_migration(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade config to latest version if needed."""
    version = raw.get("config_version", "1.0.0")  # Fixed quote + string default
    
    while version < CURRENT_CONFIG_VERSION:  # String comparison safe for "1" < "2"
        if version == "1.0.0":
            raw = migrate_v1_to_v2(raw)
            version = "2.0.0"
            continue
        break
    
    raw["config_version"] = CURRENT_CONFIG_VERSION
    return raw



# =========================================================
# MIGRATIONS (Future Safe)
# =========================================================

def migrate_v1_to_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    migration placeholder.
    """

    # Example future logic:
    # if "old_field" in raw:
    #     raw["new_field"] = raw.pop("old_field")

    return raw


# =========================================================
# EXPORT HELPERS
# =========================================================

def export_config_to_json(cfg: StackingConfig, path: str | Path):
    """
    Export validated config to JSON.
    """

    path = Path(path)

    with open(path, "w") as f:
        json.dump(
            cfg.model_dump(mode="json"),
            f,
            indent=2,
        )

def export_config_to_yaml(cfg, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        yaml.safe_dump(
            cfg.model_dump(mode="json", exclude_none=True),
            f,
            sort_keys=False
        )

# =========================================================
# DEBUG / DEV UTILITIES
# =========================================================

def validate_raw_dict(raw: Dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate raw config without raising.
    """

    try:
        build_config_from_dict(raw)
        return True, None
    except Exception as e:
        return False, str(e)

# ========================================================
# Flattening config for spectraPyle
# ========================================================
def flatten_schema_model(cfg):

    # -------- MODEL → DICT --------
    if isinstance(cfg, BaseModel):
        cfg = cfg.model_dump()

    # -------- ALREADY FLAT --------
    if "instrument" not in cfg:
        print("configuration already flatten")
        return cfg

    # -------- NORMAL FLATTEN --------
    flat = {}

    #flat = dict(cfg)  # preserve top level just in case
    #flat = dict()
    
    # ---------------- INSTRUMENT ----------------
    inst = cfg.get("instrument", {})
    flat["instrument_name"] = inst.get("instrument_name")
    flat["survey_name"] = inst.get("survey_name")
    flat["grism_type"] = inst.get("grism_type")
    flat["data_release"] = inst.get("data_release")
    
    # === instrument constants (may vary depending on the instrument) ===
    inst_const = cfg.get("instrument_constants", {})
    flat.update(inst_const)
    
    # === instrument quality (may vary depending on the instrument) ===
    inst_quality = inst.get("quality", {})
    if inst_quality is not None:
        flat.update(inst_quality) 

    # ---------------- IO ----------------
    io = cfg.get("io", {})
    flat["spectra_mode"] = io.get("spectra_mode")
    flat["input_dir"] = io.get("input_dir")
    flat["filename_in"] = io.get("filename_in")
    flat["filename_in_extention"] = io.get("filename_in_extention")
    flat["output_dir"] = io.get("output_dir")
    flat["spectra_dir"] = io.get("spectra_dir")
    flat["spectra_datafile"] = io.get("spectra_datafile")
    flat["filename_out"] = io.get("filename_out")

    # ---------------- COSMOLOGY ----------------
    cos = cfg.get("cosmology", {})
    flat["cosmo_H0"] = cos.get("cosmo_H0")
    flat["cosmo_Om0"] = cos.get("cosmo_Om0")

    # ---------------- REDSHIFT ----------------
    rz = cfg.get("redshift", {})
    flat["z_type"] = rz.get("z_type")
    flat["z_value"] = rz.get("z_value")

    # ---------------- NORMALIZATION ----------------
    norm = cfg.get("norm", {})
    flat["spectra_normalization"] = norm.get("spectra_normalization")
    flat["conservation"] = norm.get("conservation")
    #flat["lambda_norm_min"] = norm.get("lambda_norm_min")
    #flat["lambda_norm_max"] = norm.get("lambda_norm_max")
    flat["lambda_norm_rest"] = [norm.get("lambda_norm_min"), norm.get("lambda_norm_max")]
    flat["interval_norm_statistics"] = norm.get("interval_norm_statistics")

    # ---------------- CATALOG ----------------
    cat = cfg.get("catalog_columns", {})

    flat["ID_column_name"] = cat.get("ID_column_name")
    flat["redshift_column_name"] = cat.get("redshift_column_name")

    # ---- metadata ----
    metadata = cat.get("metadata")
    if metadata:
        flat["metadata_path_column_name"] = metadata.get("metadata_path_column_name")
        flat["metadata_file_column_name"] = metadata.get("metadata_file_column_name")
        flat["metadata_indx_column_name"] = metadata.get("metadata_indx_column_name")
    else:
        flat["metadata_path_column_name"] = None
        flat["metadata_file_column_name"] = None
        flat["metadata_indx_column_name"] = None

    # ---- galactic extinction ----
    gal = cat.get("galactic_extinction_parameters", {})
    flat["galactic_extinction"] = gal.get("galactic_extinction")
    flat["gal_ext_column_name"] = gal.get("gal_ext_column_name")

    # ---- custom normalization ----
    custom = cat.get("custom_normalization")
    flat["custom_column_name"] = (
        custom.get("custom_column_name") if custom else None
    )

    # ---------------- RESAMPLING ----------------
    res = cfg.get("resampling", {})
    flat["pixel_resampling_type"] = res.get("pixel_resampling_type")
    flat["pixel_size_type"] = res.get("pixel_size_type")
    flat["pixel_resampling"] = res.get("pixel_resampling")
    flat["nyquist_sampling"] = res.get("nyquist_sampling")

    # ---------------- EDGES ----------------
    flat["lambda_edges_rest"] = cfg.get("lambda_edges_rest")
    flat["spectrum_edges"] = cfg.get("spectrum_edges")

    # ---------------- BOOTSTRAP ----------------
    boot = cfg.get("bootstrap", {})
    flat["bootstrapping_R"] = boot.get("bootstrapping_R")

    # ---------------- SIGMACLIP ----------------
    sig = cfg.get("sigmaclip", {})
    flat["sigma_clipping_conditions"] = sig.get("sigma_clipping_conditions")

    # ---------------- PARALLEL ----------------
    par = cfg.get("parallel", {})
    flat["multiprocessing"] = par.get("multiprocessing")
    flat["max_cpu_fraction"] = par.get("max_cpu_fraction")

    # ---------------- PLOT ----------------
    plot = cfg.get("plot", {})
    flat["plot_results"] = plot.get("plot_results")
    
    return flat
