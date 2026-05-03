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
    """Build a validated config from a Jupyter widget collector.

    Parameters
    ----------
    collector_func : callable
        Zero-argument function that returns a flat dict of widget values.

    Returns
    -------
    StackingConfig
        Validated configuration model.
    """
    raw = collector_func()
    raw = normalize_raw_config(raw)
    return build_config_from_dict(raw)


def build_config_from_json(path: str | Path) -> StackingConfig:
    """Build config from a JSON file.

    Parameters
    ----------
    path : str or Path
        Path to JSON config file.

    Returns
    -------
    StackingConfig
        Validated configuration model.
    """
    path = Path(path)
    with open(path, "r") as f:
        raw = json.load(f)
    return build_config_from_dict(raw)


def build_config_from_yaml(path: str | Path) -> StackingConfig:
    """Build config from a YAML file.

    Parameters
    ----------
    path : str or Path
        Path to YAML config file.

    Returns
    -------
    StackingConfig
        Validated configuration model.
    """
    path = Path(path)
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return build_config_from_dict(raw)


def build_config_from_dict(raw: Dict[str, Any]) -> StackingConfig:
    """Build config from a raw dictionary.

    Parameters
    ----------
    raw : dict
        Flat dict from any input source.

    Returns
    -------
    StackingConfig
        Validated configuration model.
    """
    raw = normalize_raw_config(raw)
    return StackingConfig.model_validate(raw)


# =========================================================
# NORMALIZATION PIPELINE
# =========================================================

def normalize_raw_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw flat config dict before Pydantic validation.

    Applies in order: empty-string→None coercion, path normalization,
    lambda-norm unpacking, GUI→schema structural adaptation,
    and missing-block injection.

    Parameters
    ----------
    raw : dict
        Flat dict from any input source (GUI, JSON, YAML, CLI).

    Returns
    -------
    dict
        Normalized dict ready for ``StackingConfig.model_validate()``.
    """
    raw = normalize_empty_strings(raw)
    raw = normalize_paths(raw)
    raw = unpack_lambda_norm(raw)
    raw = adapt_gui_flat_to_schema(raw)
    raw = inject_missing_blocks(raw)
    return raw


# =========================================================
# SCHEMA ADAPTER: flat GUI dict → nested schema dict
# =========================================================

def adapt_gui_flat_to_schema(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the flat widget/JSON dict produced by the GUI into the nested
    structure expected by StackingConfig.

    Key changes from v1 schema:
    - 'grism_type' (single str) is replaced by 'grisms' (List[str])
    - 'spectra_dir' / 'spectra_datafile' (top-level) are replaced by
      'grism_io' (Dict[grism → {spectra_dir, spectra_datafile}])
    """
    if "instrument" in raw:
        # Already structured (e.g. loaded from JSON export)
        return raw

    inst_name = raw.get("instrument_name")
    rules = INSTRUMENT_RULES.get(inst_name, {})

    out = {}

    # ---------------- INSTRUMENT ----------------
    out["instrument"] = dict(
        instrument_name=raw.get("instrument_name"),
        survey_name=raw.get("survey_name"),
        grisms=raw.get("grisms", []),     # List[str] — replaces grism_type
        data_release=raw.get("data_release"),
    )

    quality_rules = rules.get("quality", {})
    quality = {
        k: raw[k]
        for k in quality_rules.keys()
        if raw.get(k) is not None
    }
    out["instrument"]["quality"] = quality or None

    # ---------------- IO ----------------
    # grism_io comes from the GUI as a dict: {grism: {spectra_dir, spectra_datafile}}
    out["io"] = dict(
        spectra_mode=raw.get("spectra_mode"),
        input_dir=raw.get("input_dir"),
        filename_in=raw.get("filename_in"),
        filename_in_extention=raw.get("filename_in_extention"),
        output_dir=raw.get("output_dir"),
        grism_io=raw.get("grism_io", {}),
        filename_out=raw.get("filename_out"),
    )

    # ------- COSMOLOGY -----------
    out["cosmology"] = dict(
        cosmo_H0=raw.get("cosmo_H0"),
        cosmo_Om0=raw.get("cosmo_Om0"),
    )

    # ------ REDSHIFT ----------
    out["redshift"] = dict(
        z_type=raw.get("z_type"),
        z_value=raw.get("z_value"),
    )

    # ------- NORMALIZATION ----------
    out["norm"] = dict(
        spectra_normalization=raw.get("spectra_normalization"),
        conservation=raw.get("conservation"),
        lambda_norm_min=raw.get("lambda_norm_min"),
        lambda_norm_max=raw.get("lambda_norm_max"),
        interval_norm_statistics=raw.get("interval_norm_statistics"),
    )

    # ----------- CATALOGUE -----------
    catalog = dict(
        ID_column_name=raw.get("ID_column_name"),
        redshift_column_name=raw.get("redshift_column_name"),
    )

    metadata_path = raw.get("metadata_path_column_name")
    metadata_file = raw.get("metadata_file_column_name")
    metadata_indx = raw.get("metadata_indx_column_name")

    catalog["metadata"] = (
        dict(
            metadata_path_column_name=metadata_path,
            metadata_file_column_name=metadata_file,
            metadata_indx_column_name=metadata_indx,
        )
        if any([metadata_path, metadata_file, metadata_indx])
        else None
    )

    catalog["galactic_extinction_parameters"] = dict(
        galactic_extinction=raw.get("galactic_extinction", False),
        gal_ext_column_name=raw.get("gal_ext_column_name"),
    )

    custom_col = raw.get("custom_column_name")
    catalog["custom_normalization"] = (
        dict(custom_column_name=custom_col) if custom_col else None
    )

    out["catalog_columns"] = catalog

    # ------- RESAMPLING ------------
    out["resampling"] = dict(
        pixel_resampling_type=raw.get("pixel_resampling_type"),
        pixel_size_type=raw.get("pixel_size_type"),
        pixel_resampling=raw.get("pixel_resampling"),
        nyquist_sampling=raw.get("nyquist_sampling"),
    )

    # ---------------- EDGES ----------------
    val = raw.get("lambda_edges_rest")
    out["lambda_edges_rest"] = tuple(val) if val else None

    val = raw.get("spectrum_edges")
    out["spectrum_edges"] = tuple(val) if val else None

    # ---------- BOOTSTRAP ---------
    out["bootstrap"] = dict(bootstrapping_R=raw.get("bootstrapping_R"))

    # ---------- SIGMACLIP ------------
    out["sigmaclip"] = dict(sigma_clipping_conditions=raw.get("sigma_clipping_conditions"))

    # ---------- PARALLEL ------------
    out["parallel"] = dict(
        multiprocessing=raw.get("multiprocessing"),
        max_cpu_fraction=raw.get("max_cpu_fraction"),
    )

    # ----------- PLOT --------------
    out["plot"] = dict(plot_results=raw.get("plot_results"))

    return out


# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def normalize_empty_strings(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert "" → None recursively."""

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

    Handles top-level path keys AND the nested grism_io dict.
    """
    TOP_LEVEL_PATH_KEYS = {"input_dir", "output_dir"}

    def walk(d):
        if not isinstance(d, dict):
            return d

        out = {}
        for k, v in d.items():
            if k in TOP_LEVEL_PATH_KEYS and isinstance(v, str):
                out[k] = Path(v)
            elif k == "grism_io" and isinstance(v, dict):
                # Normalise per-grism spectra_dir
                out[k] = {
                    grism: {
                        kk: Path(vv) if kk == "spectra_dir" and isinstance(vv, str) else vv
                        for kk, vv in (gcfg.items() if isinstance(gcfg, dict) else {}.items())
                    }
                    for grism, gcfg in v.items()
                }
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

    raise ValueError("lambda_norm_rest must be length-2 or None")


def inject_missing_blocks(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure optional top-level blocks exist so schema defaults apply cleanly."""
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

CURRENT_CONFIG_VERSION = "1.0.0"


def apply_version_migration(raw: Dict[str, Any]) -> Dict[str, Any]:
    version = raw.get("config_version", "1.0.0")

    while version < CURRENT_CONFIG_VERSION:
        if version == "1.0.0":
            raw = migrate_v1_to_v2(raw)
            version = "2.0.0"
            continue
        break

    raw["config_version"] = CURRENT_CONFIG_VERSION
    return raw


def migrate_v1_to_v2(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a v1 (single-grism) config dict to the v2 multi-grism schema.

    Converts old ``grism_type: str`` key to the ``grism_io`` nested structure
    expected by v2. Safe to call on configs that are already v2 (no-op).

    Parameters
    ----------
    raw : dict
        Raw config dict to migrate.

    Returns
    -------
    dict
        Migrated config dict.
    """
    inst = raw.get("instrument", {})
    io   = raw.get("io", {})

    grism_type = inst.pop("grism_type", None)
    if grism_type is not None:
        if grism_type == "all":
            grisms = ["blue", "red"]
        elif grism_type in ("red", "blue", "merged"):
            grisms = [grism_type]
        else:
            grisms = [grism_type]
        inst["grisms"] = grisms

        # Migrate single spectra_dir / spectra_datafile → grism_io
        spectra_dir      = io.pop("spectra_dir", None)
        spectra_datafile = io.pop("spectra_datafile", None)
        if grisms and (spectra_dir or spectra_datafile):
            io["grism_io"] = {
                g: {"spectra_dir": spectra_dir, "spectra_datafile": spectra_datafile}
                for g in grisms
            }

    raw["instrument"] = inst
    raw["io"] = io
    return raw


# =========================================================
# EXPORT HELPERS
# =========================================================

def export_config_to_json(cfg: StackingConfig, path: str | Path):
    """Export a validated config to JSON file.

    Parameters
    ----------
    cfg : StackingConfig
        Validated configuration model.
    path : str or Path
        Output file path.
    """
    path = Path(path)
    with open(path, "w") as f:
        json.dump(cfg.model_dump(mode="json"), f, indent=2)


def export_config_to_yaml(cfg: StackingConfig, path: str | Path):
    """Export a validated config to YAML file.

    Parameters
    ----------
    cfg : StackingConfig
        Validated configuration model.
    path : str or Path
        Output file path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(
            cfg.model_dump(mode="json", exclude_none=True),
            f,
            sort_keys=False,
        )


# =========================================================
# DEBUG / DEV UTILITIES
# =========================================================

def validate_raw_dict(raw: Dict[str, Any]) -> tuple[bool, str | None]:
    """Validate a raw config dict without raising exceptions.

    Parameters
    ----------
    raw : dict
        Config dict to validate.

    Returns
    -------
    bool
        True if valid, False otherwise.
    str or None
        Error message if invalid, None if valid.
    """
    try:
        build_config_from_dict(raw)
        return True, None
    except Exception as e:
        return False, str(e)


# =========================================================
# Flatten schema → flat dict for spectraPyle runtime
# =========================================================

def flatten_schema_model(cfg):
    """Flatten a validated StackingConfig back to a legacy flat dict.

    .. deprecated::
        This function exists only for backward compatibility with the
        :class:`~spectraPyle.stacking.stacking.Stacking` runtime, which
        still consumes flat keys. It will be removed once the runtime
        is refactored to consume the Pydantic model directly.

    Parameters
    ----------
    config : StackingConfig
        Validated config model.

    Returns
    -------
    dict
        Flat dict with legacy keys (e.g. ``config['grism_io']['red']['spectra_dir']``).
    """
    if isinstance(cfg, BaseModel):
        cfg = cfg.model_dump()

    if "instrument" not in cfg:
        print("configuration already flattened")
        return cfg

    flat = {}

    # ---------------- INSTRUMENT ----------------
    inst = cfg.get("instrument", {})
    flat["instrument_name"] = inst.get("instrument_name")
    flat["survey_name"]     = inst.get("survey_name")
    flat["grisms"]          = inst.get("grisms", [])   # List[str]
    flat["data_release"]    = inst.get("data_release")

    # instrument constants
    inst_const = cfg.get("instrument_constants", {})
    flat.update(inst_const)

    # instrument quality
    inst_quality = inst.get("quality", {})
    if inst_quality:
        flat.update(inst_quality)

    # ---------------- IO ----------------
    io = cfg.get("io", {})
    flat["spectra_mode"]          = io.get("spectra_mode")
    flat["input_dir"]             = io.get("input_dir")
    flat["filename_in"]           = io.get("filename_in")
    flat["filename_in_extention"] = io.get("filename_in_extention")
    flat["output_dir"]            = io.get("output_dir")
    flat["filename_out"]          = io.get("filename_out")

    # Per-grism I/O: kept as a nested dict in the flat config
    # Downstream code accesses it as config['grism_io'][grism]['spectra_dir'] etc.
    raw_grism_io = io.get("grism_io", {})
    flat["grism_io"] = {
        grism: {
            "spectra_dir":      Path(gcfg["spectra_dir"]) if gcfg.get("spectra_dir") else None,
            "spectra_datafile": gcfg.get("spectra_datafile"),
        }
        for grism, gcfg in (
            raw_grism_io.items()
            if isinstance(raw_grism_io, dict)
            else {}
        )
    }

    # ---------------- COSMOLOGY ----------------
    cos = cfg.get("cosmology", {})
    flat["cosmo_H0"] = cos.get("cosmo_H0")
    flat["cosmo_Om0"] = cos.get("cosmo_Om0")

    # ---------------- REDSHIFT ----------------
    rz = cfg.get("redshift", {})
    flat["z_type"]  = rz.get("z_type")
    flat["z_value"] = rz.get("z_value")

    # ---------------- NORMALIZATION ----------------
    norm = cfg.get("norm", {})
    flat["spectra_normalization"]   = norm.get("spectra_normalization")
    flat["conservation"]            = norm.get("conservation")
    flat["lambda_norm_rest"]        = [norm.get("lambda_norm_min"), norm.get("lambda_norm_max")]
    flat["interval_norm_statistics"] = norm.get("interval_norm_statistics")

    # ---------------- CATALOG ----------------
    cat = cfg.get("catalog_columns", {})
    flat["ID_column_name"]       = cat.get("ID_column_name")
    flat["redshift_column_name"] = cat.get("redshift_column_name")

    metadata = cat.get("metadata")
    if metadata:
        flat["metadata_path_column_name"] = metadata.get("metadata_path_column_name")
        flat["metadata_file_column_name"] = metadata.get("metadata_file_column_name")
        flat["metadata_indx_column_name"] = metadata.get("metadata_indx_column_name")
    else:
        flat["metadata_path_column_name"] = None
        flat["metadata_file_column_name"] = None
        flat["metadata_indx_column_name"] = None

    gal = cat.get("galactic_extinction_parameters", {})
    flat["galactic_extinction"]  = gal.get("galactic_extinction")
    flat["gal_ext_column_name"]  = gal.get("gal_ext_column_name")

    custom = cat.get("custom_normalization")
    flat["custom_column_name"] = custom.get("custom_column_name") if custom else None

    # ---------------- RESAMPLING ----------------
    res = cfg.get("resampling", {})
    flat["pixel_resampling_type"] = res.get("pixel_resampling_type")
    flat["pixel_size_type"]       = res.get("pixel_size_type")
    flat["pixel_resampling"]      = res.get("pixel_resampling")
    flat["nyquist_sampling"]      = res.get("nyquist_sampling")

    # ---------------- EDGES ----------------
    flat["lambda_edges_rest"] = cfg.get("lambda_edges_rest")
    flat["spectrum_edges"]    = cfg.get("spectrum_edges")

    # ---------------- BOOTSTRAP ----------------
    boot = cfg.get("bootstrap", {})
    flat["bootstrapping_R"] = boot.get("bootstrapping_R")

    # ---------------- SIGMACLIP ----------------
    sig = cfg.get("sigmaclip", {})
    flat["sigma_clipping_conditions"] = sig.get("sigma_clipping_conditions")

    # ---------------- PARALLEL ----------------
    par = cfg.get("parallel", {})
    flat["multiprocessing"]   = par.get("multiprocessing")
    flat["max_cpu_fraction"]  = par.get("max_cpu_fraction")

    # ---------------- PLOT ----------------
    plot = cfg.get("plot", {})
    flat["plot_results"] = plot.get("plot_results")

    # ---------------- LOGGING ----------------
    flat["log_level"] = cfg.get("log_level", "INFO")

    return flat
