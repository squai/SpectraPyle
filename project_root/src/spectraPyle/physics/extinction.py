"""
Galactic dust extinction correction.

Applies the Gordon et al. (2023) extinction law via the ``dust_extinction``
package to correct observed spectra for Milky Way foreground dust.
"""

import numpy as np
#import dust_extinction
from dust_extinction.parameter_averages import G23
import astropy.units as u

from spectraPyle.utils.log import get_logger

logger = get_logger(__name__)

def AA_to_micron(lbd_A):
    """Convert wavelengths from Angstroms to micrometers.

    Parameters
    ----------
    lbd_A : ndarray or float
        Wavelength in Angstroms.

    Returns
    -------
    ndarray or float
        Wavelength in micrometers.
    """
    return lbd_A / 1e4

def dustCorr_Gordon23(wave_A, ebv, Rv=3.1):
    """Apply Gordon et al. (2023) galactic extinction correction.

    Uses the G23 extinction model from the ``dust_extinction`` package
    to correct for Milky Way dust foreground reddening.

    CITATION POLICY:
    This code uses the Gordon+23 extinction curve via the
    'dust_extinction' Python package:
    https://dust-extinction.readthedocs.io/
    If you use this functionality, please follow the citation policy
    for the G23 model, available here:
    https://dust-extinction.readthedocs.io/en/latest/dust_extinction/references.html

    Parameters
    ----------
    wave_A : ndarray
        Wavelength array in Angstroms.
    ebv : float
        Foreground dust extinction E(B-V) in magnitudes.
    Rv : float, optional
        Total-to-selective extinction ratio. Default 3.1.

    Returns
    -------
    ndarray
        Extinction correction factor (flux multiplier, >= 1).
    """
    ext_model_G23 = G23(Rv)
    
    wave_micron = AA_to_micron(wave_A) * u.micron
    
    extinction_factor = 1./ext_model_G23.extinguish(wave_micron, Ebv=ebv)
    
    return extinction_factor

    
"""


def extinctionLaw_IR_Cardelli89(x, Rv=3.1):
    ## mean extinction law (A_lambda/A(V)) from Cardelli + 1989, Apj 345, 245
    a_x = 0.574 * x ** 1.61
    b_x = -0.527 * x ** 1.61
    return a_x + b_x / Rv

def dust_IR_Cardelli89(wave, ebv, Rv=3.1, unit_wave='mu'):
    ## Extinction law: Cardelli et al 1989, ApJ 345, 245
    
    if unit_wave == 'AA':
        wave = AA_to_micron(wave)
    elif unit_wave == 'mu':
        None
    else:
        raise NameError('wavelength unit not supported yet')
    
    x = 1. / wave
    
    law = extinctionLaw_IR_Cardelli89(x, Rv)
    
    extinction_factor = np.power(10, -0.4 * law * Rv * ebv)

    return extinction_factor

def dustCorr_IR_Cardelli89(wave, ebv, Rv=3.1, unit_wave='mu'):
    ## correct extinction using Cardelli et al 1989, ApJ 345, 245
    
    if ~np.isnan(ebv):
        #print ('(galactic extinction): ', ebv, Rv, unit_wave)
        if unit_wave == 'AA':
            wave = AA_to_micron(wave)
        elif unit_wave == 'mu':
            None
        else:
            raise NameError('wavelength unit not supported yet')

        x = 1. / wave

        law = extinctionLaw_IR_Cardelli89(x, Rv)

        extinction_factor = np.power(10, 0.4 * law * Rv * ebv)
    else:
        extinction_factor = np.full_like(wave, 1., dtype=float)
        print ('E(B-V)_gal provided is a NaN value. Not applying correction for galactic estinction')
    
    return extinction_factor
"""
