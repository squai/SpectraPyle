Quick Start
===========

Installation
------------

For GUI/Jupyter usage (recommended for most users):

.. code-block:: bash

   git clone https://github.com/squai/SpectraPyle
   cd SpectraPyle/project_root
   pip install -e ".[notebook]"

The ``notebook`` extra installs the dependencies required by the ipywidgets GUI and
by the local Voilà launcher. For core/CLI-only usage, ``pip install -e .`` is
sufficient.

Once installed, SpectraPyle is available as a standard Python package and can be
imported from your own notebooks or Python scripts. The notebooks shipped with the
repository are convenience/tutorial interfaces rather than a requirement for using
the package.

Local GUI via Voilà
-------------------

On a local machine, the convenience launcher starts a Voilà server and opens the GUI
in your default browser:

.. code-block:: bash

   python notebooks/run_gui.py

If the browser does not open automatically, use the local URL printed in the terminal.
Press ``Ctrl+C`` in the terminal to stop the server.

JupyterLab / ESA DataLabs
-------------------------

In Jupyter environments, including ESA DataLabs, the same GUI can be rendered directly
inside a notebook cell, without Voilà or a separate browser window:

.. code-block:: python

   from spectraPyle.gui import start

   start()

Alternatively, open ``notebooks/gui_launcher.ipynb``, which contains the same minimal
launcher. ESA DataLabs users should run the notebook with the ``EUCLID-TOOLS`` kernel;
see :doc:`datalabs` for the DataLabs-specific workflow.

Running via CLI
---------------

After installation, the standard command-line entry point is:

.. code-block:: bash

   spectrapyle --config path/to/config.yaml

A helper script is also available:

.. code-block:: bash

   python notebooks/run_cli.py --config path/to/config.yaml [--log-level INFO]

The helper provides automatic timestamped logging and supports YAML/JSON configuration
files. Available log levels include ``DEBUG``, ``INFO``, and ``WARNING``.

Override individual configuration keys at runtime, for example:

.. code-block:: bash

   spectrapyle --config config.yaml --instrument.grisms '["red","blue"]'

Post-stacking Analysis
----------------------

**Plot Helper** — Visualize the stacked spectrum:

.. code-block:: bash

   jupyter notebook notebooks/plot_helper.ipynb

Interactive notebook showing all estimators (mean, median, geometric mean, weighted mean)
and pixel count information.

**Spectral Line Manager** — Configure spectral lines in plots:

.. code-block:: bash

   jupyter notebook notebooks/line_manager.ipynb

Enable/disable emission lines and absorption features via checkboxes. Saved settings are
picked up by the next ``plotting()`` call.

Configuration Pipeline
----------------------

All inputs pass through a strict validation pipeline::

   Widgets / JSON / YAML / CLI
       ↓
   normalize_raw_config()        runtime/runtime_adapter.py
       ↓
   StackingConfig (Pydantic v2)  schema/schema.py
       ↓
   StackingConfigResolver        schema/schema.py
       ↓
   flatten_schema_model()        runtime/runtime_adapter.py
       ↓
   Stacking(flat_dict).run()     stacking/stacking.py
