from __future__ import division, print_function

import copy
from decimal import Decimal  # histograms

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import scipy as sp
from scipy.stats import norm
from tqdm import tqdm_notebook as tqdm

import corner
import emperors_library as emplib
import emperors_mirror as empmir


class CourtPainter:

    markers = ['o', 'v', '^', '>', '<', '8', 's', 'p', 'H', 'D', '*', 'd']
    error_kwargs = {'lw': 1.75, 'zorder': 0}
    chain_titles = [
        'Amplitude', 'Period', 'Longitude', 'Phase', 'Eccentricity',
        'Acceleration', 'Jitter', 'Offset'
    ]
    chain_units = [
        r' $[\frac{m}{s}]$', ' [Days]', r' $[rad]$', r' $[rads]$', '',
        r' $[\frac{m}{s^2}]$', r' $[\frac{m}{s}]$', ' r$[\frac{m}{s}]$'
    ]

    def __init__(self, setup, kplanets, working_dir, pdf, png):
        self.ntemps, self.nwalkers, self.nsteps = setup
        self.kplanets = kplanets
        self.working_dir = working_dir
        self.pdf = pdf
        self.png = png
        self.nsamp = 100

        # Read chains, posteriors and data for plotting.
        self.chains = emplib.read_chains(working_dir + 'chains.pkl')
        self.cold = self.chains[0]
        self.posteriors = emplib.read_posteriors(
            working_dir + 'posteriors.pkl')
        self.all_rv = emplib.read_rv_data(working_dir + 'rv_data.pkl')
        self.time, self.rv, self.err, self.ins = self.all_rv

        self.nins = len(sp.unique(self.ins))
        self.ndim = 1 + 5 * kplanets + self.nins * 2

        # Setup plots.
        self.read_config()
        self.time_cb = copy.deepcopy(self.time) - 2450000

        # Setup RV models.
        self.create_models()
        pass

    def create_models(self):
        # Calculate median model.
        time_m = sp.linspace(self.time.min() - 10,
                             self.time.max() + 10, 10000)
        rv_models = []  # Models sample by sample.
        rv_models_p = []
        rv_m = []  # Median model.
        for k in range(self.kplanets):
            params = self.__get_median_params(k)
            rv_m.append(empmir.mini_RV_model(params, time_m))
            rv_model = []
            rv_phased = []
            desc = 'Sampling models for planet {}'.format(k + 1)
            for i in tqdm(range(self.nsamp), desc=desc):
                iparams = self.__get_params(k, i)  # get params for sample i
                model = empmir.mini_RV_model(iparams, time_m)
                rv_model.append(model)
                # Phasefold models.
                _, model_p, _ = emplib.phasefold(
                    time_m, model, time_m, iparams[0]
                )
                rv_phased.append(model_p)
            rv_models.append(sp.array(rv_model))
            rv_models_p.append(sp.array(rv_phased))
        self.time_m = time_m
        self.rv_models = sp.array(rv_models)
        self.rv_models_p = sp.array(rv_models_p)
        self.rv_m = sp.array(rv_m)
        pass

    def __get_median_params(self, kplanet):
        """Retrieve best model parameters."""
        period = sp.median(self.cold[:, 5 * kplanet])
        amplitude = sp.median(self.cold[:, 5 * kplanet + 1])
        phase = sp.median(self.cold[:, 5 * kplanet + 2])
        eccentricity = sp.median(self.cold[:, 5 * kplanet + 3])
        longitude = sp.median(self.cold[:, 5 * kplanet + 4])
        params = (period, amplitude, phase, eccentricity, longitude)
        return params

    def __get_params(self, kplanet, i):
        """Retrieve best model parameters."""
        period = self.cold[i, 5 * kplanet]
        amplitude = self.cold[i, 5 * kplanet + 1]
        phase = self.cold[i, 5 * kplanet + 2]
        eccentricity = self.cold[i, 5 * kplanet + 3]
        longitude = self.cold[i, 5 * kplanet + 4]
        params = (period, amplitude, phase, eccentricity, longitude)
        return params

    def rv_residuals(self):
        """Calculate model residuals."""
        model = 0.
        for k in range(self.kplanets):
            params = self.__get_median_params(k)
            model += empmir.mini_RV_model(params, self.time)
        residuals = self.rv - model
        return residuals

    def clean_rvs(self):
        """Clean radial-velocities by adding the offset and jitter."""
        instrumental = self.cold[:, -2 * self.nins:]
        rv0 = copy.deepcopy(self.rv)
        err0 = copy.deepcopy(self.err)
        acc = sp.median(self.cold[:, -2 * self.nins - 1])
        for i in range(self.nins):
            jitter = sp.median(instrumental[:, i])
            offset = sp.median(instrumental[:, i + 1])
            ins = self.ins == i
            # Assume linear acceleration for now.
            rv0[ins] -= offset + acc
            err0[ins] = sp.sqrt(err0[ins] ** 2 + jitter ** 2)
        self.rv0 = rv0
        self.err0 = err0
        pass

    def paint_fold(self):
        """Create phasefold plot."""
        print('\nPAINTING PHASE FOLDS.')
        # Get globbal max and min for plots
        minx, maxx = self.time.min(), self.time.max()
        cmin, cmax = self.time_cb.min(), self.time_cb.max()

        for k in tqdm(range(self.kplanets)):
            params = self.__get_median_params(k)

            fig = plt.figure(figsize=self.phase_figsize)
            gs = gridspec.GridSpec(3, 4)
            ax = fig.add_subplot(gs[:2, :])
            ax_r = fig.add_subplot(gs[-1, :])
            cbar_ax = fig.add_axes([.85, .125, .015, .755])
            fig.subplots_adjust(right=.84, hspace=0)

            for i in range(self.nins):  # plot per instrument.
                ins = self.ins == i
                t_p, rv_p, err_p = emplib.phasefold(
                    self.time[ins], self.rv[ins], self.err[ins], params[0]
                )
                _, res_p, _p = emplib.phasefold(
                    self.time[ins], self.rv_residuals()[ins], self.err[ins],
                    params[0]
                )
                # phasefold plot.
                ax.errorbar(
                    t_p, rv_p, yerr=err_p, linestyle='', marker=None,
                    alpha=.75, ecolor=self.error_color, **self.error_kwargs
                )
                im = ax.scatter(
                    t_p, rv_p, marker=self.markers[i], edgecolors='k',
                    s=self.phase_size, c=self.time_cb[ins],
                    cmap=self.phase_cmap
                )
                im.set_clim(cmin, cmax)
                ax_r.errorbar(
                    t_p, res_p, yerr=err_p, linestyle='', marker=None,
                    ecolor=self.error_color, **self.error_kwargs
                )
                im_r = ax_r.scatter(
                    t_p, res_p, marker=self.markers[i], edgecolors='k',
                    s=self.phase_size, c=self.time_cb[ins],
                    cmap=self.phase_cmap
                )
                im_r.set_clim(cmin, cmax)
            fig.colorbar(
                im, cax=cbar_ax).set_label(
                'JD - 2450000', rotation=270, labelpad=self.cbar_labelpad,
                fontsize=self.label_fontsize, fontname=self.fontname
            )

            time_m_p, rv_m_p, _ = emplib.phasefold(
                self.time_m, self.rv_m[k][:], sp.zeros(10000), params[0])

            # Plot best model.
            ax.plot(time_m_p, rv_m_p, '-k', linewidth=2)
            # Plot models CI.
            # First we caculate a bunch of models.

            alphas = [.99, .95, .68]  # 3, 2, and 1 sigma
            for s in alphas:
                low_m = []
                up_m = []
                for it in range(len(self.time_m)):
                    _, low, up = emplib.credibility_interval(
                        self.rv_models_p[k][:, it], s
                    )
                    low_m.append(low)
                    up_m.append(up)

                ax.fill_between(
                    time_m_p, low_m, up_m, color=self.CI_color, alpha=.25
                )

            # A line to guide the eye.
            ax_r.axhline(0, color='k', linestyle='--', linewidth=2, zorder=0)

            # Labels and tick stuff.
            ax.set_ylabel(
                r'Radial Velocity (m s$^{-1}$)', fontsize=self.label_fontsize,
                fontname=self.fontname
            )
            ax_r.set_ylabel(
                'Residuals', fontsize=self.label_fontsize,
                fontname=self.fontname
            )
            ax_r.set_xlabel(
                'Phase', fontsize=self.label_fontsize, fontname=self.fontname
            )

            ax_r.get_yticklabels()[-1].set_visible(False)
            ax_r.minorticks_on()
            ax.set_xticks([])
            ax.tick_params(
                axis='both', which='major',
                labelsize=self.tick_labelsize
            )
            ax_r.tick_params(
                axis='both', which='major',
                labelsize=self.tick_labelsize
            )
            for tick in ax.get_yticklabels():
                tick.set_fontname(self.fontname)
            for tick in ax_r.get_yticklabels():
                tick.set_fontname(self.fontname)
            for tick in ax_r.get_xticklabels():
                tick.set_fontname(self.fontname)
            for tick in cbar_ax.get_yticklabels():
                tick.set_fontname(self.fontname)
            cbar_ax.tick_params(labelsize=self.tick_labelsize)

            ax.set_xlim(-.01, 1.01)
            ax_r.set_xlim(-.01, 1.01)
            if self.pdf:
                fig.savefig(self.working_dir + 'phase_fold_' +
                            str(k + 1) + '.pdf', bbox_inches='tight')
            if self.png:
                fig.savefig(self.working_dir + 'phase_fold_' +
                            str(k + 1) + '.png', bbox_inches='tight')

        pass

    def paint_timeseries(self):
        """Create timeseries plot."""
        print('\nPAINTING TIMESERIES.')
        # Get globbal max and min for plots
        minx, maxx = self.time.min(), self.time.max()
        cmin, cmax = self.time_cb.min(), self.time_cb.max()

        for k in tqdm(range(self.kplanets)):
            params = self.__get_median_params(k)

            fig = plt.figure(figsize=self.full_figsize)
            gs = gridspec.GridSpec(3, 4)
            ax = fig.add_subplot(gs[:2, :])
            ax_r = fig.add_subplot(gs[-1, :])
            cbar_ax = fig.add_axes([.85, .125, .015, .755])
            fig.subplots_adjust(right=.84, hspace=0)

            for i in range(self.nins):
                ins = self.ins == i

                ax.errorbar(
                    self.time[ins] - 2450000, self.rv[ins], yerr=self.err[ins],
                    linestyle='', marker=None, ecolor=self.error_color,
                    **self.error_kwargs
                )
                im = ax.scatter(
                    self.time[ins] - 2450000, self.rv[ins],
                    marker=self.markers[i], edgecolors='k', s=self.full_size,
                    c=self.time_cb[ins], cmap=self.full_cmap
                )
                im.set_clim(cmin, cmax)

                # Get residuals.
                res = self.rv_residuals()[ins]

                ax_r.errorbar(
                    self.time[ins] - 2450000, res, yerr=self.err[ins],
                    linestyle='', marker=None, ecolor=self.error_color,
                    **self.error_kwargs
                )
                im_r = ax_r.scatter(
                    self.time[ins] - 2450000, res, marker=self.markers[i],
                    edgecolors='k', s=self.full_size, c=self.time_cb[ins],
                    cmap=self.full_cmap
                )

                im_r.set_clim(cmin, cmax)
            fig.colorbar(
                im, cax=cbar_ax).set_label(
                'JD - 2450000', rotation=270, labelpad=self.cbar_labelpad,
                fontsize=self.label_fontsize, fontname=self.fontname
            )
            time_m = sp.linspace(self.time.min() - 10,
                                 self.time.max() + 10, 10000)
            time_m -= 2450000
            rv_m = empmir.mini_RV_model(params, time_m)

            # Plot best model.
            ax.plot(time_m, rv_m, '-k', linewidth=2)
            # Plot models CI.
            cred_intervals = [.99, .95, .68]  # 3, 2, and 1 sigma
            for s in cred_intervals:
                params_lo, params_up = self.__get_CI_params(k, s)
                # Calculate new models.
                rv_m_lo = empmir.mini_RV_model(params_lo, time_m)
                rv_m_up = empmir.mini_RV_model(params_up, time_m)

                ax.fill_between(
                    time_m, rv_m_lo, rv_m_up, color=self.CI_color, alpha=.25
                )

            # A line to guide the eye.
            ax_r.axhline(0, color='k', linestyle='--', linewidth=2, zorder=0)

            # Labels and tick stuff.
            ax.set_ylabel(
                r'Radial Velocity (m s$^{-1}$)', fontsize=self.label_fontsize,
                fontname=self.fontname
            )
            ax_r.set_ylabel(
                'Residuals', fontsize=self.label_fontsize,
                fontname=self.fontname
            )
            ax_r.set_xlabel(
                'Time (JD - 2450000)', fontsize=self.label_fontsize,
                fontname=self.fontname
            )

            ax_r.get_yticklabels()[-1].set_visible(False)
            ax_r.minorticks_on()
            ax.set_xticks([])
            ax.tick_params(
                axis='both', which='major',
                labelsize=self.tick_labelsize
            )
            ax_r.tick_params(
                axis='both', which='major',
                labelsize=self.tick_labelsize
            )
            for tick in ax.get_yticklabels():
                tick.set_fontname(self.fontname)
            for tick in ax_r.get_yticklabels():
                tick.set_fontname(self.fontname)
            for tick in ax_r.get_xticklabels():
                tick.set_fontname(self.fontname)
            for tick in cbar_ax.get_yticklabels():
                tick.set_fontname(self.fontname)
            cbar_ax.tick_params(labelsize=self.tick_labelsize)

            ax.set_xlim(time_m.min() - 25, time_m.max() + 25)
            ax_r.set_xlim(time_m.min() - 25, time_m.max() + 25)
            if self.pdf:
                fig.savefig(self.working_dir + 'timeseries_' +
                            str(k + 1) + '.pdf', bbox_inches='tight')
            if self.png:
                fig.savefig(self.working_dir + 'timeseries_' +
                            str(k + 1) + '.png', bbox_inches='tight')
        pass

    def paint_chains(self):
        """Create traceplots or chain plots for each temperature."""
        for t in range(self.ntemps):
            print('\nPAINTING CHAINS FOR TEMPERATURE', end=' ')
            print(t)
            chain = self.chains[t]
            for i in tqdm(range(self.ndim)):
                fig, ax = plt.subplots(figsize=self.chain_figsize)
                pass
        pass

    def read_config(self):
        """Read configuration file for plotting."""
        # TODO: implement.
        self.phase_figsize = (20, 10)
        self.full_figsize = (20, 10)
        self.chain_figsize = (12, 7)
        self.post_figsize = (12, 7)
        self.phase_cmap = 'cool_r'
        self.full_cmap = 'cool_r'
        self.phase_size = 100
        self.full_size = 100
        self.label_fontsize = 22
        self.CI_color = 'darkturquoise'
        self.error_color = 'k'
        self.fontname = 'serif'
        self.tick_labelsize = 20
        self.cbar_labelpad = 30
        pass
