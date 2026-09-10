"""Custom exceptions used to distinguish recoverable spectrum failures.

These exceptions are intentionally narrow: they describe problems with a
single input spectrum that should be recorded and skipped without aborting the
whole stacking run. Structural/configuration errors should use the original
exception type and propagate to the caller.
"""


class SpectrumRejected(ValueError):
    """A single spectrum is unusable but the stacking run can continue."""

    def __init__(self, message: str, reason: str = "SPECTRUM_REJECTED"):
        super().__init__(message)
        self.reason = reason


class NormalizationError(SpectrumRejected):
    """A single spectrum cannot be safely normalized."""

    def __init__(self, message: str):
        super().__init__(message, reason="INVALID_NORMALIZATION")
