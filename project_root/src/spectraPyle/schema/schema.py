"""
Widgets / JSON / CLI
        ↓
normalize_raw_config    (flat → structured)
        ↓
StackingConfig          (validation)
        ↓
StackingConfigResolver  (rules + defaults)
        ↓
FINAL CONFIG (typed, stable)
        ↓
stack.run()
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Literal, Dict, Any, Tuple
from pathlib import Path
import json
import numpy as np


# =========================================================
# Load Instrument Rules
# =========================================================

INSTRUMENT_RULES_PATH = Path(__file__).parent.parent / "instruments" / "instruments_rules.json"

with open(INSTRUMENT_RULES_PATH, "r") as f:
    INSTRUMENT_RULES: Dict[str, Any] = json.load(f)

AVAILABLE_INSTRUMENTS = tuple(INSTRUMENT_RULES.keys())


# =========================================================
# IO CONFIG
# =========================================================

SpectraMode = Literal[
    "individual fits",
    "metadata path",
    "combined fits"
]


class GrismIOConfig(BaseModel):
    """Per-grism I/O paths (directory for individual files, or combined FITS filename)."""

    spectra_dir: Optional[Path] = None
    spectra_datafile: Optional[str] = None   # filename without .fits extension

    class Config:
        frozen = True


class IOConfig(BaseModel):
    """Input/output paths and spectra access mode.

    Parameters
    ----------
    spectra_mode : {"individual fits", "combined fits", "metadata path"}
        How individual spectra are located.
    input_dir : Path, optional
        Directory containing the catalog file.
    filename_in : str, optional
        Catalog filename without extension.
    filename_in_extention : {"fits", "csv", "npz"}, optional
        Catalog file extension.
    output_dir : Path, optional
        Directory where the stacked FITS will be written.
    grism_io : dict[str, GrismIOConfig]
        Per-grism I/O paths keyed by grism name (e.g. ``"red"``, ``"blue"``).
    filename_out : str
        Output filename stem. ``"AUTO"`` triggers automatic generation via
        :func:`~spectraPyle.io.filename_builder.build_filename`.
    """

    spectra_mode: SpectraMode = "individual fits"

    input_dir: Optional[Path] = None
    filename_in: Optional[str] = None
    filename_in_extention: Optional[Literal["fits", "csv", "npz"]] = None

    output_dir: Optional[Path] = None

    # Per-grism I/O:  {"red": GrismIOConfig(...), "blue": GrismIOConfig(...)}
    grism_io: Dict[str, GrismIOConfig] = Field(default_factory=dict)

    filename_out: str = "AUTO"

    class Config:
        frozen = True


# =========================================================
# REDSHIFT CONFIG
# =========================================================

RedshiftType = Literal[
    "rest_frame",
    "observed_frame",
    "minimum_z",
    "maximum_z",
    "median_z",
    "custom"
]


class RedshiftConfig(BaseModel):
    """Redshift handling and stacking reference frame.

    Parameters
    ----------
    z_type : {"rest_frame", "observed_frame", "minimum_z", "maximum_z", "median_z", "custom"}
        Type of stacking reference redshift.
    z_value : float, optional
        Explicit redshift value when ``z_type = "custom"``.
    """

    z_type: RedshiftType = "rest_frame"
    z_value: Optional[float] = None

    def requires_catalog_column(self) -> bool:
        """Check if this redshift type requires a redshift column in the catalog."""
        return self.z_type != "observed_frame"

    @model_validator(mode="after")
    def validate_redshift(self):
        """Validate redshift configuration constraints."""
        if self.z_type == "custom":
            if self.z_value is None:
                raise ValueError("z_value required when z_type = custom")
            if not np.isfinite(self.z_value):
                raise ValueError("z_value must be finite")
        else:
            self.z_value = None
        return self


# =========================================================
# NORMALIZATION CONFIG
# =========================================================

NormalizationType = Literal[
    "no_normalization",
    "custom",
    "median",
    "interval",
    "integral",
    "template"
]

ConservationType = Literal["flux", "luminosity"]
IntervalStatisticType = Literal["mean", "median", "maximum", "minimum"]


class NormalizationConfig(BaseModel):
    """Spectrum normalization method and parameters.

    Parameters
    ----------
    spectra_normalization : {"no_normalization", "custom", "median", "interval", "integral", "template"}
        Normalization method applied to individual spectra.
    conservation : {"flux", "luminosity"}, optional
        Conservation mode for ``no_normalization``.
    lambda_norm_min : float, optional
        Lower wavelength bound for interval normalization (rest-frame Å).
    lambda_norm_max : float, optional
        Upper wavelength bound for interval normalization (rest-frame Å).
    interval_norm_statistics : {"mean", "median", "maximum", "minimum"}, optional
        Statistic to extract from wavelength interval.
    """

    spectra_normalization: NormalizationType = "median"
    conservation: Optional[ConservationType] = None

    lambda_norm_min: Optional[float] = None
    lambda_norm_max: Optional[float] = None
    interval_norm_statistics: Optional[IntervalStatisticType] = None

    @field_validator("lambda_norm_min", "lambda_norm_max")
    @classmethod
    def validate_lambda(cls, v):
        """Validate wavelength values are non-negative and finite."""
        if v is None:
            return v
        if v < 0 or not np.isfinite(v):
            raise ValueError("Invalid normalization wavelength")
        return v

    @model_validator(mode="after")
    def validate_norm(self):
        """Validate normalization configuration constraints."""

        if self.spectra_normalization == "no_normalization":
            if self.conservation is None:
                raise ValueError("Conservation required when no_normalization")
            self.lambda_norm_min = None
            self.lambda_norm_max = None
            self.interval_norm_statistics = None

        elif self.spectra_normalization == "interval":
            if None in (self.lambda_norm_min, self.lambda_norm_max):
                raise ValueError("Interval normalization requires wavelength range")
            if self.lambda_norm_min >= self.lambda_norm_max:
                raise ValueError("Invalid wavelength interval")
            if self.interval_norm_statistics is None:
                raise ValueError("Interval normalization requires statistic")
            self.conservation = None

        else:
            if self.conservation is not None:
                raise ValueError("Conservation only allowed for no_normalization")
            self.lambda_norm_min = None
            self.lambda_norm_max = None
            self.interval_norm_statistics = None

        return self


# =========================================================
# RESAMPLING CONFIG
# =========================================================

ResamplingType = Literal["lambda", "log_lambda", "lambda_shifted", "none"]
PixelModeType = Literal["manual", "instrumental"]


class ResamplingConfig(BaseModel):
    """Wavelength grid resampling configuration.

    Parameters
    ----------
    pixel_resampling_type : {"lambda", "log_lambda", "lambda_shifted", "none"}
        Type of wavelength grid spacing.
    pixel_size_type : {"manual", "instrumental"}
        Whether pixel size is manually set or derived from instrument resolution.
    pixel_resampling : float, optional
        Manual pixel size (Å) when ``pixel_size_type = "manual"``.
    nyquist_sampling : float, optional
        Nyquist sampling factor when ``pixel_size_type = "instrumental"``.
    """

    pixel_resampling_type: ResamplingType = "lambda"
    pixel_size_type: PixelModeType = "instrumental"
    pixel_resampling: Optional[float] = None
    nyquist_sampling: Optional[float] = 5

    @model_validator(mode="after")
    def validate_pixel(self):
        """Validate pixel resampling configuration constraints."""

        if self.pixel_size_type == "manual":
            if self.pixel_resampling is None:
                raise ValueError("pixel_resampling required if pixel_size_type = manual")
            if self.pixel_resampling <= 0:
                raise ValueError("pixel_resampling must be > 0")
            self.nyquist_sampling = None

        elif self.pixel_size_type == "instrumental":
            if self.nyquist_sampling is None:
                raise ValueError("nyquist_sampling required if pixel_size_type = instrumental")
            if self.nyquist_sampling <= 0:
                raise ValueError("nyquist_sampling must be > 0")
            self.pixel_resampling = None

        return self


# =========================================================
# CATALOG CONFIG
# =========================================================

class MetadataColumnsConfig(BaseModel):
    """Catalog column names for metadata path access mode.

    When ``spectra_mode = "metadata path"``, per-spectrum file paths and indices
    are read from catalog columns.

    Parameters
    ----------
    metadata_path_column_name : str
        Column name containing spectrum file paths (e.g., ``"path"``).
    metadata_file_column_name : str
        Column name containing spectrum filenames within those paths
        (e.g., ``"filename"``).
    metadata_indx_column_name : str
        Column name containing spectrum index or HDU number within the file
        (e.g., ``"index"``).
    """
    metadata_path_column_name: str
    metadata_file_column_name: str
    metadata_indx_column_name: str


class GalacticExtinctionConfig(BaseModel):
    """Galactic extinction correction configuration.

    When enabled, spectrum flux is corrected for Galactic dust extinction
    using the Gordon+23 reddening law via ``dust_extinction``.

    Parameters
    ----------
    galactic_extinction : bool
        Enable Galactic extinction correction (default: False).
    gal_ext_column_name : str, optional
        Catalog column containing E(B-V) values (required if
        ``galactic_extinction = True``).
    """
    galactic_extinction: bool = False
    gal_ext_column_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_ext(self):
        if self.galactic_extinction and not self.gal_ext_column_name:
            raise ValueError("gal_ext_column_name required if galactic extinction is True")
        if not self.galactic_extinction:
            self.gal_ext_column_name = None
        return self


class CustomNormalizationColumnsConfig(BaseModel):
    """Catalog column name for custom normalization mode.

    When ``spectra_normalization = "custom"``, the normalization scalar for
    each spectrum is read from a catalog column.

    Parameters
    ----------
    custom_column_name : str, optional
        Catalog column containing per-spectrum normalization values
        (e.g., a photometric flux). Required if custom normalization is used.
    """
    custom_column_name: Optional[str] = None


class CatalogColumnsConfig(BaseModel):
    """Catalog column name configuration.

    Maps logical column roles to actual catalog column names. The catalog is
    loaded via ``io.filename_in`` and must contain at least the ID column.

    Parameters
    ----------
    ID_column_name : str
        Column name containing unique spectrum identifiers.
    redshift_column_name : str, optional
        Column name containing redshift values (required unless
        ``redshift.z_type = "observed_frame"``).
    metadata : MetadataColumnsConfig, optional
        Column names for metadata path mode (required if
        ``spectra_mode = "metadata path"``).
    galactic_extinction_parameters : GalacticExtinctionConfig
        Galactic extinction column and enable flag.
    custom_normalization : CustomNormalizationColumnsConfig, optional
        Custom normalization column (required if
        ``spectra_normalization = "custom"``).
    """
    ID_column_name: str
    redshift_column_name: Optional[str] = None
    metadata: Optional[MetadataColumnsConfig] = None
    galactic_extinction_parameters: GalacticExtinctionConfig = GalacticExtinctionConfig()
    custom_normalization: Optional[CustomNormalizationColumnsConfig] = None


# =========================================================
# OTHER SUBCONFIGS
# =========================================================

class BootstrapConfig(BaseModel):
    """Bootstrap resampling configuration.

    Parameters
    ----------
    bootstrapping_R : int
        Number of bootstrap resamples (0–1000).
    """
    bootstrapping_R: int = Field(default=300, ge=0, le=1000)


class SigmaClipConfig(BaseModel):
    """Sigma-clipping outlier rejection configuration.

    Parameters
    ----------
    sigma_clipping_conditions : float
        Clipping threshold in units of standard deviation (0–10).
    """
    sigma_clipping_conditions: float = Field(default=3, ge=0, le=10)


class ParallelConfig(BaseModel):
    """Multiprocessing configuration.

    Parameters
    ----------
    multiprocessing : bool
        Enable multiprocessing for spectrum processing.
    max_cpu_fraction : float
        Fraction of available CPUs to use (0–1).
    """
    multiprocessing: bool = True
    max_cpu_fraction: float = Field(default=0.9, gt=0, le=1)


class CosmologyConfig(BaseModel):
    """Cosmology parameters.

    Parameters
    ----------
    cosmo_H0 : float
        Hubble constant (km/s/Mpc).
    cosmo_Om0 : float
        Matter density parameter (0 < Om0 < 1).
    """
    cosmo_H0: float = Field(default=70, gt=0)
    cosmo_Om0: float = Field(default=0.3, gt=0, lt=1)


class InstrumentQualityConfig(BaseModel):
    """Instrument-specific quality filtering parameters.

    Parameters
    ----------
    pixel_mask : list[int], optional
        Pixel bitmask bits to flag as bad.
    n_min_dithers : int, optional
        Minimum number of dithers required for valid data.
    """
    pixel_mask: Optional[List[int]] = None
    n_min_dithers: Optional[int] = None


class InstrumentConfig(BaseModel):
    """Instrument and survey configuration.

    Parameters
    ----------
    instrument_name : str
        Instrument name (e.g. ``"euclid"``, ``"desi"``).
    survey_name : str
        Survey/program name.
    grisms : list[str]
        List of grism names (e.g. ``["red"]``, ``["red", "blue"]``).
    data_release : str
        Data release identifier.
    quality : InstrumentQualityConfig, optional
        Quality filtering parameters.
    """
    instrument_name: str
    survey_name: str
    grisms: List[str]           # replaces grism_type; e.g. ["red"] or ["red", "blue"]
    data_release: str
    quality: Optional[InstrumentQualityConfig] = None


class PlotConfig(BaseModel):
    """Output plotting configuration.

    Parameters
    ----------
    plot_results : bool
        Generate and display Plotly interactive plot of stacked spectrum.
    """
    plot_results: bool = True


# =========================================================
# MAIN CONFIG (USER LEVEL)
# =========================================================

class StackingConfig(BaseModel):
    """Complete validated configuration for spectrum stacking.

    This is the primary configuration model used throughout the stacking pipeline.
    It combines instrument settings, I/O configuration, spectral processing
    parameters, and output options.

    Parameters
    ----------
    instrument : InstrumentConfig
        Instrument and survey selection.
    instrument_constants : dict[str, Any], optional
        Instrument-specific constants (populated by resolver).
    io : IOConfig
        Input catalog and output spectrum paths.
    cosmology : CosmologyConfig
        Cosmology parameters.
    redshift : RedshiftConfig
        Stacking redshift reference frame.
    norm : NormalizationConfig
        Spectrum normalization method.
    catalog_columns : CatalogColumnsConfig
        Column names in the input catalog.
    resampling : ResamplingConfig
        Wavelength grid resampling configuration.
    lambda_edges_rest : tuple[float, float], optional
        Rest-frame wavelength range override (Å).
    spectrum_edges : tuple[int, int], optional
        Pixel range to include in spectrum.
    bootstrap : BootstrapConfig
        Bootstrap resampling configuration.
    sigmaclip : SigmaClipConfig
        Sigma-clipping configuration.
    parallel : ParallelConfig
        Multiprocessing configuration.
    plot : PlotConfig
        Output plot configuration.
    log_level : {"DEBUG", "INFO", "WARNING"}
        Logging verbosity level.
    config_version : str
        Configuration schema version.
    """

    instrument: InstrumentConfig
    instrument_constants: Optional[Dict[str, Any]] = None

    io: IOConfig = IOConfig()

    cosmology: CosmologyConfig = CosmologyConfig()
    redshift: RedshiftConfig = RedshiftConfig()
    norm: NormalizationConfig = NormalizationConfig()

    catalog_columns: CatalogColumnsConfig
    resampling: ResamplingConfig = ResamplingConfig()

    lambda_edges_rest: Optional[Tuple[float, float]] = None
    spectrum_edges: Optional[Tuple[int, int]] = None

    bootstrap: BootstrapConfig = BootstrapConfig()
    sigmaclip: SigmaClipConfig = SigmaClipConfig()
    parallel: ParallelConfig = ParallelConfig()

    plot: PlotConfig = PlotConfig()

    log_level: Literal["DEBUG", "INFO", "WARNING"] = "INFO"

    config_version: str = "1.0.0"

    class Config:
        frozen = True


# =========================================================
# RESOLVER LAYER
# =========================================================

def compute_catalog_requirements(cfg: StackingConfig):

    required = ["ID_column_name"]

    if cfg.redshift.requires_catalog_column():
        required.append("redshift_column_name")

    if cfg.io.spectra_mode == "metadata path":
        required.append("metadata")

    if cfg.norm.spectra_normalization == "custom":
        required.append("custom_normalization")

    if cfg.catalog_columns.galactic_extinction_parameters.galactic_extinction:
        required.append("galactic_extinction_parameters.gal_ext_column_name")

    return required


class StackingConfigResolver:
    """Resolver for cross-field validation and instrument-specific rules.

    Applies constraints that depend on multiple fields and loads instrument rules
    from the `instruments/instruments_rules.json` file.
    """

    @staticmethod
    def resolve(cfg: StackingConfig) -> StackingConfig:
        """Apply cross-field validation and instrument rules.

        Parameters
        ----------
        cfg : StackingConfig
            Partially validated config from Pydantic.

        Returns
        -------
        StackingConfig
            Fully resolved and validated configuration.

        Raises
        ------
        ValueError
            If cross-field constraints or instrument rules are violated.
        """

        # ---------------- INSTRUMENT ----------------
        inst_name = cfg.instrument.instrument_name
        rules = INSTRUMENT_RULES.get(inst_name, {})

        # Validate selected grisms against survey rules
        survey_rules = rules.get("surveys", {}).get(cfg.instrument.survey_name, {})
        allowed_grisms = survey_rules.get("grisms", [])
        for g in cfg.instrument.grisms:
            if allowed_grisms and g not in allowed_grisms:
                raise ValueError(
                    f"Grism '{g}' is not available for survey "
                    f"'{cfg.instrument.survey_name}'. Allowed: {allowed_grisms}."
                )

        if not cfg.instrument.grisms:
            raise ValueError("At least one grism must be selected.")

        # Constants
        constants = rules.get("constants", {})

        # Quality defaults
        quality_rules = rules.get("quality", {})
        quality_defaults = {k: v.get("default") for k, v in quality_rules.items()}
        user_quality = cfg.instrument.quality.model_dump() if cfg.instrument.quality else {}
        merged_quality = ({**quality_defaults, **user_quality}
                          if quality_defaults or user_quality else None)

        cfg = cfg.model_copy(
            update={
                "instrument_constants": constants,
                "instrument": cfg.instrument.model_copy(
                    update={"quality": merged_quality}
                ),
            },
            deep=True,
        )

        # ---- IO rules: validate per-grism paths ----
        mode = cfg.io.spectra_mode

        if mode == "individual fits":
            for g in cfg.instrument.grisms:
                gcfg = cfg.io.grism_io.get(g)
                if gcfg is None or gcfg.spectra_dir is None:
                    raise ValueError(
                        f"spectra_dir is required for grism '{g}' "
                        f"in 'individual fits' mode."
                    )

        elif mode == "combined fits":
            for g in cfg.instrument.grisms:
                gcfg = cfg.io.grism_io.get(g)
                if gcfg is None or gcfg.spectra_dir is None or gcfg.spectra_datafile is None:
                    raise ValueError(
                        f"Both spectra_dir and spectra_datafile are required "
                        f"for grism '{g}' in 'combined fits' mode."
                    )

        # ---- Resampling vs Redshift ----
        if (
            cfg.resampling.pixel_resampling_type == "none"
            and cfg.redshift.z_type != "observed_frame"
        ):
            raise ValueError("Resampling 'none' is only allowed in observed_frame mode.")

        # ---- Catalog requirements ----
        reqs = compute_catalog_requirements(cfg)

        if "redshift_column_name" in reqs and cfg.catalog_columns.redshift_column_name is None:
            raise ValueError("Missing redshift_column_name in catalog_columns.")

        if "metadata" in reqs and cfg.catalog_columns.metadata is None:
            raise ValueError("metadata columns required for metadata path mode.")

        if (
            "custom_normalization" in reqs
            and (
                cfg.catalog_columns.custom_normalization is None
                or cfg.catalog_columns.custom_normalization.custom_column_name is None
            )
        ):
            raise ValueError("custom_normalization column is required.")

        return cfg
