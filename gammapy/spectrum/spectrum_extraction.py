# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import absolute_import, division, print_function, unicode_literals
import logging
import os
import numpy as np
import astropy.units as u
from astropy.units import Quantity
from ..extern.pathlib import Path
from ..extern.regions import CircleSkyRegion
from ..utils.scripts import make_path
from ..data import Target
from ..background import reflected_regions_background_estimate
from . import (
    PHACountsSpectrum,
    SpectrumObservation,
    SpectrumObservationList,
)
from ..data import Target
from ..extern.bunch import Bunch
from ..extern.pathlib import Path
from ..extern.regions.shapes import CircleSkyRegion
from ..image import ExclusionMask
from ..irf import EffectiveAreaTable, EnergyDispersion
from ..utils.energy import EnergyBounds, Energy
from ..utils.scripts import make_path, write_yaml

__all__ = [
    'SpectrumExtraction',
]

log = logging.getLogger(__name__)


class SpectrumExtraction(object):
    """Class for creating input data to 1D spectrum fitting

    This class takes a `~gammapy.data.Target` as input and creates 1D counts on
    and off counts vectors as well as an effective area vector and an energy
    dispersion matrix.  For more info see :ref:`spectral_fitting`.

    For point sources analyzed with 'full containement' IRFs, a correction for
    PSF leakage out of the circular ON region can be applied.

    Parameters
    ----------
    target : `~gammapy.data.Target` or `~regions.SkyRegion`
        Observation target
    obs: `~gammapy.data.ObservationList`
        Observations to process
    background : `~gammapy.data.BackgroundEstimate` or dict
        Background estimate or dict of parameters
    e_reco : `~astropy.units.Quantity`, optional
        Reconstructed energy binning
    containment_correction : bool
        Apply containment correction for point sources and circular ON regions.

    Examples
    --------
    """
    OGIP_FOLDER = 'ogip_data'
    """Folder that will contain the output ogip data"""

    def __init__(self, target, obs, background, e_reco=None, e_true=None,
                 containment_correction=False):

        if isinstance(target, CircleSkyRegion):
            target = Target(target)
        self.obs = obs
        self.background = background
        self.target = target
        # This is the 14 bpd setup used in HAP Fitspectrum
        self.e_reco = e_reco or np.logspace(-2, 2, 96) * u.TeV
        self.e_true = e_true or np.logspace(-2, 2.3, 250) * u.TeV
        self._observations = None
        self.containment_correction = containment_correction
        if self.containment_correction and not isinstance(target.on_region,
                                                          CircleSkyRegion):
            raise TypeError("Incorrect region type for containment correction."
                            " Should be CircleSkyRegion.")

    @property
    def observations(self):
        """List of `~gammapy.spectrum.SpectrumObservation`

        This list is generated via
        :func:`~gammapy.spectrum.spectrum_extraction.extract_spectrum`
        when the property is first called and the result is cached.
        """
        if self._observations is None:
            self.extract_spectrum()
        return self._observations

    def run(self, outdir=None):
        """Run all steps

        Extract spectrum, update observation table, filter observations,
        write results to disk.

        Parameters
        ----------
        outdir : Path, str
            directory to write results files to
        """
        cwd = Path.cwd()
        outdir = cwd if outdir is None else make_path(outdir)
        outdir.mkdir(exist_ok=True, parents=True)
        os.chdir(str(outdir))
        if not isinstance(self.background, list):
            log.info('Estimate background with config {}'.format(self.background))
            self.estimate_background()
        self.extract_spectrum()
        self.write()
        os.chdir(str(cwd))

    def estimate_background(self):
        method = self.background.pop('method')
        if method == 'reflected':
            exclusion = self.background.pop('exclusion', None)
            bkg = [reflected_regions_background_estimate(
                self.target.on_region,
                _.pointing_radec,
                exclusion,
                _.events) for _ in self.obs]
        else:
            raise NotImplementedError("Method: {}".format(method))
        self.background = bkg

    def filter_observations(self):
        """Filter observations by number of reflected regions"""
        n_min = self.bkg_method['n_min']
        obs = self.observations
        mask = obs.filter_by_reflected_regions(n_min)
        inv_mask = np.where([_ not in mask for _ in np.arange(len(mask + 1))])
        excl_obs = self.obs_table[inv_mask[0]]['OBS_ID'].data
        log.info('Excluding obs {} : Found less than {} reflected '
                 'region(s)'.format(excl_obs, n_min))
        self._observations = SpectrumObservationList(np.asarray(obs)[mask])
        self.obs_table = self.obs_table[mask]

    def extract_spectrum(self):
        """Extract 1D spectral information

        The result can be obtained via
        :func:`~gammapy.spectrum.spectrum_extraction.observations`
        """
        spectrum_observations = []
        if not isinstance(self.background, list):
            raise ValueError("Invalid background estimate: {}".format(self.background))
        for obs, bkg in zip(self.obs, self.background):
            log.info('Extracting spectrum for observation {}'.format(obs))
            idx = self.target.on_region.contains(obs.events.radec)
            on_events = obs.events[idx]

            counts_kwargs = dict(energy=self.e_reco,
                                 exposure=obs.observation_live_time_duration,
                                 obs_id=obs.obs_id,
                                 hi_threshold=obs.aeff.high_threshold,
                                 lo_threshold=obs.aeff.low_threshold)

            # We now add a number of optional keywords for the DataStoreObservation
            # We first check that the entry exists in the table
            try:
                counts_kwargs.update(tstart=obs.tstart)
            except KeyError:
                pass
            try:
                counts_kwargs.update(tstop=obs.tstop)
            except KeyError:
                pass
            try:
                counts_kwargs.update(muoneff=obs.muoneff)
            except KeyError:
                pass
            try:
                counts_kwargs.update(zen_pnt=obs.pointing_zen)
            except KeyError:
                pass

            on_vec = PHACountsSpectrum(backscal=bkg.a_on, **counts_kwargs)
            off_vec = PHACountsSpectrum(backscal=bkg.a_off, is_bkg=True,
                                        **counts_kwargs)

            on_vec.fill(on_events)
            off_vec.fill(bkg.off_events)

            offset = obs.pointing_radec.separation(self.target.on_region.center)
            arf = obs.aeff.to_effective_area_table(offset, energy=self.e_true)
            rmf = obs.edisp.to_energy_dispersion(offset,
                                                 e_reco=self.e_reco,
                                                 e_true=self.e_true)

            # If required, correct arf for psf leakage
            if self.containment_correction:
                # First need psf
                angles = np.linspace(0., 1.5, 150) * u.deg
                psf = obs.psf.to_table_psf(offset, angles)

                center_energies = arf.energy.nodes
                for index, energy in enumerate(center_energies):
                    try:
                        correction = psf.integral(energy,
                                                  0. * u.deg,
                                                  self.target.on_region.radius)
                    except:
                        correction = np.nan

                    arf.data[index] = arf.data[index] * correction

            temp = SpectrumObservation(on_vec, off_vec, arf, rmf)
            spectrum_observations.append(temp)

        self._observations = SpectrumObservationList(spectrum_observations)

    def define_energy_threshold(self, method_lo_threshold='area_max', **kwargs):
        """Set energy threshold
        
        Set the high and low energy threshold for each observation based on a
        choosen method. 
        
        Available methods for setting the low energy threshold

        * area_max : Set energy threshold at x percent of the maximum effective
                     area (x given as kwargs['percent'])

        Available methods for setting the high energy threshold

        * TBD

        Parameters
        ----------
        method_lo_threshold : {'area_max'}
            method for defining the low energy threshold
        """
        # TODO: define method for the high energy threshold

        # It is important to update the low and high threshold for ON and OFF
        # vector, otherwise Sherpa will not understand the files
        for obs in self.observations:
            if method_lo_threshold == 'area_max':
                aeff_thres = kwargs['percent'] / 100 * obs.aeff.max_area
                thres = obs.aeff.find_energy(aeff_thres) 
                obs.on_vector.lo_threshold = thres
                obs.off_vector.lo_threshold = thres
            else:
                raise ValueError('Undefine method for low threshold: {}'.format(
                    method_lo_threshold))

    def write(self):
        """Write results to disk"""
        self.observations.write(self.OGIP_FOLDER)
        # TODO : add more debug plots etc. here
