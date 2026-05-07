Instruments & Input Data Formats
=================================

This guide explains how to prepare your data for SpectraPyle. It covers the expected
file formats, FITS column layouts, and configuration for each supported instrument driver.

For API documentation, see :doc:`/api/instruments`.

Overview
--------

+----------------+-------------------+-------------+--------------------------------------------------------------+
| Instrument     | Grism(s)          | Status      | Best for                                                     |
+================+===================+=============+==============================================================+
| Euclid NISP    | ``red``, ``blue`` | Active      | Euclid NISP spectroscopy, multi-grism stacking               |
+----------------+-------------------+-------------+--------------------------------------------------------------+
| DESI           | ``merged``        | Back-compat | Euclid–DESI crossmatched catalogs only                       |
+----------------+-------------------+-------------+--------------------------------------------------------------+
| Generic        | ``default``       | Active      | Any standard FITS binary table or WCS-compliant image HDU    |
+----------------+-------------------+-------------+--------------------------------------------------------------+

Spectra Modes
--------------

SpectraPyle supports three ways to locate and load individual spectra. All three modes
work with Euclid (with metadata path limitations). DESI supports all three. Generic supports
the first two.

**individual fits**

  Each spectrum lives in its own FITS file. SpectraPyle builds the path as:
  ``{spectra_dir}/{specid}.fits`` (generic) or with per-release naming variants (Euclid).
  The spectrum is extracted from the file and returned to the stacking pipeline.

  *Config:*

  .. code-block:: yaml

    io:
      spectra_mode: individual fits
      grism_io:
        red:
          spectra_dir: /path/to/spectra/red

**combined fits**

  Multiple spectra are stored in a single FITS file, identified by HDU name or table row.
  SpectraPyle opens the file and extracts the spectrum matching ``specid``.

  *Config:*

  .. code-block:: yaml

    io:
      spectra_mode: combined fits
      grism_io:
        red:
          spectra_dir: /path/to/combined/
          spectra_datafile: my_combined_spectra.fits

**metadata path**

  The input catalog contains explicit columns pointing to the FITS directory, filename, and HDU index for each spectrum.
  This is useful when spectra are scattered across many files or follow a non-standard naming scheme.

  Requires three catalog columns:

  - ``metadata_path_column_name`` (config key ``catalog_columns.metadata.metadata_path_column_name``) — column name containing FITS directory path
  - ``metadata_file_column_name`` (config key ``catalog_columns.metadata.metadata_file_column_name``) — column name containing FITS filename
  - ``metadata_indx_column_name`` (config key ``catalog_columns.metadata.metadata_indx_column_name``) — column name containing HDU index (integer)

  SpectraPyle combines the first two to form the full path: ``{path}/{filename}``, then reads HDU ``{index}``.

  *Config:*

  .. code-block:: yaml

    io:
      spectra_mode: metadata path

    catalog_columns:
      metadata:
        metadata_path_column_name: fits_path_col
        metadata_file_column_name: fits_file_col
        metadata_indx_column_name: hdu_index_col

  *Example catalog columns:*

  +---------+------------------+------------------+-----------+
  | specid  | fits_path_col    | fits_file_col    | hdu_index |
  +=========+==================+==================+===========+
  | 12345   | /data/batch1/    | 12345.fits       | 1         |
  +---------+------------------+------------------+-----------+
  | 12346   | /data/batch2/    | spec_12346.fits  | 2         |
  +---------+------------------+------------------+-----------+

  .. note::

    **ESA Datalabs users:** If you are working on Datalabs with Euclid data exported from the SAS catalogue query, map the three SIR catalogue columns (``datalabs_path``, ``file_name``, ``hdu_index``) to the configuration above. See :doc:`datalabs` for a complete walkthrough and example configuration.

Euclid NISP
-----------

Euclid provides a mature, well-tested driver with multi-grism support and per-data-release
filename pattern handling.

**Grisms**

  ``red`` (wavelength 11900–19002 Å, R~600) and ``blue`` (wavelength 9260–13660 Å, R~600)

**Supported spectra modes**

  All three: ``individual fits``, ``combined fits``, ``metadata path``

**FITS Binary Table Format**

Euclid spectra are stored in FITS binary table HDUs. SpectraPyle auto-detects column names
using aliases; the first match wins:

+-------------------+----------------------------------+
| Physical quantity | Column name aliases              |
+===================+==================================+
| Wavelength        | ``WAVELENGTH``, ``wave``         |
+-------------------+----------------------------------+
| Flux              | ``SIGNAL``, ``flux``             |
+-------------------+----------------------------------+
| Error/Variance    | ``VAR`` (sqrt'd to sigma),       |
|                   | ``error``                        |
+-------------------+----------------------------------+
| Quality mask      | ``MASK`` (optional, bitmask)     |
+-------------------+----------------------------------+
| Dither count      | ``NDITH`` (optional, dither flag)|
+-------------------+----------------------------------+

**Data Release Filename Patterns**

When using ``individual fits`` mode, SpectraPyle resolves filenames per data release:

- **Q1** — Simple naming: ``{spectra_dir}/{specid}.fits``
- **DR1** — Variant patterns (tries in order):

  - ``{spectra_dir}/{specid}.fits``
  - ``{spectra_dir}/{specid}_{grism}.fits``
  - ``{spectra_dir}/SPECTRA_{prefix}-sedm {specid}.fits`` (where prefix is ``RGS`` for red, ``BGS`` for blue)

**combined fits Layout**

When using ``combined fits``, SpectraPyle tries three HDU-matching strategies (in order):

1. HDU named ``{specid}`` — per-spectrum binary table
2. HDU named ``{specid}_{grism}`` — per-spectrum/grism binary table
3. HDU named ``{specid}_{prefix}`` — per-spectrum/grism binary table ((where prefix is ``RGS`` for red, ``BGS`` for blue)
4. A single ``SPECTRA`` table with an ``ID_column_name`` column to filter by ``specid``

**Quality Filters**

Euclid supports bitmask-based quality filtering. Configure in the ``io`` block:

.. code-block:: yaml

  io:
    pixel_mask: [0]              # Bit positions to NaN out (default: [0])
    n_min_dithers: 3             # Min dither count; below this → NaN (default: 3)
    spectrum_edges: [10, -10]    # Pixel indices to NaN (leading/trailing)

**Wavelength Reference**

Automatically retrieved from ``instruments_rules.json``:

- Red: 11900–19002 Å, R = 600, reference wavelength 16000 Å
- Blue: 9260–13660 Å, R = 600, reference wavelength 16000 Å
- Flux units: ``erg / s / cm² / Å``, scale factor 1e-16

DESI (Back-Compatibility)
--------------------------

.. warning::

  The DESI driver is maintained **only for back-compatibility with Euclid–DESI crossmatched samples**.
  It is not under active development. For new DESI-only workflows, we recommend using the Generic driver instead.

**Grism**

  ``merged`` only (no red/blue separation)

**Supported spectra modes**

  All three: ``individual fits``, ``combined fits``, ``metadata path``

**FITS Binary Table Format**

DESI spectra use lowercase, strictly-matched column names. **No aliases are supported:**

+-----------+----------+
| Quantity  | Column   |
+===========+==========+
| Wavelength| ``wavelength`` |
+-----------+----------+
| Flux      | ``flux`` |
+-----------+----------+
| Error     | ``noise`` (already sigma, not variance) |
+-----------+----------+

**Limitations**

- No bitmask or dither-count filtering (quality filters are not implemented)
- combined fits only matches HDU named ``{specid}`` (no ``SPECTRA`` table fallback)
- Older resource management (file handles not explicitly closed in some paths)

**Filename patterns**

Always ``{spectra_dir}/{specid}.fits`` (no data-release variants). 
Note: On ESA Datalabs, the DESI spectra cross-matched with Euclid Q1 are stored following the rule specid=Euclid{object_id}_DESI{desi_id}.fits

**Wavelength Reference**

Automatically retrieved from ``instruments_rules.json``:

- Merged: 3600–9824 Å, R = 5200, reference wavelength 9824 Å
- Flux units: ``erg / s / cm² / Å``, scale factor 1e-17

Generic Instrument
-------------------

The Generic driver is highly flexible and auto-detects FITS column layouts, making it
ideal for non-standard or external data formats.

**Grism**

  ``default`` (the only option)

**Supported spectra modes**

  ``individual fits`` and ``combined fits`` (metadata path not supported)

**Wavelength Auto-Detection**

The Generic driver has three fallback strategies for wavelength reconstruction (tried in order):

1. **SDSS-style log spacing** — if ``COEFF0`` and ``COEFF1`` keywords exist in the HDU header:

   .. code-block:: text

     wavelength = 10^(COEFF0 + COEFF1 * arange(NAXIS1))

2. **Log-linear WCS** — if ``CTYPE1`` contains ``'LOG'`` and WCS keywords (``CRVAL1``, ``CDELT1``, ``CRPIX1``) are present:

   .. code-block:: text

     log_wavelength = CRVAL1 + CDELT1 * (arange(NAXIS1) - (CRPIX1 - 1))
     wavelength = 10^log_wavelength

3. **Linear WCS (default)** — uses standard WCS keywords:

   .. code-block:: text

     wavelength = CRVAL1 + CDELT1 * (arange(NAXIS1) - (CRPIX1 - 1))

If none of these work, set ``lambda_edges`` in your config (see below).

**Binary Table Format**

Column auto-detection (first match wins):

+-------------------+--------------------------------------+
| Physical quantity | Column alias chain                   |
+===================+======================================+
| Wavelength        | ``wavelength`` → ``WAVE`` → ``LAMBDA`` |
|                   | (or WCS reconstruction if none found)|
+-------------------+--------------------------------------+
| Flux              | ``flux`` → ``FLUX`` → ``SIGNAL``     |
+-------------------+--------------------------------------+
| Error             | ``error`` → ``ERROR`` → ``NOISE``    |
|                   | → ``VAR`` (VAR is sqrt'd)            |
+-------------------+--------------------------------------+

**1-D Image HDU Format**

If the FITS has 1-D image HDUs instead of tables:

- **Flux** — extracted from the first 1-D image HDU
- **Error** — extracted from the next HDU if it exists and shape matches; else NaN
- **Wavelength** — always reconstructed from WCS header keywords (strategies 1–3 above)

**Flux Scale Factor**

Auto-read from the header (first match wins):

.. code-block:: text

  BSCALE → FLUXSCAL → FLUX_SCALE (defaults to 1.0)

**Wavelength Range**

Two options:

1. **Manual: set** ``lambda_edges`` **in config** (recommended for reproducibility):

   .. code-block:: yaml

     instrument:
       lambda_edges: [3500, 9500]  # [min, max] in Ångströms

2. **Auto-detect:** Leave ``lambda_edges`` unset. SpectraPyle reads the first spectrum
   in the catalog and infers the wavelength range from its header. **A warning is printed;**
   all spectra are assumed to share the same range. Use this only for homogeneous catalogs.

**Pixel Size Type**

The Generic driver does **not** support automatic instrumental or Nyquist pixel sizing.
You **must** specify ``pixel_size_type: manual`` and set ``pixel_resampling`` explicitly:

.. code-block:: yaml

  resampling:
    pixel_resampling_type: lambda      # or log_lambda
    pixel_size_type: manual            # Required
    pixel_resampling: 0.5              # Å per pixel (for lambda) or dex per pixel (for log_lambda)

Config Quick Reference
----------------------

Sample configurations for each instrument:

**Euclid (multi-grism)**

.. code-block:: yaml

  instrument:
    instrument_name: euclid
    survey_name: wide
    grisms: [red, blue]
    data_release: DR1

  io:
    spectra_mode: individual fits
    input_dir: /path/to/catalog
    filename_in: euclid_catalog
    output_dir: /path/to/output
    pixel_mask: [0]
    n_min_dithers: 3
    spectrum_edges: [10, -10]
    grism_io:
      red:
        spectra_dir: /data/euclid/red
      blue:
        spectra_dir: /data/euclid/blue

  resampling:
    pixel_resampling_type: lambda
    pixel_size_type: instrumental
    nyquist_sampling: 5.0

**DESI (back-compat with crossmatched Euclid)**

.. code-block:: yaml

  instrument:
    instrument_name: desi
    grisms: [merged]

  io:
    spectra_mode: individual fits
    input_dir: /path/to/catalog
    filename_in: euclid_desi_xmatch
    output_dir: /path/to/output
    grism_io:
      merged:
        spectra_dir: /data/desi/spectra

  resampling:
    pixel_resampling_type: log_lambda
    pixel_size_type: manual
    pixel_resampling: 0.0001

**Generic (any standard FITS)**

.. code-block:: yaml

  instrument:
    instrument_name: generic
    grisms: [default]
    lambda_edges: [3500, 9500]  # Manual wavelength range

  io:
    spectra_mode: individual fits
    input_dir: /path/to/catalog
    filename_in: my_catalog
    output_dir: /path/to/output
    grism_io:
      default:
        spectra_dir: /path/to/my_spectra

  resampling:
    pixel_resampling_type: lambda
    pixel_size_type: manual
    pixel_resampling: 0.5

Troubleshooting
---------------

**"No such column" error in Euclid/DESI**

  Check that your FITS has the expected binary table columns (with correct case and aliases).
  Use ``fitsio`` or ``astropy.io.fits`` to inspect::

    from astropy.io import fits
    with fits.open('spectrum.fits') as hdul:
        print(hdul[1].columns.names)

**"Could not infer wavelength range" for Generic**

  Either set ``lambda_edges`` in your config, or ensure the first spectrum in your catalog
  has proper WCS keywords (``CRVAL1``, ``CDELT1``, ``CRPIX1``) or SDSS-style keywords
  (``COEFF0``, ``COEFF1``).

**Generic driver not finding wavelength column**

  If none of the aliases (``wavelength``, ``WAVE``, ``LAMBDA``) match and WCS reconstruction fails,
  manually verify your FITS structure and consider using ``WAVE`` as the column name.

**Pixel size type "manual" is required for Generic**

  The Generic driver has no built-in instrumental constant (R value, reference wavelength).
  You must set ``pixel_size_type: manual`` and provide ``pixel_resampling`` in Å/pixel or dex/pixel.
