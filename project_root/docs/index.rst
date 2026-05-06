SpectraPyle Documentation
=========================

SpectraPyle is a flexible, scalable tool for stacking galaxy spectra.
It shifts spectra to a common rest frame, normalizes, resamples, sigma-clips,
and combines them using six stacking estimators: mean, median, geometric mean (lenient & strict),
mode (HSM), and weighted mean. Includes bootstrap uncertainty estimation and interactive plots.

**Supported instruments:** Euclid (NISP) · DESI · Generic (any standard FITS)

**Development team:** S. Quai, L. Pozzetti, M. Moresco, M. Talia, Z. Mao, X. Lopez Lopez, E. Lusso, S. Fotopoulou
**Maintainer:** Salvatore Quai (salvatore.quai@unibo.it)
**License:** MIT

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   quickstart
   gui-tour
   instruments
   citation

.. toctree::
   :maxdepth: 2
   :caption: Concepts

   normalization
   resampling
   statistics
   plotting

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/stacking
   api/schema
   api/processes
   api/instruments
   api/io
   api/spectrum
   api/statistic
   api/plot
   api/utils
