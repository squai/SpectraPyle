#!/usr/bin/env python
"""
Test script for verifying generic.py HDU scanning flexibility.
Creates synthetic FITS files with different HDU layouts and tests readSpec.
"""

import numpy as np
from astropy.io import fits
from astropy.table import Table
from pathlib import Path
import tempfile
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "project_root" / "src"))

from spectraPyle.instruments.generic import readSpec

def create_standard_layout(filepath):
    """HDU[0] has 1-D flux data (image mode, standard layout)."""
    naxis1 = 1000
    flux = np.random.rand(naxis1)

    primary = fits.PrimaryHDU(data=flux)
    # WCS keywords added after data
    primary.header['CRVAL1'] = 4000.0  # Rest wavelength
    primary.header['CDELT1'] = 1.0     # Angstrom per pixel
    primary.header['CRPIX1'] = 1.0     # Reference pixel

    hdul = fits.HDUList([primary])
    hdul.writeto(filepath, overwrite=True, output_verify='silentfix')
    print(f"✓ Standard layout: HDU[0] has 1-D flux")


def create_mef_table(filepath):
    """HDU[0] empty, HDU[1] is BinTable with flux+wave (MEF standard)."""
    naxis1 = 1000
    wavelength = np.linspace(4000, 5000, naxis1)
    flux = np.random.rand(naxis1)
    error = np.abs(np.random.randn(naxis1)) * 0.1

    # Empty primary
    primary = fits.PrimaryHDU()
    # WCS in header for fallback
    primary.header['CRVAL1'] = 4000.0
    primary.header['CDELT1'] = 1.0
    primary.header['CRPIX1'] = 1.0
    primary.header['NAXIS1'] = naxis1

    # Binary table at HDU[1]
    col_w = fits.Column(name='wavelength', format='E', array=wavelength)
    col_f = fits.Column(name='flux', format='E', array=flux)
    col_e = fits.Column(name='error', format='E', array=error)
    cols = fits.ColDefs([col_w, col_f, col_e])
    table = fits.BinTableHDU.from_columns(cols)

    hdul = fits.HDUList([primary, table])
    hdul.writeto(filepath, overwrite=True, output_verify='silentfix')
    print(f"✓ MEF table: HDU[0] void, HDU[1] BinTable with flux+wave")


def create_late_extension_image(filepath):
    """HDU[0] empty, HDU[1] empty, HDU[2] has 1-D flux (image mode)."""
    naxis1 = 1000
    flux = np.random.rand(naxis1)

    # Empty primary
    primary = fits.PrimaryHDU()
    # WCS for fallback
    primary.header['CRVAL1'] = 4000.0
    primary.header['CDELT1'] = 1.0
    primary.header['CRPIX1'] = 1.0
    primary.header['NAXIS1'] = naxis1

    # Empty extension at HDU[1]
    empty = fits.ImageHDU(data=np.array([]))

    # Data at HDU[2]
    image = fits.ImageHDU(data=flux)

    hdul = fits.HDUList([primary, empty, image])
    hdul.writeto(filepath, overwrite=True, output_verify='silentfix')
    print(f"✓ Late extension: HDU[0] void, HDU[1] void, HDU[2] has 1-D flux")


def create_wcs_in_extension_header(filepath):
    """HDU[0] empty header, HDU[1] BinTable with WCS in its own header."""
    naxis1 = 1000
    wavelength = np.linspace(4000, 5000, naxis1)
    flux = np.random.rand(naxis1)
    error = np.abs(np.random.randn(naxis1)) * 0.1

    # Empty primary (no WCS)
    primary = fits.PrimaryHDU()

    # Binary table at HDU[1] with WCS in its header
    col_w = fits.Column(name='wavelength', format='E', array=wavelength)
    col_f = fits.Column(name='flux', format='E', array=flux)
    col_e = fits.Column(name='error', format='E', array=error)
    cols = fits.ColDefs([col_w, col_f, col_e])
    table = fits.BinTableHDU.from_columns(cols)

    # Add WCS to extension header (not primary)
    table.header['CRVAL1'] = 4000.0
    table.header['CDELT1'] = 1.0
    table.header['CRPIX1'] = 1.0
    table.header['NAXIS1'] = naxis1

    hdul = fits.HDUList([primary, table])
    hdul.writeto(filepath, overwrite=True, output_verify='silentfix')
    print(f"✓ WCS in extension: HDU[0] empty, HDU[1] BinTable with WCS in its header")


def create_all_hdu_empty(filepath):
    """All HDUs empty (should raise ValueError)."""
    primary = fits.PrimaryHDU()
    empty = fits.ImageHDU(data=np.array([]))
    hdul = fits.HDUList([primary, empty])
    hdul.writeto(filepath, overwrite=True, output_verify='silentfix')
    print(f"✓ All empty: HDU[0] and HDU[1] both void (expect ValueError)")


def test_layout(name, create_func):
    """Test a single FITS layout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "test.fits"
        create_func(filepath)

        # Minimal config
        config = {
            'spectra_mode': 'individual fits',
            'grism_io': {
                'default': {
                    'spectra_dir': tmpdir,
                    'spectra_datafile': None,
                }
            },
            'spectrum_edges': None,
        }

        try:
            lbd, flux, error = readSpec(config, 'test', 'default')

            # Sanity checks
            if len(lbd) == 0 or len(flux) == 0:
                print(f"  ✗ {name}: Empty arrays returned!")
                return False
            if np.all(np.isnan(flux)):
                print(f"  ✗ {name}: All flux is NaN!")
                return False
            if np.allclose(flux, 0):
                print(f"  ✗ {name}: All flux is zero!")
                return False

            print(f"  ✓ {name}: lbd={len(lbd)}, flux={flux.shape}, error={error.shape}, flux_mean={np.nanmean(flux):.3f}")
            return True

        except ValueError as e:
            if "All empty" in name:
                print(f"  ✓ {name}: Correctly raised ValueError: {str(e)[:60]}...")
                return True
            else:
                print(f"  ✗ {name}: Unexpected ValueError: {e}")
                return False
        except Exception as e:
            print(f"  ✗ {name}: Unexpected error: {type(e).__name__}: {e}")
            return False


if __name__ == '__main__':
    print("=" * 70)
    print("Testing generic.py HDU flexibility")
    print("=" * 70)

    tests = [
        ("Standard layout", create_standard_layout),
        ("MEF table", create_mef_table),
        ("Late extension image", create_late_extension_image),
        ("WCS in extension header", create_wcs_in_extension_header),
        ("All empty", create_all_hdu_empty),
    ]

    results = []
    for name, create_func in tests:
        print(f"\n{name}:")
        result = test_layout(name, create_func)
        results.append((name, result))

    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    all_pass = all(r for _, r in results)
    sys.exit(0 if all_pass else 1)
