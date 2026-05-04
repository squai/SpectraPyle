Quick Start
===========

Installation
------------

.. code-block:: bash

   pip install -e ".[all]"

Running via Voilà GUI
---------------------

.. code-block:: bash

   python project_root/notebooks/run_gui.py

Opens a browser tab with an interactive config builder.

Running via CLI
---------------

**Option 1: Using the CLI helper script (recommended)**

.. code-block:: bash

   python project_root/notebooks/run_cli.py --config path/to/config.yaml [--log-level INFO]

Features: automatic logging setup with timestamp, supports YAML/JSON, log levels: DEBUG/INFO/WARNING

**Option 2: Direct CLI invocation**

.. code-block:: bash

   python project_root/src/spectraPyle/stacking/stacking.py --config path/to/config.yaml

Override individual keys at runtime:

.. code-block:: bash

   python project_root/src/spectraPyle/stacking/stacking.py --config config.yaml --instrument.grisms '["red","blue"]'

Post-stacking Analysis
----------------------

**Plot Helper** — Visualize the stacked spectrum:

.. code-block:: bash

   jupyter notebook project_root/notebooks/plot_helper.ipynb

Interactive notebook showing all estimators (mean, median, geometric mean, weighted mean) and pixel count information.

**Spectral Line Manager** — Configure spectral lines in plots:

.. code-block:: bash

   jupyter notebook project_root/notebooks/line_manager.ipynb

Enable/disable emission lines and absorption features via checkboxes. Saved settings are picked up by the next ``plotting()`` call.

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
