import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy import units as u
import importlib
import spectraPyle.physics.extinction as sext

def useSpec(
    config,
    specid,
    z,
    zStack,
    ebv_gal,
    cosmo,
    grism,
    metadata_name=None,
    hdu_indx=None
):
    """
    Load and transform a spectrum to the stacking redshift frame.

    This function reads a spectrum using either standard or metadata-driven
    I/O depending on `config['spectra_datafile']`, then applies optional
    Galactic extinction correction, air-to-vacuum conversion, and flux /
    luminosity conservation scaling to a target stacking redshift.

    Parameters
    ----------
    config : dict
        Configuration dictionary containing instrument and processing options.
    specid : str or int
        Spectrum identifier.
    z : float
        Source redshift.
    zStack : float
        Target stacking redshift.
    ebv_gal : float
        Galactic extinction E(B-V).
    cosmo : astropy.cosmology
        Cosmology object used for luminosity distance calculations.
    grism : str
        Grism identifier
    metadata_name : str, optional
        Metadata file path (required if spectra_datafile='metadata').
    hdu_indx : int, optional
        FITS HDU index (required if metadata mode).

    Returns
    -------
    tuple
        lbd_zStack : ndarray
            Wavelengths shifted to stacking redshift frame.
        flux_zStack : ndarray
            Flux scaled to stacking redshift frame.
        error_zStack : ndarray
            Flux error scaled to stacking redshift frame.

    Raises
    ------
    NameError
        If unsupported conservation mode is requested.
    ValueError
        If metadata mode is enabled but metadata inputs are missing.

    Notes
    -----
    Conservation modes:
    - 'luminosity' : converts flux preserving luminosity
    - 'flux'       : rescales flux by redshift factor only
    - 'none'       : leaves flux unchanged
    """

    conservation = config['conservation']
    condGalacticExtinction = config['galactic_extinction']
    condAirVac = config['air_vacuum']
    use_metadata = config.get('spectra_mode') == 'metadata path'

    inst = importlib.import_module(
        f"spectraPyle.instruments.{config['instrument_name']}"
    )

    # -------- Spectrum Reading --------
    if use_metadata:
        if metadata_name is None or hdu_indx is None:
            raise ValueError(
                "metadata_name and hdu_indx must be provided in metadata mode"
            )

        lbd, flux, error = inst.readSpec_metadata(
            config, specid, metadata_name, hdu_indx
        )
    else:
        lbd, flux, error = inst.readSpec(config, specid, grism)

    # -------- Galactic Extinction --------
    if condGalacticExtinction:
        flux *= sext.dustCorr_Gordon23(
            wave_A=lbd, ebv=ebv_gal, Rv=3.1
        )
    
    
    if config['z_type'] != 'observed_frame':
    
        # -------- Wavelength redshift frame conversion --------
        lbdRest = lbd / (1 + z)

        if condAirVac:
            lbdRest = lbdRest / (
                1.0
                + 2.735182E-4
                + 131.4182 / lbdRest**2
                + 2.76249E8 / lbdRest**4
            )

        lbd_zStack = lbdRest * (1 + zStack)

        # -------- Conservation Scaling --------
        if conservation == 'luminosity':

            ld_z = cosmo.luminosity_distance(z=z)

            if zStack != 0.0:
                ld_zStack = cosmo.luminosity_distance(z=zStack)

                scale = ((1 + z) * (ld_z**2)) / ((1 + zStack) * (ld_zStack**2))
                flux_zStack = flux * scale
                error_zStack = error * scale

            else:
                scale = (
                    config['units_scale_factor']
                    * (1 + z)
                    * 4 * np.pi
                    * (ld_z.to(u.cm).value ** 2)
                )

                flux_zStack = flux * scale
                error_zStack = error * scale

        elif conservation == 'flux':

            scale = (1 + z) / (1 + zStack)
            flux_zStack = flux * scale
            error_zStack = error * scale

        elif conservation == None:

            flux_zStack = flux
            error_zStack = error

        else:
            raise NameError(f"conservation: {conservation} NOT supported!")

        return lbd_zStack, flux_zStack, error_zStack
    
    else:
        return lbd, flux, error


'''
def useSpec(config, specid, z, zStack, ebv_gal, cosmo):
    
    conservation = config['conservation']
    condGalacticExtinction = config['galactic_extinction']
    condAirVac = config['air_vacuum']
    
    inst = importlib.import_module(f"spectraPyle.supported_instruments.{config['instrument_name']}")
    
    lbd, flux, error = inst.readSpec(config, specid)
    
    if condGalacticExtinction:
        #flux *= sext.dustCorr_IR_Cardelli89(wave=lbd, ebv=ebv_gal, Rv=3.1, unit_wave='AA')
        flux *= sext.dustCorr_Gordon23(wave_A=lbd, ebv=ebv_gal, Rv=3.1)

    lbdRest = lbd / (1 + z) ## rest frame wavelengths
    if condAirVac: lbdRest=lbdRest/(1.0+2.735182E-4+131.4182/lbdRest**2+2.76249E8/lbdRest**4)
    lbd_zStack = lbdRest * (1 + zStack)  ## wavelengths at the stacking redshift
    
    if conservation == 'luminosity':
        ld_z = cosmo.luminosity_distance(z=z)
        if zStack != 0.0:
            ld_zStack = cosmo.luminosity_distance(z=zStack)
            flux_zStack = flux * ((1+z)*(ld_z**2)) / ((1+zStack)*(ld_zStack**2))   ## flux at the target redshift [erg/s/cm-2/AA]
            error_zStack = error * ((1+z)*(ld_z**2)) / ((1+zStack)*(ld_zStack**2))   ## error at the target redshift [erg/s/cm-2/AA]
        else:
            flux_zStack = flux * config['units_scale_factor'] * (1 + z) * 4 * np.pi * ((ld_z.to(u.cm).value)**2) ## restframe luminosity [erg/s/AA]
            error_zStack = error * config['units_scale_factor'] * (1 + z) * 4 * np.pi * ((ld_z.to(u.cm).value)**2) ## restframe luminosity [erg/s/AA]

    elif conservation == 'flux':
        flux_zStack = flux * (1 + z) / (1 + zStack)  ## flux at the target redshift [erg/s/cm-2/AA]
        error_zStack = error * (1 + z) / (1 + zStack)  ## error at the target redshift [erg/s/cm-2/AA]
    
    elif conservation == 'none':
        flux_zStack = flux
        error_zStack = error
        
    else:
        raise NameError('conservation: '+conservation+' NOT supported!')

    return lbd_zStack, flux_zStack, error_zStack

def useSpec_metadata(config, specid, z, zStack, ebv_gal, metadata_name, hdu_indx, cosmo):
    
    conservation = config['conservation']
    condGalacticExtinction = config['galactic_extinction']
    condAirVac = config['air_vacuum']
    
    inst = importlib.import_module(f"spectraPyle.supported_instruments.{config['instrument_name']}")
    
    lbd, flux, error = inst.readSpec_metadata(config, specid, metadata_name, hdu_indx)
    
    if condGalacticExtinction:
        #flux *= sext.dustCorr_IR_Cardelli89(wave=lbd, ebv=ebv_gal, Rv=3.1, unit_wave='AA')
        flux *= sext.dustCorr_Gordon23(wave_A=lbd, ebv=ebv_gal, Rv=3.1)

    lbdRest = lbd / (1 + z) ## rest frame wavelengths
    if condAirVac: lbdRest=lbdRest/(1.0+2.735182E-4+131.4182/lbdRest**2+2.76249E8/lbdRest**4)
    lbd_zStack = lbdRest * (1 + zStack)  ## wavelengths at the stacking redshift

    if conservation == 'luminosity':
        ld_z = cosmo.luminosity_distance(z=z)
        if zStack != 0.0:
            ld_zStack = cosmo.luminosity_distance(z=zStack)
            flux_zStack = flux * ((1+z)*(ld_z**2)) / ((1+zStack)*(ld_zStack**2))   ## flux at the target redshift [erg/s/cm-2/AA]
            error_zStack = error * ((1+z)*(ld_z**2)) / ((1+zStack)*(ld_zStack**2))   ## error at the target redshift [erg/s/cm-2/AA]
        else:
            flux_zStack = flux * config['units_scale_factor'] * (1 + z) * 4 * np.pi * ((ld_z.to(u.cm).value)**2) ## restframe luminosity [erg/s/AA]
            error_zStack = error * config['units_scale_factor'] * (1 + z) * 4 * np.pi * ((ld_z.to(u.cm).value)**2) ## restframe luminosity [erg/s/AA]

    elif conservation == 'flux':
        flux_zStack = flux * (1 + z) / (1 + zStack)  ## flux at the target redshift [erg/s/cm-2/AA]
        error_zStack = error * (1 + z) / (1 + zStack)  ## error at the target redshift [erg/s/cm-2/AA]
    
    elif conservation == 'none':
        flux_zStack = flux
        error_zStack = error

    else:
        raise NameError('conservation: '+conservation+' NOT supported!')
    
    return lbd_zStack, flux_zStack, error_zStack
'''
