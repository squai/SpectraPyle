"""
Auto-generation of output FITS filenames from configuration.

Provides :func:`build_filename` which constructs descriptive, self-documenting
filenames encoding instrument, grisms, redshift type, normalization, and sample size.
"""


def build_filename(cfg):
    """Auto-generate the output FITS filename stem from config fields.

    Constructs a descriptive name encoding instrument, grisms, redshift type,
    normalization, and sample size so output files are self-documenting.

    Parameters
    ----------
    config : dict
        Flat stacking config dict.

    Returns
    -------
    str
        Filename stem (without ``.fits`` extension).
    """

    parts = []

    # ---------- BASE ----------
    parts.append(cfg["filename_in"])

    parts.append(f"idCol_{cfg['ID_column_name']}")

    if cfg["redshift_column_name"]:
        parts.append(f"zCol_{cfg['redshift_column_name']}")

    parts.append(f"zType_{cfg['z_type']}")

    parts.append(f"galExtCol_{cfg['gal_ext_column_name']}")

    parts.append(f"conservation_{cfg['conservation']}")

    parts.append(f"spectraNormalization_{cfg['spectra_normalization']}")

    # ---------- NORMALIZATION EXTRAS ----------
    if cfg["spectra_normalization"] == "interval" and cfg["lambda_norm_rest"]:
        l0, l1 = cfg["lambda_norm_rest"]
        parts.append(f"lbdRest_{l0}_{l1}")

    if cfg["spectra_normalization"] == "custom" and cfg["custom_column_name"]:
        parts.append(f"normParam_{cfg['custom_column_name']}")

    # ---------- RESAMPLING ----------
    if cfg["pixel_resampling"]:
        parts.append(f"pxlResamp_{cfg['pixel_resampling']}")

    # ---------- QUALITY ----------
    sigma = cfg["sigma_clipping_conditions"]
    parts.append(f"sigmaClip_{sigma}")
        
    
    parts.append(f"bootstrapping_{cfg['bootstrapping_R']}")

    # ---------- INSTRUMENT QC ----------
    
    masked_bits = cfg.get("pixel_mask", [])
    masked_str = ""

    if masked_bits:
        "bitMask" + "_".join(map(str, masked_bits))
        parts.append(masked_str)

    if cfg.get("n_min_dithers") not in [None, False]:
        parts.append(f"NdithMask{cfg['n_min_dithers']}")

    parts.append("STACKING")

    return "__".join(parts)
