##########################################################################
## HISTORY:
## v5.0 optimesed the configuration for JSON/YAML standards amd CLI approach (for HPC users)
## v5.0 made a GUI accessible from external port (via python script, voila package)
## v5.0 completely revised the module structure of the project, added a schema with a rigid control over the configuration paramters, and a runtime adapter function that guarantees agreement between raw configuration and validated configuration
## v4.7 generated configuration for ingesting DESI spectra 
## v4.7 Implemented possibility to perform stacking following Francis+1991 (for QSOs and for generating spectral templates)
## v4.7 Pixel size can now be either deducted from the instrumental resolution (Nyquist sampling) or manually ingested.
## v4.7 added possibility to sampling either on a regular dl constant or logarithmic dl/l (or velocity) costant wavelength grid.
## v4.7 module plot.py completely renovated with modern plotly packages 
## v4.7 Checked and approved all functions measuring statistics on stacked spectra
## v4.7 Added possibility to stack spectra in the observed frame, with the flexibility to keep the original wavelengths and pixel scale (typical case for coadding repeated spectra of the same source), or to resample them over a new wavelength grid. 
## v4.7 Added the possibility to read spectra (only for Euclid.py so far) stored in a single fits file, in a HDU called 'SPECTRA'
## v4.7 reviewed and improved efficiency of the functions that calculate the statistics of the stacked spectra
## v4.7 changed the name of the modules from stackSpec (old name already used for another python package) to spectraPyle (the official name published in https://ui.adsabs.harvard.edu/abs/2025arXiv250916120E/abstract. 
## v4.7 Improved resampling function, now adapted from Fruchter & Hook 2002 (see .utils/resampling.py)
## v4.6 implemented Galactic extinction correction, following Gordon+23 (see ./utils/extinction.py). The two config file's keywords for including corrections are galExt:True or False, galExt_name=name-of-the-column-containing-the-E(B-V) values.
## v4.5 Improved the configuration file 
## v4.5 Added possibility to exclude N first and M last pixels (alternative to the bitmask 2 in Euclid)
## v4.5 Added possibility to customize wavelength range of the stacked spectrum
## v4.5 Fixed bugs when normalizing flux within a wavelength interval.
## v4.5 Removed limit to two CPUs (it was in place since v4.4)
## v4.4 Imporved reading procedure, by storing chunks of spectra (fixed for now to 500/chunk) in h5 file, necessary for reading > 10 000 spectra (to avoid fatal RAM issues).
## v4.4 Reduced the number of max CPUs to two (due to Euclid Datalabs resources/user). To be revised in the near feature if the resources/user. will be increased, or if the code is used in a different environment (e.g., private cluster, etc.). 
## v4.4 Saving the 2D array containing the processed spectra to external .h5 file (stored in the /path_to_output/ directory defined in the config file)
## v4.4 Added a time counter when reading the spectra and when bootstrapping (see ./utils/IO.py , and ./utils/statistics.py) 
## v4.3.1 Updated the file name of the output products (see ./utils/config.py)
## v4.3 Added possibility to stack at the minimum and maximum redshift of the redshift distribution of the sample to be stacked.
## v4.2 Upgraded counts of initial, good, and bad pixels (see rows 272-300)
## v4.2 Modified the resampling function (see ./utils/resampling.py) and fixed a bug with resampling the spectra. Modified, accordingly, also ./utils/IO.py that calls the resampling function.
## v4.0 Added multiprocessing to the reading spectra function to speed up computational performances (see ./utils/IO.py)
## v3.1 main: saving 16th, 84th, 98th, 99th percentiles
## v3.1 main: saving list of IDs and redshift of the galaxies in the composite spectrum
## v3.1 statistics.py: return percentiles of flux distributions per pixel
## v3.1 normalization.py: returning the normalization factor used
## v3.1 main: adding "conservation" choice (i.e., either flux or luminosity conservation)
## v3.1 spectra.py: adding "conservation" choice (i.e., either flux or luminosity conservation)
