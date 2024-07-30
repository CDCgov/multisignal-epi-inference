# numpydoc ignore=GL08
import jax.numpy as jnp
import numpyro.distributions as dist

# import pyrenew.transformation as transformation
from pyrenew.deterministic import DeterministicVariable
from pyrenew.latent import (
    InfectionInitializationProcess,
    InfectionsWithFeedback,
    InitializeInfectionsExponentialGrowth,
)
from pyrenew.metaclass import (  # TransformedRandomVariable,
    DistributionalRV,
    Model,
)
from pyrenew.process import RtWeeklyDiffProcess


class hosp_only_ww_model(Model):  # numpydoc ignore=GL08
    def __init__(
        self,
        state_pop,
        i0_over_n_rv,
        initialization_rate_rv,
        log_r_mu_intercept_rv,
        autoreg_rt_rv,  # ar process
        eta_sd_rv,  # sd of random walk for ar process
        generation_interval_pmf_rv,
        infection_feedback_strength_rv,
        infection_feedback_pmf_rv,
        p_hosp_mean_rv,
        p_hosp_w_sd_rv,
        autoreg_p_hosp_rv,
        n_initialization_points,
        n_timepoints,
    ):  # numpydoc ignore=GL08
        self.infection_initialization_process = InfectionInitializationProcess(
            "I0_initialization",
            # TransformedRandomVariable(
            #     "i0",
            #     i0_over_n_rv,
            #     transforms=transformation.AffineTransform(
            #         loc=0, scale=state_pop
            #     ),
            # ),
            i0_over_n_rv,
            InitializeInfectionsExponentialGrowth(
                n_initialization_points,
                initialization_rate_rv,
                t_pre_init=0,
            ),
            t_unit=1,
        )

        self.inf_with_feedback_proc = InfectionsWithFeedback(
            infection_feedback_strength=infection_feedback_strength_rv,
            infection_feedback_pmf=infection_feedback_pmf_rv,
        )

        self.autoreg_rt_rv = autoreg_rt_rv
        self.eta_sd_rv = eta_sd_rv
        self.log_r_mu_intercept_rv = log_r_mu_intercept_rv
        self.generation_interval_pmf_rv = generation_interval_pmf_rv
        self.infection_feedback_pmf_rv = infection_feedback_pmf_rv
        self.p_hosp_mean_rv = p_hosp_mean_rv
        self.p_hosp_w_sd_rv = p_hosp_w_sd_rv
        self.autoreg_p_hosp_rv = autoreg_p_hosp_rv
        self.state_pop = state_pop
        self.n_timepoints = n_timepoints
        return None

    def validate(self):  # numpydoc ignore=GL08
        return None

    def sample(self):  # numpydoc ignore=GL08
        i0 = self.infection_initialization_process()

        eta_sd = self.eta_sd_rv()[0].value

        init_rate_of_change_rv = DistributionalRV(
            "init_rate_of_change", dist.Normal(0, eta_sd)
        )

        init_rate_of_change = init_rate_of_change_rv()[0].value
        log_r_mu_intercept = self.log_r_mu_intercept_rv()[0].value

        rt_proc = RtWeeklyDiffProcess(
            name="rtu_weekly_diff",
            offset=0,
            log_rt_prior=DeterministicVariable(
                name="log_rt",
                value=jnp.array(
                    [
                        log_r_mu_intercept,
                        log_r_mu_intercept + init_rate_of_change,
                    ]
                ),
            ),
            autoreg=self.autoreg_rt_rv,
            periodic_diff_sd=DeterministicVariable(
                name="periodic_diff_sd", value=jnp.array(eta_sd)
            ),
        )

        rtu = rt_proc.sample(duration=self.n_timepoints)
        generation_interval_pmf = self.generation_interval_pmf_rv()

        inf_with_feedback_proc_sample = self.inf_with_feedback_proc.sample(
            Rt=rtu[0].value,
            I0=i0[0].value,
            gen_int=generation_interval_pmf[0].value,
        )

        # infection_hosp_rate, *_ = self.infect_hosp_rate_rv(**kwargs)

        # infection_hosp_rate_t = infection_hosp_rate.value * latent_infections

        # (
        #     infection_to_admission_interval,
        #     *_,
        # ) = self.infection_to_admission_interval_rv(**kwargs)

        # latent_hospital_admissions = jnp.convolve(
        #     infection_hosp_rate_t,
        #     infection_to_admission_interval.value,
        #     mode="full",
        # )[: infection_hosp_rate_t.shape[0]]

        # # Applying the day of the week effect
        # latent_hospital_admissions = (
        #     latent_hospital_admissions
        #     * self.day_of_week_effect_rv(
        #         n_timepoints=latent_hospital_admissions.size, **kwargs
        #     )[0].value
        # )

        # # Applying reporting probability
        # latent_hospital_admissions = (
        #     latent_hospital_admissions
        #     * self.hosp_report_prob_rv(**kwargs)[0].value
        # )

        # numpyro.deterministic(
        #     "latent_hospital_admissions", latent_hospital_admissions
        # )

        return (
            i0,
            rtu,
            inf_with_feedback_proc_sample,
        )