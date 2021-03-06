.. note::

    A new set of map and cube classes is being developed in `gammapy.maps`
    and long-term will replace the existing `gammapy.image.SkyImage` and
    `gammapy.cube.SkyCube` classes. Please consider trying out `gammapy.maps`
    and changing your scripts to use those new classes. See :ref:`maps`.

.. _cube:

***************************
3D cube analysis (``cube``)
***************************

.. currentmodule:: gammapy.cube

Introduction
============

The `~gammapy.cube` module bundles functionality for combined spatial and
spectral analysis (cube style analysis) of gamma-ray sources.

Some information on cube style analysis in gamma-ray astronomy can be found here:

* `Cube style analysis for Cherenkov telescope data`_
* `Classical analysis in VHE gamma-ray astronomy`_

.. _Cube style analysis for Cherenkov telescope data: https://github.com/gammapy/PyGamma15/blob/gh-pages/talks/analysis-cube/2015-11-16_PyGamma15_Eger_Cube_Analysis.pdf
.. _Classical analysis in VHE gamma-ray astronomy: https://github.com/gammapy/PyGamma15/blob/gh-pages/talks/analysis-classical/2015-11-16_PyGamma15_Terrier_Classical_Analysis.pdf


Getting Started
===============

Use `~gammapy.cube.SkyCube` to read a Fermi-LAT diffuse model cube::

    >>> from gammapy.cube import SkyCube
    >>> filename = '$GAMMAPY_EXTRA/test_datasets/unbundled/fermi/gll_iem_v02_cutout.fits'
    >>> cube = SkyCube.read(filename, format='fermi-background')
    >>> print(cube)
    Sky cube flux with shape=(30, 21, 61) and unit=1 / (cm2 MeV s sr):
     n_lon:       61  type_lon:    GLON-CAR         unit_lon:    deg
     n_lat:       21  type_lat:    GLAT-CAR         unit_lat:    deg
     n_energy:    30  unit_energy: MeV

Use the cube methods to do computations::

    import astropy.units as u
    emin, emax = [1, 10] * u.GeV
    image = cube.sky_image_integral(emin=emin, emax=emax)
    image.show('ds9')

Using `gammapy.cube`
=====================

Gammapy tutorial notebooks that show examples using ``gammapy.cube``:

* :gp-extra-notebook:`analysis_3d`
* :gp-extra-notebook:`simulate_3d`
* :gp-extra-notebook:`data_fermi_lat`

Reference/API
=============

.. automodapi:: gammapy.cube
    :no-inheritance-diagram:
    :include-all-objects:
