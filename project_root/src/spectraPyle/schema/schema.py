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

IO_MODE_RULES = {
    "individual fits": {
        "required": ["spectra_dir"],
        "forbidden": ["spectra_datafile"],
    },
    "combined fits": {
        "required": ["spectra_dir", "spectra_datafile"],
    },
    "metadata path": {
        "auto_set": {"spectra_datafile": "metadata", "spectra_dir": None},
    },
}

class Config:
    frozen = True
    extra = "forbid"

class IOConfig(BaseModel):

    spectra_mode: SpectraMode = "individual fits"

    input_dir: Optional[Path] = None
    filename_in: Optional[str] = None
    filename_in_extention: Optional[Literal["fits", "csv", "npz"]] = None

    output_dir: Optional[Path] = None

    spectra_dir: Optional[Path] = None
    spectra_datafile: Optional[str] = None

    filename_out: str = "AUTO"

    @model_validator(mode="after")
    def normalize_metadata_mode(self):
        rules = IO_MODE_RULES.get(self.spectra_mode, {})
        for k, v in rules.get("auto_set", {}).items():
            setattr(self, k, v)
        return self


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

    z_type: RedshiftType = "rest_frame"
    z_value: Optional[float] = None

    def requires_catalog_column(self) -> bool:
        return self.z_type != "observed_frame"

    @model_validator(mode="after")
    def validate_redshift(self):
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

    spectra_normalization: NormalizationType = "median"
    conservation: Optional[ConservationType] = None

    lambda_norm_min: Optional[float] = None
    lambda_norm_max: Optional[float] = None
    interval_norm_statistics: Optional[IntervalStatisticType] = None

    @field_validator("lambda_norm_min", "lambda_norm_max")
    @classmethod
    def validate_lambda(cls, v):
        if v is None:
            return v
        if v < 0 or not np.isfinite(v):
            raise ValueError("Invalid normalization wavelength")
        return v

    @model_validator(mode="after")
    def validate_norm(self):

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

    pixel_resampling_type: ResamplingType = "lambda"

    pixel_size_type: PixelModeType = "instrumental"

    pixel_resampling: Optional[float] = None
    nyquist_sampling: Optional[float] = 5

    @model_validator(mode="after")
    def validate_pixel(self):

        if self.pixel_size_type == "manual":

            if self.pixel_resampling is None:
                raise ValueError(
                    "pixel_resampling required if pixel_size_type = manual"
                )

            if self.pixel_resampling <= 0:
                raise ValueError(
                    "pixel_resampling must be > 0"
                )

            self.nyquist_sampling = None

        elif self.pixel_size_type == "instrumental":

            if self.nyquist_sampling is None:
                raise ValueError(
                    "nyquist_sampling required if pixel_size_type = instrumental"
                )

            if self.nyquist_sampling <= 0:
                raise ValueError(
                    "nyquist_sampling must be > 0"
                )

            self.pixel_resampling = None

        return self



# =========================================================
# CATALOG CONFIG
# =========================================================

class MetadataColumnsConfig(BaseModel):
    metadata_path_column_name: str
    metadata_file_column_name: str
    metadata_indx_column_name: str


class GalacticExtinctionConfig(BaseModel):
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
    custom_column_name: Optional[str] = None


class CatalogColumnsConfig(BaseModel):
    ID_column_name: str
    redshift_column_name: Optional[str] = None
    metadata: Optional[MetadataColumnsConfig] = None
    galactic_extinction_parameters: GalacticExtinctionConfig = GalacticExtinctionConfig()
    custom_normalization: Optional[CustomNormalizationColumnsConfig] = None


# =========================================================
# OTHER SUBCONFIGS
# =========================================================

class BootstrapConfig(BaseModel):
    bootstrapping_R: int = Field(default=300, ge=0, le=1000)


class SigmaClipConfig(BaseModel):
    sigma_clipping_conditions: float = Field(default=3, ge=0, le=10)


class ParallelConfig(BaseModel):
    multiprocessing: bool = True
    max_cpu_fraction: float = Field(default=0.9, gt=0, le=1)


class CosmologyConfig(BaseModel):
    cosmo_H0: float = Field(default=70, gt=0)
    cosmo_Om0: float = Field(default=0.3, gt=0, lt=1)


class InstrumentQualityConfig(BaseModel):
    pixel_mask: Optional[List[int]] = None
    n_min_dithers: Optional[int] = None


class InstrumentConfig(BaseModel):
    instrument_name: str
    survey_name: str
    grism_type: str
    data_release: str
    quality: Optional[InstrumentQualityConfig] = None


class PlotConfig(BaseModel):
    plot_results: bool = True


# =========================================================
# MAIN CONFIG (USER LEVEL)
# =========================================================

class StackingConfig(BaseModel):

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

    @staticmethod
    def resolve(cfg: StackingConfig) -> StackingConfig:

        # ---------------- INSTRUMENT ----------------
        inst_name = cfg.instrument.instrument_name
        rules = INSTRUMENT_RULES.get(inst_name, {})

        # === CONSTANTS ===
        constants = rules.get("constants", {})

        # === QUALITY ===
        quality_rules = rules.get("quality", {})

        quality_defaults = {
            key: spec.get("default")
            for key, spec in quality_rules.items()
        }
        
        user_quality = (
            cfg.instrument.quality.model_dump()
            if cfg.instrument.quality
            else {}
        )

        merged_quality = (
            {**quality_defaults, **user_quality}
            if quality_defaults or user_quality
            else None
        )

        # ---------------- APPLY UPDATE ----------------
        cfg = cfg.model_copy(
            update={
                "instrument_constants": constants,
                "instrument": cfg.instrument.model_copy(
                    update={"quality": merged_quality}
                )
            },
            deep=True
        )


        
        # ---- IO rules ----
        io_rules = IO_MODE_RULES.get(cfg.io.spectra_mode, {})

        for field in io_rules.get("required", []):
            if getattr(cfg.io, field) is None:
                raise ValueError(f"{field} required for mode {cfg.io.spectra_mode}")

        # ---- Resampling vs Redshift ----
        if (
            cfg.resampling.pixel_resampling_type == "none"
            and cfg.redshift.z_type != "observed_frame"
        ):
            raise ValueError("Resampling 'none' allowed only in observed_frame")

        # ---- Catalog requirements ----
        reqs = compute_catalog_requirements(cfg)

        if "redshift_column_name" in reqs and cfg.catalog_columns.redshift_column_name is None:
            raise ValueError("Missing redshift column")

        if "metadata" in reqs and cfg.catalog_columns.metadata is None:
            raise ValueError("Metadata columns required")

        if (
            "custom_normalization" in reqs
            and (
                cfg.catalog_columns.custom_normalization is None
                or cfg.catalog_columns.custom_normalization.custom_column_name is None
            )
        ):
            raise ValueError("Custom normalization column required")

        return cfg


