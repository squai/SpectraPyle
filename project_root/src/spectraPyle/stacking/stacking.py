#!/bin/python3
"""Orchestrate the full spectral stacking pipeline.

Reads a catalog, processes spectra in parallel chunks of 500
(shift → resample → normalize), applies sigma-clipping, computes
stacking statistics (median / mean / weighted mean / geometric mean),
and writes the result as a two-HDU FITS file.

Entry point: :func:`main`.
"""

# -------------- spectraPyle --------------- #
__author__ = "Salvatore Quai"
__credits__ = ["Salvatore Quai",
"Lucia Pozzetti",
"Michele Moresco",
"Margherita Talia",
"Zhiying Mao",
"Xavier Lopez Lopez",
"Elisabeta Lusso",
"Sotiria Fotopoulou"]
__version__ = "5.0.2"
__maintainer__ = "Salvatore Quai"
__email__ = "salvatore.quai@unibo.it"
__status__ = "Developement"

# -------------- Packages --------------
import os
import os.path
import sys
import argparse
from pathlib import Path
import yaml
import json
import h5py
import warnings
#warnings.filterwarnings('ignore')
import importlib

import numpy as np

from astropy.stats import sigma_clip
from astropy.cosmology import FlatLambdaCDM

from multiprocessing import Pool

import spectraPyle
importlib.reload(spectraPyle)

from spectraPyle.schema.schema import StackingConfig, StackingConfigResolver
from spectraPyle.runtime.runtime_adapter import (
    flatten_schema_model,
    build_config_from_json,
    build_config_from_yaml,
    build_config_from_dict
    )
from spectraPyle.utils.log import setup_logging, get_logger

logger = get_logger(__name__)

import spectraPyle.io.IO as sio
import spectraPyle.process.processes as spr
import spectraPyle.statistic.statistics as sstat
import spectraPyle.plot.plot as spl
import spectraPyle.spectrum.normalization as snorm
from spectraPyle.io.filename_builder import build_filename
#importlib.reload(sio)
#importlib.reload(spr)
#importlib.reload(sstat)
#importlib.reload(spl)
#importlib.reload(snorm)

#from typing import Optional, List, Literal, Dict, Any, Tuple
from typing import Optional, Any

# -------------- Stacking -------------
class Stacking:
    """Orchestrates the full spectral stacking pipeline.

    Loads a flat configuration dictionary (produced by
    :func:`~spectraPyle.runtime.runtime_adapter.flatten_schema_model`), sets up
    cosmology and multiprocessing, then calls :meth:`run` to execute the pipeline.

    Parameters
    ----------
    config_dict : dict
        Flat configuration dictionary. Keys follow the legacy flat-dict convention
        (e.g. ``config['grism_io']['red']['spectra_dir']``).

    Attributes
    ----------
    config : dict
    inst : module
        Dynamically loaded instrument module (e.g. ``spectraPyle.instruments.euclid``).
    cosmology : astropy.cosmology.FlatLambdaCDM
    num_cpus : int or None
        Number of worker processes; ``None`` when multiprocessing is disabled.
    """

    def __init__(self, config_dict):
        
        self.config = config_dict
        
        # ------ Title ---------
        self.width_print = 80
        print("\n" + "*" * self.width_print)
        print(f"spectraPyle - Version {__version__}".center(self.width_print))
        print(f"Contact: {__email__}".center(self.width_print))
        print(f"Status: {__status__}".center(self.width_print))
        print("*" * self.width_print + "\n")
        
        
        # ---------- Filename ----------
        if self.config["filename_out"] == "AUTO":

            self.config["filename_out"] = build_filename(self.config)
        
        print (f"\nConfiguration: {self.config}")
        
        print (f"\nStarting stacking: {self.config['filename_in']}")
        
        # ---------- Instrument ----------
        instrument_loader = InstrumentLoader()
        self.inst = instrument_loader.get_instrument_module(self.config["instrument_name"])
        
        # ---------- Output directory ----------
        output_path = Path(self.config['output_dir'])
        output_path.mkdir(parents=True, exist_ok=True)  
        
        # ---------- Cosmology ----------
        self.cosmology = FlatLambdaCDM(H0=self.config['cosmo_H0'], Om0=self.config['cosmo_Om0'])
        
        max_cpu_fraction = self.config["max_cpu_fraction"]
        if self.config['multiprocessing']:    
            self.num_cpus = int(max(1, max_cpu_fraction*sio.get_effective_cpu_limit()))
        else:
            self.num_cpus = None
        
        print (f"Multiprocessing: using {self.num_cpus} CPUs")
        
        # ----------- Fixed variables (To be deprecated) ------
        self.config["air_vacuum"] = False
        self.config["save_to_file"] = True
            
    # ------------ RUN --------------
    def run(self):
        """Execute the stacking pipeline end-to-end.

        Pipeline steps:

        1. Read catalog and build wavelength grid.
        2. Split catalog into chunks of 500 spectra.
        3. For each chunk: call :func:`~spectraPyle.process.processes.main_parallel`,
           accumulate resampled spectra in an intermediate HDF5 file.
        4. Load the full resampled array, apply sigma-clipping.
        5. Compute stacking statistics (mean, median, geometric mean, weighted mean).
        6. Write output FITS file via :func:`~spectraPyle.io.IO.write_stack`.
        7. Optionally generate a Plotly plot.

        Returns
        -------
        None
            Results are written to disk at ``config['output_dir']``.

        Side effects
        -----------
        Creates ``<output_dir>/<filename_out>_array.h5`` (intermediate, deleted after use)
        and ``<output_dir>/<filename_out>.fits`` (final output).
        """
        # --- Initialize an empty dictionary that will contain the main results ---# 
        data_dict = {}

        # --- initializing variables --- #

        keys_input = [self.config['ID_column_name']]

        if self.config['z_type'] != 'observed_frame':
            keys_input.append(self.config['redshift_column_name'])

        if self.config['galactic_extinction']:
            keys_input.append(self.config['gal_ext_column_name'])

            logger.info("-" * self.width_print + "\n")
            logger.info("Galactic Extinction Correction:\n")
            print(
                "This code uses the Gordon+23 extinction curve via the "
                "'dust_extinction' Python package:\n"
                "https://dust-extinction.readthedocs.io/\n\n"
                "If you use this functionality, please follow the citation policy "
                "for the G23 model, available here:\n"
                "https://dust-extinction.readthedocs.io/en/latest/dust_extinction/references.html\n"
            )
            logger.info("-" * self.width_print + "\n")

        if self.config['spectra_normalization'] == 'custom':
            keys_input.append(self.config['custom_column_name'])

        if self.config['spectra_mode'] == 'metadata path':
            keys_input.append(self.config['metadata_path_column_name'])
            keys_input.append(self.config['metadata_file_column_name'])
            keys_input.append(self.config['metadata_indx_column_name'])


        data_input = sio.read_catalog(self.config['input_dir'], self.config['filename_in'], extension=self.config['filename_in_extention'], mandatory_keys=keys_input)


        if self.config['spectra_normalization'] == 'template':
            sio.z_sort(z_column_name=self.config['redshift_column_name'], data_input=data_input)

        specIDs = data_input[self.config['ID_column_name']]

        if self.config['galactic_extinction']:
            ebv_galactic = data_input[self.config['gal_ext_column_name']]
        else:
            ebv_galactic = np.zeros_like(specIDs, dtype=float)

        if self.config['spectra_normalization'] == 'custom':
            custom_norm_param = data_input[self.config['custom_column_name']]
        else:
            custom_norm_param = np.ones_like(specIDs, dtype=float)


        if self.config['z_type'] != 'observed_frame':
            """ redshift array """
            redshift = data_input[self.config['redshift_column_name']]

            """ defining the redshift of the stacking """
            zMin, zMax, data_dict['z_stacking'] = sio.z_stack(redshift=redshift,
                                                          z_type=self.config['z_type'],
                                                          conservation=self.config['conservation'])
        else:
            print ('The stacked spectrum will be generated at the observed frame')
            redshift = np.full_like(specIDs, np.nan, dtype=float)
            #redshift = 'none'
            data_dict['z_stacking'] = 'observed_frame'
            zMin = zMax = np.nan


        """ defining the minimum and maximum wavelength of the stacked spectrum """
        
        wavelMin, wavelMax, grismList = self.inst.prepare_stacking(self.config, z_stacking=data_dict['z_stacking'], zMin=zMin, zMax=zMax, lambda_edges=self.config['lambda_edges_rest'])

        if self.config['pixel_resampling_type'] != 'none':
            data_dict['wavelength_stacking'], wavelength_stacking_bins, data_dict['pixelResampling'] = sio.build_wavelength_grid(
                wavelMin,
                wavelMax,
                self.config,
                data_dict['z_stacking']
            )

            if self.config['pixel_resampling_type'] in ['lambda', 'lambda_shifted']:
                print ("Δλ[AA] (constant) = {:.2e}".format(data_dict['pixelResampling']))
            elif self.config['pixel_resampling_type'] == 'log_lambda':
                logger.debug("Δlog λ (constant) = {:.2e}".format(data_dict['pixelResampling']))

        else:
            inst = importlib.import_module(
            f"spectraPyle.supported_instruments.{self.config['instrument_name']}"
            )

            if self.config.get('spectra_mode') == 'metadata path':
                metadata_name = (
                    data_input[self.config['metadata_path_column_name']]
                    + '/'
                    + data_input[self.config['metadata_file_column_name']]
                )

                hdu_indx = data_input[self.config['metadata_indx_column_name']]
                if metadata_name is None or hdu_indx is None:
                    raise ValueError(
                        "metadata_name and hdu_indx must be provided in metadata mode"
                    )

                data_dict['wavelength_stacking'], _, _ = inst.readSpec_metadata(
                    self.config, specIDs[0], metadata_name, hdu_indx
                )
            else:
                first_grism = self.config['grisms'][0]
                data_dict['wavelength_stacking'], _, _ = inst.readSpec(self.config, specIDs[0], first_grism)


            data_dict['pixelResampling'] = 'original'
            wavelength_stacking_bins = 'original'


        #################################################################################################################
        data_dict.update({
                        'initialPixelCount': [], 
                        'badPixelCount': [], 
                        'sigmaClippedCount': [], 
                        'goodPixelCount': [],
                        'voidPixelCount': []
                        })
    #################################################################################################################

        chunk_size = 500  # Process in chunks of N spectra
        #num_chunks = max(1, round(len(specIDs) / chunk_size))  # Ensure at least 1 chunk
        num_chunks = max(1, int(np.ceil(len(specIDs) / chunk_size)))

        print("-" * self.width_print + "\n")
        print (f"Processing {len(specIDs)} spectra, split in {num_chunks} chunks.")
        print("-" * self.width_print + "\n")

        # Detect type of first non-null element
        first_id = next((x for x in specIDs if x is not None), None)
        if isinstance(first_id, (int, np.integer, np.int64)):
            # Pure numeric IDs -> store as integer
            dtype_id = "i8"
        else:
            # Mixed or string IDs → use UTF-8 string dtype
            dtype_id = h5py.string_dtype(encoding="utf-8")
                
        #hdf5_filename = self.config['output_dir'] + self.config["filename_out"] + '_array'
        #with h5py.File(hdf5_filename+'.h5', "w") as f:
        
        hdf5_path = self.config['output_dir'] / f"{self.config['filename_out']}_array.h5"
        with h5py.File(hdf5_path, "w") as f:
            
            # Create compressed HDF5 datasets with chunking
            if "stackArr" not in f:
                stackArr_dset = f.create_dataset("stackArr", shape=(len(data_dict['wavelength_stacking']), 0), 
                                            maxshape=(len(data_dict['wavelength_stacking']), None), dtype="f8",
                                            chunks=(len(data_dict['wavelength_stacking']),chunk_size), 
                                            compression="gzip", compression_opts=9) 
                stackArrErr_dset = f.create_dataset("stackArrErr", shape=(len(data_dict['wavelength_stacking']), 0), 
                                               maxshape=(len(data_dict['wavelength_stacking']), None), dtype="f8",
                                               chunks=(len(data_dict['wavelength_stacking']), chunk_size), 
                                               compression="gzip", compression_opts=9) 

                spectraIDlist_dset = f.create_dataset("object_id", shape=(0,),
                                maxshape=(None,), dtype=dtype_id,
                                chunks=(chunk_size,),
                                compression="gzip", compression_opts=9)

                norm_factor_dset = f.create_dataset("norm_factor", shape=(0,),
                                maxshape=(None,), dtype="f8",
                                chunks=(chunk_size,),
                                compression="gzip", compression_opts=9)

                grism_label_dset = f.create_dataset("grism_label", shape=(0,),
                                maxshape=(None,), dtype=h5py.special_dtype(vlen=str),
                                chunks=(chunk_size,))
            else:
                stackArr_dset = f["stackArr"]
                stackArrErr_dset = f["stackArrErr"]
                spectraIDlist_dset = f["object_id"]
                norm_factor_dset = f["norm_factor"]
                grism_label_dset = f["grism_label"]


            for i in range(num_chunks):
                logger.info(f"Processing chunk {i+1}/{num_chunks}...")

                start_idx = i * chunk_size
                end_idx = min((i + 1) * chunk_size, len(specIDs))

                # Read chunk
                chunk_specIDs = specIDs[start_idx:end_idx]
                chunk_redshift = redshift[start_idx:end_idx]                
                chunk_ebv_galactic = ebv_galactic[start_idx:end_idx]
                chunk_custom_norm_param = custom_norm_param[start_idx:end_idx]
                chunk_data_input = {key: val[start_idx:end_idx] for key, val in data_input.items()}

                # ----- processing the spectra ------ #
                chunk_stackArr, chunk_stackArrErr, norm_factor, spectra_not_found, chunk_spectraIDlist, chunk_grism_labels = spr.main_parallel(
                        self, chunk_specIDs, chunk_redshift, chunk_ebv_galactic,
                        chunk_custom_norm_param,
                        wavelength_stacking_bins, data_dict['pixelResampling'],
                        data_dict['z_stacking'], grismList, chunk_data_input
                    )

                # Compute counts
                initialPixelCount = np.sum(~np.isinf(chunk_stackArr), axis=1)
                badPixelCount = np.sum(np.isnan(chunk_stackArr), axis=1)
                voidPixelCount = np.sum(np.isinf(chunk_stackArr), axis=1) ## number of spectra with flux=np.inf in a given pixel 

                # Convert inf → NaN for sigma clipping
                chunk_stackArr = np.where(chunk_stackArr == np.inf, np.nan, chunk_stackArr)
                chunk_stackArrErr = np.where(chunk_stackArrErr == np.inf, np.nan, chunk_stackArrErr)

                # Get current number of spectra (num_spectra) before resizing
                current_spectra_count = stackArr_dset.shape[1]  # How many spectra are already stored

                # Compute new total size
                new_size = current_spectra_count + chunk_stackArr.shape[1]

                # Resize datasets to accommodate new chunk
                stackArr_dset.resize((stackArr_dset.shape[0], new_size))  # Resize along num_spectra
                stackArrErr_dset.resize((stackArrErr_dset.shape[0], new_size))  # Resize along num_spectra

                spectraIDlist_dset.resize((new_size,))  # Resize along num_spectra
                norm_factor_dset.resize((new_size,))
                grism_label_dset.resize((new_size,))

                # Correctly insert new chunk at the end of the dataset
                stackArr_dset[:, current_spectra_count:new_size] = chunk_stackArr
                stackArrErr_dset[:, current_spectra_count:new_size] = chunk_stackArrErr

                chunk_spectraIDlist = np.array(chunk_spectraIDlist)
                spectraIDlist_dset[current_spectra_count:new_size] = chunk_spectraIDlist
                norm_factor_dset[current_spectra_count:new_size] = norm_factor
                grism_label_dset[current_spectra_count:new_size] = chunk_grism_labels

                # Store in dictionary
                if i == 0:
                    data_dict['initialPixelCount'] = initialPixelCount
                    data_dict['badPixelCount'] = badPixelCount
                    data_dict['voidPixelCount'] = voidPixelCount
                else:
                    data_dict['initialPixelCount'] += initialPixelCount
                    data_dict['badPixelCount'] += badPixelCount
                    data_dict['voidPixelCount'] += voidPixelCount


            stackArr = f["stackArr"][:]
            stackArrErr = f["stackArrErr"][:]


            # Sigma Clipping
            if self.config['sigma_clipping_conditions'] > 0:
                stackArr = sigma_clip(stackArr, 
                                      sigma=self.config['sigma_clipping_conditions'],
                                      maxiters=None, axis=1,
                                      cenfunc=np.nanmean, copy=False).filled(np.nan)

            stackArrErr = np.where(np.isnan(stackArr), np.nan, stackArrErr)

            # Compute some other counts
            data_dict['sigmaClippedCount'] = np.sum(np.isnan(stackArr), axis=1) - data_dict['badPixelCount'] - data_dict['voidPixelCount']

            #initialPixelCount - badPixelCount
            data_dict['goodPixelCount'] = data_dict['initialPixelCount'] - data_dict['badPixelCount'] - data_dict['sigmaClippedCount']

            data_dict['templateNormMaskedCount'] = np.zeros_like(data_dict['goodPixelCount'])

            # ------ francis+1991 like normalization -------
            if self.config['spectra_normalization'] == 'template':
                pre_nan = np.sum(np.isnan(stackArr), axis=1)
                stackArr, stackArrErr, alphas = snorm.francis1991_normalize(
                stackArr,
                stackArrErr,
                norm_stat="median"
                #norm_stat="mean"
                )
                templateNormMaskedCount = np.sum(np.isnan(stackArr), axis=1) - pre_nan
                data_dict['templateNormMaskedCount'] = templateNormMaskedCount
                data_dict['goodPixelCount'] -= templateNormMaskedCount

                # update norm_factor with actual alpha values from template normalization
                f['norm_factor'][:] = alphas

                # write new datasets (do NOT overwrite originals)
                f.create_dataset("stackArr_norm", data=stackArr, compression="gzip")
                f.create_dataset("stackArrErr_norm", data=stackArrErr, compression="gzip")
            # -----------------------------------------------

        logger.info(f"Processing complete. The array containing the processed spectra has been stored in the HDF5 file {hdf5_path}.")

        #################################################################################################################
        """ statistics: """
        data_dict['stackSPmean'], data_dict['stackDISPmean'], data_dict['stackSPmed'], data_dict['stackDISPmed'], data_dict['stackSPgeomMean'], data_dict['stackDISPgeomMean'], \
            data_dict['stackSPmeanWeighted'], data_dict['stackDISPmeanWeighted'], data_dict['stackERmeanWeighted'], data_dict['stackPERC16th'], \
            data_dict['stackPERC84th'], data_dict['stackPERC98th'], data_dict['stackPERC99th'], \
            data_dict['geomMeanPixelCount'], data_dict['stackSPmode'], data_dict['stackDISPmode'], \
            data_dict['stackSPgeomMeanStrict'], data_dict['stackDISPgeomMeanStrict'] = sstat.stack_statistics(stackArr, stackArrErr)


        if np.all(np.isnan(data_dict['stackSPgeomMean'])):
            warning_message = (
                "\n WARNING: the Geometric mean stacked spectrum contains NaN values EXCLUSIVELY! \n"
                "This may be due to one or more input spectra containing zero or negative fluxes in each pixel of the stacked spectrum. \n"
                "The geometric mean is defined only for positive values. Please review your input data. \n"
            )
            warnings.warn(warning_message)
        elif np.any(np.isnan(data_dict['stackSPgeomMean'])):
            warning_message = (
                "\n Warning: The geometric mean stacked spectrum may be unreliable. \n"
                "It contains NaN or negative values, possibly due to zero or negative fluxes in one or more input spectra. \n"
                "The geometric mean is defined only for positive values. Please be careful when using the geometric mean stacked spectrum. \n"
            )
            warnings.warn(warning_message)


        #################################################################################################################
        """ bootstrap with replacement (for statistical uncertainties estimation): """

        if self.config['bootstrapping_R'] > 0:
            _, data_dict['stackERmean'], _, data_dict['stackERmed'], _, data_dict['stackERgeomMean'], _, data_dict['stackERmode'], _, data_dict['stackERgeomMeanStrict'] = sstat.bootstrStack(arr=stackArr,R=self.config['bootstrapping_R'],n_processes=self.num_cpus)
        else:
            data_dict['stackERmean'] = data_dict['stackDISPmean'] / np.sqrt(data_dict['goodPixelCount'])
            data_dict['stackERmed'] = data_dict['stackDISPmed'] / np.sqrt(data_dict['goodPixelCount'])
            data_dict['stackERgeomMean'] = data_dict['stackDISPgeomMean'] / np.sqrt(data_dict['goodPixelCount'])
            data_dict['stackERmode'] = data_dict['stackDISPmode'] / np.sqrt(data_dict['goodPixelCount'])
            data_dict['stackERgeomMeanStrict'] = data_dict['stackDISPgeomMeanStrict'] / np.sqrt(data_dict['goodPixelCount'])

            """ note: about the error spectrum of the weighted average spectrum see ./stackingEuclid/utils/statistics.py """


        #################################################################################################################
        """ saving to file: """
        output_filename = None
        if self.config['save_to_file']:
            output_filename = sio.save_to_file(self.config, data_dict)


        #################################################################################################################
        """ Closing the program: """
        print("-" * self.width_print + "\n")
        #print ('spectra_not_found: ', spectra_not_found)
        print ('N. of spectra not found (or corrupted): ', len(spectra_not_found[spectra_not_found != 'nan']))
        if len(spectra_not_found[spectra_not_found != 'nan']) > 0:
            print ('IDs of spectra not found (or corrupted):')
            for sp_n_f in spectra_not_found:
                if sp_n_f != 'nan':
                    print (sp_n_f)

        print (self.config['filename_in'], ' stacking completed.')
        print("#" * self.width_print + "\n")
        print ()

        return output_filename

class InstrumentLoader:
    """Dynamic loader for per-instrument driver modules.

    Loads instrument-specific modules (euclid, desi) based on configuration.
    """

    def __init__(self):
        self._modules_cache: dict[str, Any] = {}
    
    def get_instrument_module(self, instrument_name: str) -> Any:
        """Load and return the instrument driver module.

        Parameters
        ----------
        instrument_name : str
            Instrument name ('euclid' or 'desi').

        Returns
        -------
        module
            Dynamically imported module containing readSpec, readSpec_metadata, prepare_stacking.

        Raises
        ------
        ImportError
            If the instrument module cannot be imported.
        """
        module_name = f"spectraPyle.instruments.{instrument_name}"
        
        if module_name not in self._modules_cache:
            # First time: import
            module = importlib.import_module(module_name)
            self._modules_cache[module_name] = module
            return module
        
        # Already imported: reload if needed
        module = self._modules_cache[module_name]
        importlib.reload(module)
        self._modules_cache[module_name] = module  # Update cache
        return module

        
def load_config_file(path):

    path = Path(path)

    if path.suffix in [".yaml", ".yml"]:
        with open(path) as f:
            raw = yaml.safe_load(f)

    elif path.suffix == ".json":
        with open(path) as f:
            raw = json.load(f)

    else:
        raise ValueError("Unsupported config format")

    return raw     
        


def validate_config(raw_dict):
    return StackingConfig(**raw_dict)

def run_stacking(config):
    stack = Stacking(config)
    output_filename = stack.run()
    return output_filename


def main(config):
    """CLI and programmatic entry point.

    Accepts a path to a YAML/JSON config file or a pre-built config dict,
    validates it through the full pipeline, and runs :class:`Stacking`.

    Parameters
    ----------
    config : str, Path, or dict
        Path to a YAML/JSON config file, or a pre-validated flat config dict.
    """

    if isinstance(config, str):
        print ("Reading and validating config from file")
        raw = load_config_file(config)
        cfg = validate_config(raw)

    elif isinstance(config, dict):
        print ("Reading and validating config from dictionary")
        cfg = validate_config(config)

    else:
        cfg = config   
        
    print ("✅ Configuration file read!")
    print (f"\n Using: {cfg}")
    
    cfg = flatten_schema_model(cfg) # to be deprecated. 

    return run_stacking(cfg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spectral stacking pipeline")
    parser.add_argument("--config", type=str, required=True, help="Path to config file (YAML or JSON)")
    args = parser.parse_args()
    main(args.config)
