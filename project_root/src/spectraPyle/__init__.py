"""
SpectraPyle — spectral stacking for Euclid and DESI.

Subpackages
-----------
stacking
    Full pipeline orchestrator (:class:`~spectraPyle.stacking.stacking.Stacking`).
schema
    Pydantic validation models.
runtime
    Config normalization and adapter layer.
instruments
    Per-instrument drivers (Euclid, DESI).
io
    Catalog I/O and FITS output.
spectrum
    Per-spectrum processing (shift, resample, normalize).
statistic
    Stacking estimators and bootstrap.
plot
    Plotly visualization.
physics
    Galactic extinction correction.
utils
    Logging utilities.
"""

__version__ = "5.0.2"
__author__ = "Salvatore Quai"
