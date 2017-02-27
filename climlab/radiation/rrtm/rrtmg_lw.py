from __future__ import division
import numpy as np
from climlab import constants as const
from climlab.radiation.radiation import _Radiation_LW
from utils import _prepare_general_arguments
from utils import _climlab_to_rrtm, _climlab_to_rrtm_sfc, _rrtm_to_climlab
from . import nbndlw, naerec
from _rrtmg_lw import driver as lwdriver


class RRTMG_LW(_Radiation_LW):
    def __init__(self,
            # GENERAL, used in both SW and LW
            icld = 1,    # Cloud overlap method, 0: Clear only, 1: Random, 2,  Maximum/random] 3: Maximum
            irng = 1,  # more monte carlo stuff
            idrv = 0,  # whether to also calculate the derivative of flux with respect to surface temp
            permuteseed =  300,
            inflglw  = 2,
            iceflglw = 1,
            liqflglw = 1,
            tauc = 0.,  # in-cloud optical depth
            tauaer = 0.,   # Aerosol optical depth at mid-point of LW spectral bands
            **kwargs):
        super(RRTMG_LW, self).__init__(**kwargs)
        #  define INPUTS
        self.add_input('icld', icld)
        self.add_input('irng', irng)
        self.add_input('idrv', idrv)
        self.add_input('permuteseed', permuteseed)
        self.add_input('inflglw', inflglw)
        self.add_input('iceflglw', iceflglw)
        self.add_input('liqflglw', liqflglw)
        self.add_input('tauc', tauc)
        self.add_input('tauaer', tauaer)

    def _prepare_lw_arguments(self):
        #  scalar integer arguments
        icld = self.icld
        irng = self.irng
        idrv = self.idrv
        permuteseed = self.permuteseed
        inflglw = self.inflglw
        iceflglw = self.iceflglw
        liqflglw = self.liqflglw

        (ncol, nlay, play, plev, tlay, tlev, tsfc,
        h2ovmr, o3vmr, co2vmr, ch4vmr, n2ovmr, o2vmr, cfc11vmr,
        cfc12vmr, cfc12vmr, cfc22vmr, ccl4vmr,
        cldfrac, ciwp, clwp, relq, reic) = _prepare_general_arguments(self)
        # surface emissivity
        emis = self.emissivity * np.ones((ncol,nbndlw))
        #  These arrays have an extra dimension for number of bands
        # in-cloud optical depth [nbndlw,ncol,nlay]
        tauc = _climlab_to_rrtm(self.tauc * np.ones_like(self.Tatm))
        #  broadcast to get [nbndlw,ncol,nlay]
        tauc = tauc * np.ones([nbndlw,ncol,nlay])
        # Aerosol optical depth at mid-point of LW spectral bands [ncol,nlay,nbndlw]
        tauaer = _climlab_to_rrtm(self.tauaer * np.ones_like(self.Tatm))
        #  broadcast and transpose to get [ncol,nlay,nbndlw]
        tauaer = np.transpose(tauaer * np.ones([nbndlw,ncol,nlay]), (1,2,0))
        args = [ncol, nlay, icld, permuteseed, irng, idrv, const.cp,
                play, plev, tlay, tlev, tsfc,
                h2ovmr, o3vmr, co2vmr, ch4vmr, n2ovmr, o2vmr,
                cfc11vmr, cfc12vmr, cfc22vmr, ccl4vmr, emis,
                inflglw, iceflglw, liqflglw,
                cldfrac, ciwp, clwp, reic, relq, tauc, tauaer,]
        return args

    def _compute_heating_rates(self):
        '''Prepare arguments and call the RRTGM_LW driver to calculate
        radiative fluxes and heating rates'''
        args = self._prepare_lw_arguments()
        #  Call the RRTM code!
        uflx, dflx, hr, uflxc, dflxc, hrc, duflx_dt, duflxc_dt = lwdriver(*args)
        #  Output is all (ncol,nlay+1) or (ncol,nlay)
        self.LW_flux_up = _rrtm_to_climlab(uflx)
        self.LW_flux_down = _rrtm_to_climlab(dflx)
        self.LW_flux_up_clr = _rrtm_to_climlab(uflxc)
        self.LW_flux_down_clr = _rrtm_to_climlab(dflxc)
        #  Compute quantities derived from fluxes, including OLR
        self._compute_LW_flux_diagnostics()
        #  calculate heating rates from flux divergence
        LWheating_Wm2 = np.diff(self.LW_flux_net, axis=-1)
        LWheating_clr_Wm2 = np.diff(self.LW_flux_net_clr, axis=-1)
        self.heating_rate['Ts'] = -self.LW_flux_net[..., -1, np.newaxis]
        self.heating_rate['Tatm'] = LWheating_Wm2
        #  Convert to K / day
        Catm = self.Tatm.domain.heat_capacity
        self.TdotLW = LWheating_Wm2 / Catm * const.seconds_per_day
        self.TdotLW_clr = LWheating_clr_Wm2 / Catm * const.seconds_per_day
        #self.TdotLW = _rrtm_to_climlab(hr)  # heating rate in K/day
        #self.TdotLW_clr = _rrtm_to_climlab(hrc)  # clear-sky heating rate in K/day
