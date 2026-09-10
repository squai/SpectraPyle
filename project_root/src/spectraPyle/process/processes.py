"""
Multiprocessing driver for per-spectrum processing.

:func:`main_parallel` splits spectrum IDs across CPUs and runs the
read → redshift-shift → normalize → resample pipeline for each spectrum.
Recoverable problems affecting a single spectrum are recorded and skipped;
structural/configuration errors propagate and stop the run.
"""

from pathlib import Path
import logging
import logging.handlers
import multiprocessing
from multiprocessing import Pool

import numpy as np

import spectraPyle.spectrum.spectra as sspec
import spectraPyle.spectrum.normalization as snorm
import spectraPyle.spectrum.resampling as sres

from tqdm import tqdm

from spectraPyle.utils.exceptions import SpectrumRejected, NormalizationError
from spectraPyle.utils.log import get_logger
from spectraPyle.instruments._combined_fits_cache import init_file_handles, close_file_handles

logger = get_logger(__name__)


def _worker_logging_init(queue):
    """Configure logging in a worker process via QueueHandler."""
    root = logging.getLogger("spectraPyle")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(logging.handlers.QueueHandler(queue))


def _worker_init(log_queue, grism_paths):
    """Initialize worker logging and optional combined-FITS cache handles."""
    _worker_logging_init(log_queue)
    if grism_paths:
        init_file_handles(grism_paths)


def _looks_like_missing_spectrum(exc: Exception) -> bool:
    """Return True when an I/O exception clearly means one spectrum is absent."""
    msg = str(exc).lower()
    return (
        "spectrum" in msg
        and "not found" in msg
        and "column" not in msg
        and "layout" not in msg
    )


def _empty_result(n_output: int, fill_value: float):
    """Build flux/error placeholders for an unusable spectrum."""
    return (
        np.full(n_output, fill_value, dtype=float),
        np.full(n_output, fill_value, dtype=float),
    )


def main_parallel(
    self,
    specIDs,
    redshift,
    ebv_galactic,
    custom_norm_param,
    wavelength_stacking_bins,
    pixelResampling,
    z_stacking,
    grismList,
    data_input=None,
    output_npix=None,
    progress_callback=None,
    progress_offset=0,
    progress_total=None,
    chunk_index=None,
    num_chunks=None,
):
    """Parallel processing driver for spectrum stacking.

    Parameters are the same as in the historical API, with optional progress
    metadata used by the GUI.  When ``progress_callback`` is None, terminal
    users retain the normal tqdm progress bar.

    Returns
    -------
    tuple
        specResampledArr, errResampledArr, normalization_factors,
        spectra_not_found, specid, grism_labels, processing_status,
        rejection_reason
    """

    config = self.config
    cosmology = self.cosmology
    use_metadata = config.get("spectra_mode") == "metadata path"

    allowed_norm = {"no_normalization", "template", "integral", "median", "interval", "custom"}
    if config.get("spectra_normalization") not in allowed_norm:
        raise ValueError(
            f"Normalization type '{config.get('spectra_normalization')}' is not supported."
        )

    if output_npix is None:
        if isinstance(wavelength_stacking_bins, str):
            raise ValueError("output_npix is required when pixel resampling is disabled")
        output_npix = len(wavelength_stacking_bins) - 1

    # -------- Metadata preparation --------
    if use_metadata:
        if data_input is None:
            raise ValueError("data_input must be provided when spectra_mode='metadata path'")

        metadata_name = (
            data_input[config["metadata_path_column_name"]]
            + "/"
            + data_input[config["metadata_file_column_name"]]
        )
        metadata_indx = data_input[config["metadata_indx_column_name"]]
    else:
        metadata_name = [None] * len(specIDs)
        metadata_indx = [None] * len(specIDs)

    # -------- Argument packing --------
    args = [
        (
            specid,
            z,
            ebv_g,
            norm_param,
            mname,
            mindx,
            config,
            cosmology,
            wavelength_stacking_bins,
            pixelResampling,
            z_stacking,
            grismList,
            output_npix,
        )
        for specid, z, ebv_g, norm_param, mname, mindx in zip(
            specIDs,
            redshift,
            ebv_galactic,
            custom_norm_param,
            metadata_name,
            metadata_indx,
        )
    ]

    # -------- Build grism_paths for combined FITS cache --------
    spectra_mode = config.get("spectra_mode")
    grism_paths = {}
    if spectra_mode == "combined fits":
        for grism in grismList:
            gcfg = config.get("grism_io", {}).get(grism, {})
            datafile = gcfg.get("spectra_datafile")
            if datafile:
                grism_paths[grism] = Path(gcfg["spectra_dir"]) / f"{datafile}.fits"

    parent_handlers = logging.getLogger("spectraPyle").handlers[:]
    total_objects = len(args)
    n_grisms = max(1, len(grismList))

    def consume(iterator):
        results = []
        if progress_callback is None:
            iterator = tqdm(iterator, total=total_objects, desc="Processing spectra")

        for obj_index, result in enumerate(iterator, start=1):
            results.append(result)
            if progress_callback is not None:
                flat = result
                n_ok = sum(item[6] == "OK" for item in flat)
                n_rejected = sum(item[6] not in {"OK", "FILE_UNAVAILABLE"} for item in flat)
                n_missing = sum(item[6] == "FILE_UNAVAILABLE" for item in flat)
                progress_callback(
                    stage="spectra",
                    current=min(progress_offset + obj_index * n_grisms, progress_total or 10**18),
                    total=progress_total or total_objects * n_grisms,
                    chunk=chunk_index,
                    chunks=num_chunks,
                    delta_ok=n_ok,
                    delta_rejected=n_rejected,
                    delta_missing=n_missing,
                )
        return results

    # -------- Multiprocessing --------
    if config.get("multiprocessing", True):
        log_queue = multiprocessing.Queue()
        listener = logging.handlers.QueueListener(
            log_queue, *parent_handlers, respect_handler_level=True
        )
        listener.start()
        try:
            with Pool(
                processes=self.num_cpus,
                initializer=_worker_init,
                initargs=(log_queue, grism_paths),
            ) as pool:
                results = consume(pool.imap(process_spectrum_parallel, args))
        finally:
            listener.stop()
    else:
        if grism_paths:
            init_file_handles(grism_paths)
        try:
            results = consume(map(process_spectrum_parallel, args))
        finally:
            if grism_paths:
                close_file_handles()

    flat_results = [item for sublist in results for item in sublist]
    if not flat_results:
        raise RuntimeError("No spectrum-processing results were produced")

    (
        specid_result,
        grism_labels,
        specResampledArr,
        errResampledArr,
        normalization_factors,
        spectra_not_found,
        processing_status,
        rejection_reason,
    ) = zip(*flat_results)

    return (
        np.array(specResampledArr).T,
        np.array(errResampledArr).T,
        np.array(normalization_factors),
        np.array(spectra_not_found, dtype=str),
        np.array(specid_result),
        np.array(grism_labels),
        np.array(processing_status, dtype=str),
        np.array(rejection_reason, dtype=str),
    )


def process_spectrum_parallel(args):
    """Process one catalogue object for all requested grisms.

    Spectrum-local failures are converted into placeholders so the run can
    continue and pixel statistics can track them.  Structural input/config
    failures are deliberately re-raised.
    """
    (
        specid,
        z,
        ebv_g,
        norm_param,
        metadata_name,
        hdu_indx,
        config,
        cosmology,
        wavelength_stacking_bins,
        pixelResampling,
        z_stacking,
        grismList,
        output_npix,
    ) = args

    results = []

    for grism in grismList:
        normalization_factor = np.nan
        spectra_not_found = np.nan
        status = "OK"
        reason = ""
        wavelength = None

        try:
            # -------- Spectrum loading --------
            try:
                wavelength, spec, err = sspec.useSpec(
                    config,
                    specid,
                    z,
                    z_stacking,
                    ebv_g,
                    cosmology,
                    grism,
                    metadata_name,
                    hdu_indx,
                )
            except FileNotFoundError as exc:
                status = "FILE_UNAVAILABLE"
                reason = str(exc)
                spectra_not_found = specid
                logger.warning(
                    f"Spectrum {specid} (grism={grism}) unavailable: {exc}"
                )
                specResampled, errResampled = _empty_result(output_npix, np.inf)
                results.append(
                    (specid, grism, specResampled, errResampled, normalization_factor,
                     spectra_not_found, status, reason)
                )
                continue
            except OSError as exc:
                # I/O failure of one physical spectrum/file is recoverable.
                status = "FILE_UNAVAILABLE"
                reason = str(exc)
                spectra_not_found = specid
                logger.warning(
                    f"Spectrum {specid} (grism={grism}) could not be read: {exc}"
                )
                specResampled, errResampled = _empty_result(output_npix, np.inf)
                results.append(
                    (specid, grism, specResampled, errResampled, normalization_factor,
                     spectra_not_found, status, reason)
                )
                continue
            except (ValueError, NameError) as exc:
                if _looks_like_missing_spectrum(exc):
                    status = "FILE_UNAVAILABLE"
                    reason = str(exc)
                    spectra_not_found = specid
                    logger.warning(
                        f"Spectrum {specid} (grism={grism}) unavailable: {exc}"
                    )
                    specResampled, errResampled = _empty_result(output_npix, np.inf)
                    results.append(
                        (specid, grism, specResampled, errResampled, normalization_factor,
                         spectra_not_found, status, reason)
                    )
                    continue
                # Missing columns, unknown FITS layout, bad HDU/config etc. are
                # structural and must not be silently swallowed.
                raise

            wavelength = np.asarray(wavelength)
            spec = np.asarray(spec, dtype=float)
            err = np.asarray(err, dtype=float)

            if wavelength.ndim != 1 or spec.ndim != 1 or err.ndim != 1:
                raise SpectrumRejected(
                    f"expected 1-D wavelength/flux/error arrays; got "
                    f"{wavelength.shape}, {spec.shape}, {err.shape}",
                    reason="INVALID_SPECTRUM_SHAPE",
                )
            if not (len(wavelength) == len(spec) == len(err)):
                raise SpectrumRejected(
                    f"wavelength/flux/error lengths differ: "
                    f"{len(wavelength)}/{len(spec)}/{len(err)}",
                    reason="INVALID_SPECTRUM_SHAPE",
                )
            if len(spec) < 2:
                raise SpectrumRejected(
                    "fewer than two spectral pixels available",
                    reason="NO_VALID_PIXELS",
                )

            finite = np.isfinite(spec) & np.isfinite(err)
            if not np.any(finite):
                raise SpectrumRejected(
                    "no finite flux/error pixels",
                    reason="ALL_NAN",
                )

            # -------- Normalization --------
            try:
                norm_type = config["spectra_normalization"]
                if norm_type in ["no_normalization", "template"]:
                    normalization_factor = 1.0
                elif norm_type == "integral":
                    spec, err, normalization_factor = snorm.normSpecIntegrMean(
                        wavelength, spec, err
                    )
                elif norm_type == "median":
                    spec, err, normalization_factor = snorm.normSpecMed(
                        wavelength, spec, err
                    )
                elif norm_type == "interval":
                    z_st = 0 if config["z_type"] == "observed_frame" else z_stacking
                    spec, err, normalization_factor = snorm.normSpecInterv(
                        specid,
                        wavelength,
                        spec,
                        err,
                        config["lambda_norm_rest"][0] * (1 + z_st),
                        config["lambda_norm_rest"][1] * (1 + z_st),
                        config["interval_norm_statistics"],
                    )
                elif norm_type == "custom":
                    spec, err, normalization_factor = snorm.normSpecCustom(
                        wavelength, spec, err, norm_param
                    )
            except NormalizationError:
                raise
            except (FloatingPointError, ArithmeticError) as exc:
                raise SpectrumRejected(
                    f"numerical normalization failure: {exc}",
                    reason="INVALID_NORMALIZATION",
                ) from exc

            # -------- Resampling --------
            if config["pixel_resampling_type"] != "none":
                try:
                    specResampled, errResampled = sres.resamplingSpecFluxCons(
                        wavelength,
                        spec,
                        err**2,
                        lambdaInterp=wavelength_stacking_bins,
                    )
                except (ValueError, FloatingPointError, ArithmeticError) as exc:
                    raise SpectrumRejected(
                        f"resampling failed: {exc}",
                        reason="RESAMPLING_FAILED",
                    ) from exc
            else:
                specResampled = spec
                errResampled = err

            if len(specResampled) != output_npix:
                raise SpectrumRejected(
                    f"processed spectrum has {len(specResampled)} pixels; expected {output_npix}",
                    reason="INVALID_OUTPUT_SHAPE",
                )

            if not np.any(np.isfinite(specResampled) & np.isfinite(errResampled)):
                raise SpectrumRejected(
                    "no usable pixels remain after processing",
                    reason="NO_VALID_PIXELS",
                )

        except SpectrumRejected as exc:
            status = exc.reason
            reason = str(exc)
            logger.warning(
                f"Spectrum {specid} (grism={grism}) rejected [{status}]: {reason}"
            )
            # NaN means the spectrum existed/was read but is unusable.  This is
            # intentionally different from inf, which denotes absent/void input.
            specResampled, errResampled = _empty_result(output_npix, np.nan)
            normalization_factor = np.nan

        # Any other exception is structural/unexpected and propagates.  Examples:
        # missing FITS columns, unknown HDU layout, invalid configuration, code bug.

        results.append(
            (
                specid,
                grism,
                specResampled,
                errResampled,
                normalization_factor,
                spectra_not_found,
                status,
                reason,
            )
        )

    return results
