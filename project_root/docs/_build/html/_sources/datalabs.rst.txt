.. _datalabs:

===================================
ESA Datalabs Users
===================================

This guide is for Euclid scientists working on the **ESA Datalabs** platform. If you are accessing Euclid spectroscopic data through the Datalabs infrastructure, you can configure SpectraPyle to read directly from your data using the Science Archive System (SAS) query results.

Overview
--------

On ESA Datalabs, Euclid spectroscopic data is stored across the local Datalabs filesystem. Rather than downloading entire FITS files, you can:

1. Query the **SIR catalogue** using the SAS portal
2. Export the query results as a table (FITS, CSV, NPZ)
3. Use SpectraPyle's ``metadata path`` spectra mode to read spectra directly from the Datalabs filesystem

This approach is ideal for stacking large samples where you want to avoid the overhead of downloading thousands of FITS files.

Launching the GUI on Datalabs
-----------------------------

SpectraPyle includes a web-based configuration GUI (Voilà) that works on Datalabs through JupyterHub's server proxy mechanism.

**Installation**

When you install SpectraPyle with ``pip install -e ".[all]"``, the GUI dependencies (including ``jupyter-server-proxy``) are installed automatically.

**First-time setup**

  1. Install SpectraPyle on Datalabs (if not already done):

     .. code-block:: bash

       pip install -e ".[all]"

  2. Restart your personal JupyterLab server:

     - Click the **Hub** menu in JupyterLab → **Control Panel**
     - Click **Stop My Server**
     - Wait a few seconds, then click **Start My Server**

  This allows the newly installed ``jupyter-server-proxy`` to register with the Datalabs platform.

**Launching the GUI**

  Datalabs does not expose standard JupyterHub environment variables. To get a directly clickable URL, set the ``SPECTRAPYLE_HOST`` environment variable once — just the hostname, without any path. The session-specific path (which changes with each notebook) is detected automatically.

  1. Open a terminal in JupyterLab
  2. Set your Datalabs hostname. This is stable and the same for every session:

     .. code-block:: bash

       export SPECTRAPYLE_HOST=https://euclid.dataspace.esa.int

     You can add this line to your ``~/.bashrc`` or ``~/.profile`` so it persists across sessions.

  3. Navigate to the notebooks directory:

     .. code-block:: bash

       cd project_root/notebooks

  4. Run the GUI launcher:

     .. code-block:: bash

       python run_gui.py

  5. The terminal will print a fully clickable URL, with the correct session path detected automatically:

     .. code-block:: text

       [SpectraPyle] GUI starting on port 45678
       [SpectraPyle] Open in browser: https://euclid.dataspace.esa.int/data-analysis/apps/my-notebook/proxy/45678/

  6. Click or copy the URL and open it in your browser. The SpectraPyle GUI will load in a clean browser window with no notebook code visible.

  **Without** ``SPECTRAPYLE_HOST``: The script still prints a relative proxy path and a hint on how to set the variable. You can manually prepend your Datalabs hostname to construct the full URL.

**GUI workflow**

  Once the GUI is open, you can:

  - Load a previous configuration (``.gui`` file)
  - Configure the instrument, I/O paths, and processing parameters
  - Export your configuration as YAML, JSON, or ``.gui`` format
  - Run the stacking pipeline directly and monitor progress
  - View the output log and resulting stacked spectrum

  See :doc:`gui-tour` for a full walkthrough.

Accessing Internal Euclid Data
-------------------------------

**Authentication**

  If you are working with **internal Euclid data releases** (e.g., ``IDR1``, ``IQ2``, etc), your Datalabs session must be authenticated with the Euclid collaboration. Public data releases do not require additional authentication.

**Data Access**

  Once logged into Datalabs, you can query the SAS catalogue interactively. The Euclid NISP spectra are organized per data release. The SAS portal allows you to filter by survey, quality flags, and other criteria.

Querying the SIR Catalogue
--------------------------

The **SIR catalogue** contains metadata for all Euclid spectroscopic observations. When you export query results, the table includes:

- **object_id** or **source_id** — unique Euclid object identifier
- **redshift** — spectroscopic redshift (column name varies; check your query output)
- **datalabs_path** — local directory on the Datalabs filesystem where the spectrum FITS is stored (e.g., ``/data/euclid/internal/DR1/blablabla``)
- **file_name** — filename of the FITS file containing the spectrum (e.g., ``123456789101112131415.fits``)
- **hdu_index** — HDU number within the FITS file where the combined 1D spectrum data is located

The full path to the spectrum is: ``{datalabs_path}/{file_name}``, and the spectrum is read from HDU number ``{hdu_index}``.

Why Three Metadata Columns?
----------------------------

SpectraPyle's ``metadata path`` spectra mode is designed to handle non-standard file layouts. Instead of assuming all spectra follow a fixed naming pattern (e.g., ``{spectra_dir}/{specid}.fits``), the mode reads file paths and HDU indices directly from your catalogue.

The SIR catalogue splits this information across **three columns**:

1. **datalabs_path** — the directory containing the spectrum (varies per batch/release)
2. **file_name** — the filename within that directory (may not match the object ID)
3. **hdu_index** — the HDU number within the file

SpectraPyle combines the first two to form the full path (``datalabs_path + '/' + file_name``) and uses the third to select the correct HDU. This design is general-purpose: any workflow involving scattered or non-standard file layouts can use it. See :doc:`instruments` for the full specification.

Configuring SpectraPyle for Datalabs
------------------------------------

**Step 1: Prepare your catalogue**

  Export your SIR query results as a FITS, CSV, or NPZ file. Ensure the output includes columns for object ID, redshift, and the three path/index columns (``datalabs_path``, ``file_name``, ``hdu_index``).

**Step 2: Configure spectra mode**

  Set ``spectra_mode: metadata path`` and map the three catalogue columns to SpectraPyle's metadata configuration:

  .. code-block:: yaml

    io:
      spectra_mode: metadata path

    catalog_columns:
      ID_column_name: object_id
      redshift_column_name: redshift
      metadata:
        metadata_path_column_name: datalabs_path
        metadata_file_column_name: file_name
        metadata_indx_column_name: hdu_index

**Step 3: Run the stack**

  Via GUI or CLI. SpectraPyle will read each spectrum directly from the Datalabs filesystem using the three catalogue columns, with no intermediate downloads required.

**Full Example Config**

  .. code-block:: yaml

    instrument:
      instrument_name: euclid
      survey_name: wide
      grisms: [red]
      data_release: DR1

    io:
      input_dir: /datalabs/my_analysis
      filename_in: sir_catalogue_query
      spectra_mode: metadata path
      output_dir: /datalabs/my_analysis/output

    catalog_columns:
      ID_column_name: object_id
      redshift_column_name: redshift
      metadata:
        metadata_path_column_name: datalabs_path
        metadata_file_column_name: file_name
        metadata_indx_column_name: hdu_index

    redshift:
      z_type: rest_frame

    norm:
      norm_type: median

    resampling:
      pixel_resampling_type: lambda
      pixel_size_type: instrumental
      nyquist_sampling: 5.0

General Applicability
---------------------

While this guide focuses on Euclid data on Datalabs, the ``metadata path`` mode is **not Datalabs-specific**. Any scientific workflow where spectra are scattered across many files, or follow non-standard naming schemes, can use this mode. For example:

- **Individual FITS files, all with spectrum in HDU[1]:** Add a constant ``hdu_index`` column (filled with ``1`` for all rows) and point ``metadata_path_column_name`` and ``metadata_file_column_name`` to your directory and filename columns.
- **Legacy archive with mixed HDU layouts:** If HDU positions vary per file, explicitly list them in the ``hdu_index`` column and use ``metadata path`` mode.
- **Cross-matched or composite catalogues:** Combine file paths from multiple sources using this mode.

The SIR catalogue mapping is simply a concrete instance of this general mechanism.

References
----------

For more details on the ``metadata path`` spectra mode, see :doc:`instruments`. For the full configuration reference, see :doc:`/api/schema`.

External links:

- **Euclid Data Space:** https://euclid.dataspace.esa.int/
- **Euclid Collaboration:** https://www.euclid-ec.org/
