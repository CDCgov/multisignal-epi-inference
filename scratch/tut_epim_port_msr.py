"""
Porting `cfa-forecast-renewal-epidemia`
over to MSR. Validated on NHSN influenza
data from the 2023-24 season.
"""


import datetime as dt
import glob
import inspect
import logging
import os
from datetime import datetime

import jax
import jax.numpy as jnp
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import numpyro
import numpyro.distributions as dist
import polars as pl
import pyrenew.transformation as t
import toml
from jax.typing import ArrayLike
from matplotlib import font_manager as fm
from numpyro.infer.reparam import LocScaleReparam
from pyrenew.deterministic import DeterministicPMF
from pyrenew.latent import (
    InfectionInitializationProcess,
    InitializeInfectionsFromVec,
    logistic_susceptibility_adjustment,
)
from pyrenew.metaclass import (
    DistributionalRV,
    Model,
    RandomVariable,
    TransformedRandomVariable,
)
from pyrenew.observation import NegativeBinomialObservation
from pyrenew.process import SimpleRandomWalkProcess
from pyrenew.regression import GLMPrediction

FONT_PATH = "texgyreschola-regular.otf"
if os.path.exists(FONT_PATH):
    TITLE_FONT_PROP = fm.FontProperties(fname=FONT_PATH, size=17.5)
    LABEL_FONT_PROP = fm.FontProperties(fname=FONT_PATH, size=12.5)
    AXES_FONT_PROP = fm.FontProperties(fname=FONT_PATH, size=16.5)

# use first mplstyle file that appears, should one exist
if len(glob.glob("*mplstyle")) != 0:
    plt.style.use(glob.glob("*mplstyle")[0])

CURRENT_DATE = datetime.today().strftime("%Y-%m-%d")
CURRENT_DATE_EXTENDED = datetime.today().strftime("%Y-%m-%d_%H:%M:%S")

# set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Config:  # numpydoc ignore=GL08
    def __init__(self, config_dict):  # numpydoc ignore=GL08
        for key, value in config_dict.items():
            setattr(self, key, value)


def display_data(
    data: pl.DataFrame, n_row_count: int = 15, n_col_count: int = 5
) -> None:
    """
    Display the columns and rows of
    a polars dataframe.

    Parameters
    ----------
    data : pl.DataFrame
        A polars dataframe.
    n_row_count : int, optional
        How many rows to print.
        Defaults to 15.
    n_col_count : int, optional
        How many columns to print.
        Defaults to 15.

    Returns
    -------
    None
    """
    rows, cols = data.shape
    assert (
        1 <= n_col_count <= cols
    ), f"Must have reasonable column count; was {n_col_count}"
    assert (
        1 <= n_row_count <= rows
    ), f"Must have reasonable row count; was {n_row_count}"
    pl.Config.set_tbl_hide_dataframe_shape(True)
    pl.Config.set_tbl_formatting("ASCII_MARKDOWN")
    pl.Config.set_tbl_hide_column_data_types(True)
    with pl.Config(tbl_rows=n_row_count, tbl_cols=n_col_count):
        print(f"Dataset In Use For `cfaepim`:\n{data}\n")


def check_file_path_valid(file_path: str) -> None:
    """
    Checks if a file path is valid. Used to check
    the entered data and config paths.

    Parameters
    ----------
    file_path : str
        Path to the file (usually data or config).

    Returns
    -------
    None
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The path '{file_path}' does not exist.")
    if not os.path.isfile(file_path):
        raise IsADirectoryError(f"The path '{file_path}' is not a file.")
    return None


def load_data(
    data_path: str,
    sep: str = "\t",
    schema_length: int = 10000,
) -> pl.DataFrame:
    """
    Loads historical (i.e., `.tsv` data generated
    `cfaepim` for a weekly run) data.

    Parameters
    ----------
    data_path : str
        The path to the tsv file to be read.
    sep : str, optional
        The separator between values in the
        data file. Defaults to tab-separated.
    schema_length : int, optional
        An approximation of the expected
        maximum number of rows. Defaults
        to 10000.

    Returns
    -------
    pl.DataFrame
        An unvetted polars dataframe of NHSN
        hospitalization data.
    """
    check_file_path_valid(file_path=data_path)
    assert sep in ["\t", ","], f"Separator must be tabs or commas; was {sep}"
    assert (
        7500 <= schema_length <= 25000
    ), f"Schema length must be reasonable; was {schema_length}"
    data = pl.read_csv(
        data_path, separator=sep, infer_schema_length=schema_length
    )
    return data


def load_config(config_path: str) -> dict[str, any]:
    """
    Attempts to load config toml file.

    Parameters
    ----------
    config_path : str
        The path to the configuration file,
        read in via argparse.

    Returns
    -------
    config
        A dictionary of variables with
        associates values for `cfaepim`.
    """
    check_file_path_valid(file_path=config_path)
    try:
        config = toml.load(config_path)
    except toml.TomlDecodeError as e:
        raise ValueError(
            f"Failed to parse the TOML file at '{config_path}'; error: {e}"
        )
    except Exception as e:
        raise RuntimeError(
            f"An unexpected error occurred while reading the TOML file: {e}"
        )
    return config


def forecast_report():  # numpydoc ignore=GL08
    pass


def model_report():  # numpydoc ignore=GL08
    pass


def prior_report():  # numpydoc ignore=GL08
    pass


def plot_utils(
    axes: mpl.axes,
    figure: plt.figure,
    use_log: bool = False,
    title: str = "",
    ylabel: str = "",
    xlabel: str = "",
    use_legend: bool = False,
    display: bool = True,
    filename: str = "delete_me",
    save_as_img: bool = False,
    save_to_pdf: bool = False,
):  # numpydoc ignore=GL08
    if use_legend:
        axes.legend(loc="best")
    if use_log:
        axes.set_yscale("log")
        axes.set_ylabel(ylabel + " (Log-Scale)", fontproperties=AXES_FONT_PROP)
    axes.set_title(
        title,
        fontproperties=TITLE_FONT_PROP,
    )
    if not use_log:
        axes.set_xlabel(xlabel, fontproperties=AXES_FONT_PROP)
        axes.set_ylabel(ylabel, fontproperties=AXES_FONT_PROP)
    for label in axes.get_xticklabels():
        label.set_rotation(45)
        label.set_fontproperties(LABEL_FONT_PROP)
    for label in axes.get_yticklabels():
        label.set_fontproperties(LABEL_FONT_PROP)
    if display:
        plt.tight_layout()
        plt.show()
    if not os.path.exists(f"./figures/{filename}.png"):
        plt.tight_layout()
        if save_as_img:
            figure.savefig(f"./figures/{filename}")
        if save_to_pdf:
            return figure
    return None


def base_object_plot(
    y: np.ndarray,
    X: np.ndarray,
    title: str = "",
    X_label: str = "",
    Y_label: str = "",
    use_log: bool = False,
    use_legend: bool = False,
    display: bool = True,
    filename: str = "delete_me",
    save_as_img: bool = False,
    save_to_pdf: bool = False,
):  # numpydoc ignore=GL08
    figure, axes = plt.subplots(1, 1)
    axes.plot(X, y, color="black")
    axes.set_xlim(left=0)
    axes.set_ylim(bottom=0)
    plot_utils(
        figure=figure,
        axes=axes,
        title=title,
        xlabel=X_label,
        ylabel=Y_label,
        use_log=use_log,
        use_legend=use_legend,
        display=display,
        filename=filename,
        save_as_img=save_as_img,
        save_to_pdf=save_to_pdf,
    )


def plot_single_location_hosp_data(
    incidence_data: pl.DataFrame,
    states: str | list[str],
    lower_date: str,
    upper_date: str,
    use_log: bool = False,
    use_legend: bool = True,
    save_as_img: bool = False,
    save_to_pdf: bool = False,
    display: bool = True,
) -> None:
    """
    Plots incidence data between some
    lower and upper date (inclusive) for
    a single US territory.

    Parameters
    ----------
    incidence_data : pl.DataFrame
        A polars dataframe containing
        hospital admissions data.
    states : str | list[str]
        Two letter region abbreviation.
    lower_date : str
        Start date for data visualization.
    upper_date : str
        End date for data visualization.
    use_log : bool, optional
        Whether to use log-scaling on the
        y-axis. Defaults to False.
    use_legend : bool, optional
        Whether to use a legend. Defaults
        to True.
    save_as_img : bool, optional
        Whether to save the plot as an
        image. Defaults to False.
    save_to_pdf : bool, optional
        Whether to return the figure for
        use in a collected PDF of images.
    display : bool, optional
        Whether to show the image.

    Returns
    -------
    None | plt.figure
        Returns nothing if not saving
        to a pdf, otherwise return the
        figure.
    """
    # check states and set up linestyles
    if isinstance(states, str):
        states = [states]
    assert len(states) <= 4, "Use not more than four states."
    linestyles = ["solid", "dashed", "dotted", "dashdot"]
    # create figure and plot
    figure, axes = plt.subplots(1, 1)
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    axes.xaxis.set_major_locator(mdates.MonthLocator())
    # retrieve hospital admissions data and plot
    for i, state in enumerate(states):
        state_data = incidence_data.filter(
            (pl.col("location") == state)
            & (pl.col("date") >= lower_date)
            & (pl.col("date") <= upper_date)
        ).sort("date")
        observed_hosp_admissions = [
            int(elt) for elt in state_data["hosp"].to_list()
        ]
        dates = [
            dt.datetime.strptime(date, "%Y-%m-%d")
            for date in state_data["date"].to_list()
        ]
        axes.plot(
            dates,
            observed_hosp_admissions,
            color="black",
            linestyle=linestyles[i],
            label=state,
        )
    # other settings and saving figure
    ylabel = "Hospital Admissions"
    plot_utils(
        axes=axes,
        figure=figure,
        use_log=use_log,
        ylabel=ylabel,
        title=f"Reported Hospital Admissions: [{lower_date}, {upper_date}]",
        use_legend=use_legend,
        display=display,
        filename=f"{state}_{lower_date}-{upper_date}",
        save_as_img=save_as_img,
        save_to_pdf=save_to_pdf,
    )
    return None


class CFAEPIM_Infections(RandomVariable):  # numpydoc ignore=GL08
    def __init__(
        self,
        I0: ArrayLike,
        susceptibility_prior: numpyro.distributions,
    ):  # numpydoc ignore=GL08
        self.I0 = I0
        self.susceptibility_prior = susceptibility_prior

    @staticmethod
    def validate() -> None:  # numpydoc ignore=GL08
        return None

    def sample(
        self, Rt: ArrayLike, gen_int: ArrayLike, P: float, **kwargs
    ) -> tuple:  # numpydoc ignore=GL08
        """
        Given an array a reproduction numbers, a generation
        interval, and the size of the population, calculate
        infections under scheme of susceptible depletion.

        Parameters
        ----------
        Rt : ArrayLike
            Reproduction number over time.
            This is an array of Rt values for each time step.
        gen_int : ArrayLike
            Generation interval probability mass function.
            This is an array of probabilities representing the
            distribution of times between successive infections
            in a chain of transmission.
        P : float
            Population size. This is the total
            population size used for
            susceptibility adjustment.
        **kwargs : dict, optional
            Additional keyword arguments
            passed through to internal
            sample calls, should there be any.

        Returns
        -------
        tuple
            A tuple containing two arrays (all_I_t) array
            of infections at each time step and (all_S_t)
            array of susceptible individuals at each
            time step.

        Raises
        ------
        ValueError
            If the length of the initial infections vector (I0) is less
            than the length of the generation interval.
        """

        # get initial infections
        I0_samples = self.I0.sample()
        I0 = I0_samples[0].value

        # reverse generation interval (recency)
        gen_int_rev = jnp.flip(gen_int)

        if I0.size < gen_int.size:
            raise ValueError(
                "Initial infections vector must be at least as long as "
                "the generation interval. "
                f"Initial infections vector length: {I0.size}, "
                f"generation interval length: {gen_int.size}."
            )
        recent_I0 = I0[-gen_int_rev.size :]

        # sample the initial susceptible population
        # proportion S_{v-1} / P from prior
        init_S_proportion = numpyro.sample(
            "S_v_minus_1_over_P", self.susceptibility_prior
        )

        # confirm: ensure the proportion is between 0 and 1
        init_S_proportion = jnp.clip(init_S_proportion, 0, 1)

        # calculate initial susceptible population S_{v-1}
        init_S = init_S_proportion * P

        def update_infections(carry, Rt):  # numpydoc ignore=GL08
            S_t, I_recent = carry

            # compute raw infections
            i_raw_t = Rt * jnp.dot(I_recent, gen_int_rev)

            # apply the logistic susceptibility
            # adjustment to a potential new
            # incidence I_unadjusted proposed in
            # equation 6 of Bhatt et al 2023
            i_t = logistic_susceptibility_adjustment(
                I_raw_t=i_raw_t, frac_susceptible=S_t / P, n_population=P
            )

            # update susceptible population
            S_t -= i_t

            # update infections
            I_recent = jnp.concatenate([I_recent[:-1], jnp.array([i_t])])

            return (S_t, I_recent), i_t

        # initial carry state
        init_carry = (init_S, recent_I0)

        # scan to iterate over time steps and update infections
        (_, all_S_t), all_I_t = numpyro.contrib.control_flow.scan(
            update_infections, init_carry, Rt
        )

        return all_I_t, all_S_t


class CFAEPIM_Observation(RandomVariable):  # numpydoc ignore=GL08
    def __init__(
        self,
        predictors,
        alpha_intercept_prior_mode,
        alpha_intercept_prior_scale,
        day_of_week_effect_prior_modes,
        day_of_week_effect_prior_scales,
        holiday_eff_prior_mode,
        holiday_eff_prior_scale,
        post_holiday_eff_prior_mode,
        post_holiday_eff_prior_scale,
        non_obs_effect_prior_mode,
        non_obs_effect_prior_scale,
        max_rt,
        nb_concentration_prior,
    ):  # numpydoc ignore=GL08
        self.predictors = predictors
        self.alpha_intercept_prior_mode = alpha_intercept_prior_mode
        self.alpha_intercept_prior_scale = alpha_intercept_prior_scale

        # update: this should not depend on explicit covariates, it should
        # receive all_coefficient_priors? (works fine)
        self.day_of_week_effect_prior_modes = day_of_week_effect_prior_modes
        self.day_of_week_effect_prior_scales = day_of_week_effect_prior_scales
        self.holiday_eff_prior_mode = holiday_eff_prior_mode
        self.holiday_eff_prior_scale = holiday_eff_prior_scale
        self.post_holiday_eff_prior_mode = post_holiday_eff_prior_mode
        self.post_holiday_eff_prior_scale = post_holiday_eff_prior_scale
        self.non_obs_effect_prior_mode = non_obs_effect_prior_mode
        self.non_obs_effect_prior_scale = non_obs_effect_prior_scale
        self.max_rt = max_rt
        self.nb_concentration_prior = nb_concentration_prior

        self._init_alpha_t()
        self._init_negative_binomial()

    def _init_alpha_t(self):  # numpydoc ignore=GL08
        predictor_values = self.predictors
        alpha_intercept_prior = dist.Normal(
            self.alpha_intercept_prior_mode, self.alpha_intercept_prior_scale
        )
        # update: fine for
        all_coefficient_priors = dist.Normal(
            loc=jnp.array(
                self.day_of_week_effect_prior_modes
                + [
                    self.holiday_eff_prior_mode,
                    self.post_holiday_eff_prior_mode,
                    self.non_obs_effect_prior_mode,
                ]
            ),
            scale=jnp.array(
                self.day_of_week_effect_prior_scales
                + [
                    self.holiday_eff_prior_scale,
                    self.post_holiday_eff_prior_scale,
                    self.non_obs_effect_prior_scale,
                ]
            ),
        )
        self.alpha_process = GLMPrediction(
            name="alpha_t",
            fixed_predictor_values=predictor_values,
            intercept_prior=alpha_intercept_prior,
            coefficient_priors=all_coefficient_priors,
            transform=t.ScaledLogitTransform(x_max=1.0),
        )

    def _init_negative_binomial(self):  # numpydoc ignore=GL08
        self.nb_observation = NegativeBinomialObservation(
            name="negbinom_rv",
            concentration_rv=DistributionalRV(
                name="nb_concentration",
                dist=self.nb_concentration_prior,
            ),
        )

    @staticmethod
    def validate() -> None:  # numpydoc ignore=GL08
        pass

    def sample(
        self,
        infections: ArrayLike,
        delay_distribution: ArrayLike,
        **kwargs,
    ) -> tuple:  # numpydoc ignore=GL08
        alpha_samples = self.alpha_process.sample()["prediction"]
        alpha_samples = alpha_samples[: infections.shape[0]]
        expected_hosp = (
            alpha_samples
            * jnp.convolve(infections, delay_distribution, mode="full")[
                : infections.shape[0]
            ]
        )
        nb_samples = self.nb_observation.sample(mu=expected_hosp, **kwargs)
        return nb_samples


class CFAEPIM_Rt(RandomVariable):  # numpydoc ignore=GL08
    def __init__(
        self,
        intercept_RW_prior: numpyro.distributions,
        max_rt: float,
        gamma_RW_prior_scale: float,
    ):  # numpydoc ignore=GL08
        self.intercept_RW_prior = intercept_RW_prior
        self.max_rt = max_rt
        self.gamma_RW_prior_scale = gamma_RW_prior_scale

    @staticmethod
    def validate() -> None:  # numpydoc ignore=GL08
        pass

    def sample(self, n_steps: int, **kwargs) -> tuple:  # numpydoc ignore=GL08
        sd_wt = numpyro.sample(
            "Wt_rw_sd", dist.HalfNormal(self.gamma_RW_prior_scale)
        )
        wt_rv = SimpleRandomWalkProcess(
            name="Wt",
            step_rv=DistributionalRV(
                name="rw_step_rv",
                dist=dist.Normal(0, sd_wt),
                reparam=LocScaleReparam(0),
            ),
            init_rv=DistributionalRV(
                name="init_Wt_rv",
                dist=self.intercept_RW_prior,
            ),
        )
        transformed_rt_samples = TransformedRandomVariable(
            name="transformed_rt_rw",
            base_rv=wt_rv,
            transforms=t.ScaledLogitTransform(x_max=self.max_rt).inv,
        ).sample(n_steps=n_steps, **kwargs)
        return transformed_rt_samples

    # update: eventually want canonical ways to do this
    # update: to sampled value or in the sample call


class CFAEPIM_Model(Model):  # numpydoc ignore=GL08,PR01
    def __init__(
        self,
        config: dist[str, any],
        population: int,
        week_indices: list[int],
        first_week_hosp: int,
        predictors: list[int],
    ):  # numpydoc ignore=GL08
        self.population = (population,)
        self.week_indices = (week_indices,)
        self.first_week_hosp = (first_week_hosp,)
        self.predictors = (predictors,)

        self.config = config
        for key, value in config.items():
            setattr(self, key, value)

        # transmission: generation time distribution
        self.pmf_array = jnp.array(self.generation_time_dist)
        self.gen_int = DeterministicPMF(name="gen_int", value=self.pmf_array)

        # transmission: prior for RW intercept
        self.intercept_RW_prior = dist.Normal(
            self.rt_intercept_prior_mode, self.rt_intercept_prior_scale
        )

        # transmission: Rt process
        self.Rt_process = CFAEPIM_Rt(
            intercept_RW_prior=self.intercept_RW_prior,
            max_rt=self.max_rt,
            gamma_RW_prior_scale=self.weekly_rw_prior_scale,
        )

        # infections: get value rate for infection seeding (initialization)
        self.mean_inf_val = (
            self.inf_model_prior_infections_per_capita * self.population
        ) + (self.first_week_hosp / (self.ihr_intercept_prior_mode * 7))

        # infections: initial infections
        self.I0 = InfectionInitializationProcess(
            name="I0_initialization",
            I_pre_init_rv=DistributionalRV(
                name="I0",
                dist=dist.Exponential(rate=1 / self.mean_inf_val).expand(
                    [self.inf_model_seed_days]
                ),
            ),
            infection_init_method=InitializeInfectionsFromVec(
                n_timepoints=self.inf_model_seed_days
            ),
            t_unit=1,
        )

        # infections: susceptibility depletion prior
        self.susceptibility_prior = dist.Normal(
            self.susceptible_fraction_prior_mode,
            self.susceptible_fraction_prior_scale,
        )

        # infections component
        self.infections = CFAEPIM_Infections(
            I0=self.I0, susceptibility_prior=self.susceptibility_prior
        )

        # observations component
        self.nb_concentration_prior = dist.Normal(
            self.reciprocal_dispersion_prior_mode,
            self.reciprocal_dispersion_prior_scale,
        )
        self.obs_process = CFAEPIM_Observation(
            self.predictors,
            self.ihr_intercept_prior_mode,
            self.ihr_intercept_prior_scale,
            self.day_of_week_effect_prior_modes,
            self.day_of_week_effect_prior_scales,
            self.holiday_eff_prior_mode,
            self.holiday_eff_prior_scale,
            self.post_holiday_eff_prior_mode,
            self.post_holiday_eff_prior_scale,
            self.non_obs_effect_prior_mode,
            self.non_obs_effect_prior_scale,
            self.max_rt,
            self.nb_concentration_prior,
        )

    @staticmethod
    def validate() -> None:  # numpydoc ignore=GL08
        pass

    def sample(
        self,
        n_steps: int,
        **kwargs,
    ) -> tuple:  # numpydoc ignore=GL08
        # updated state of the components as classes
        # update: unfinished!
        # update: n_steps

        rt_samples = self.Rt_process.sample(n_steps=n_steps, **kwargs)["value"]
        all_I_t, all_S_t = self.infections.sample(
            Rt=rt_samples, gen_int=self.gen_int, P=self.population, **kwargs
        )
        nb_samples = self.observation.sample(
            infections=all_I_t,
            delay_distribution=self.inf_to_hosp_dist,
            **kwargs,
        )
        return rt_samples, all_I_t, all_S_t, nb_samples

    def predict(self, rng_key, **kwargs):  # numpydoc ignore=GL08
        posterior_pred_dist = numpyro.infer.Predictive(
            self.model, self.mcmc.get_samples()
        )
        predictions = posterior_pred_dist(
            rng_key=jax.random.PRNGKey(
                self.seed
            ),  # confirm: do not just define as instance attribute?
            num_samples=self.n_iter,
        )
        return predictions


def run(
    state: str, dataset: pl.DataFrame, config: dict[str, any]
):  # numpydoc ignore=GL08
    # extract population
    population = int(
        dataset.filter(pl.col("location") == state)
        .select(["population"])
        .unique()
        .to_numpy()[0][0]
    )

    # extract week indices
    week_indices = list(
        dataset.filter(pl.col("location") == state).select(["week"])["week"]
    )

    # first week hospitalizations
    first_week_hosp = (
        dataset.filter((pl.col("location") == state))
        .select(["first_week_hosp"])
        .to_numpy()[0][0]
    )

    # extract predictors
    day_of_week_covariate = dataset.select(pl.col("day_of_week")).to_dummies()
    remaining_covariates = dataset.select(["is_holiday", "is_post_holiday"])
    covariates = pl.concat(
        [day_of_week_covariate, remaining_covariates], how="horizontal"
    )
    predictors = covariates.to_numpy()

    # extract reported hospitalizations
    data_observed_hosp_admissions = np.array(
        dataset.filter(pl.col("location") == state).select(["date", "hosp"])[
            "hosp"
        ]
    )
    print(data_observed_hosp_admissions)

    # instantiate cfaepim-MSR
    cfaepim_MSR = CFAEPIM_Model(
        config=config,
        population=population,
        week_indices=week_indices,
        first_week_hosp=first_week_hosp,
        predictors=predictors,
    )
    print(cfaepim_MSR)


def verify_cfaepim_MSR(cfaepim_MSR_model) -> None:  # numpydoc ignore=GL08
    logger.info(f"Population Value:\n{cfaepim_MSR_model.population}\n")

    logger.info(f"Predictors:\n{cfaepim_MSR_model.predictors}\n")

    cfaepim_MSR_model.gen_int.validate(cfaepim_MSR_model.pmf_array)
    sampled_gen_int = cfaepim_MSR_model.gen_int.sample()
    logger.info(f"Generation Interval (Sampled):\n{sampled_gen_int}\n")

    base_object_plot(
        y=sampled_gen_int[0].value,
        X=np.arange(0, len(sampled_gen_int[0].value)),
        title="Sampled Generation Interval",
        filename="sample_generation_interval",
        save_as_img=False,
        display=False,
    )

    logger.info(
        f"Rt Process Object:\n{cfaepim_MSR_model.Rt_process}\n{dir(cfaepim_MSR_model.Rt_process)}"
    )
    logger.info(
        f"Rt Process Sample Method Signature):\n{inspect.signature(cfaepim_MSR_model.Rt_process.sample)}"
    )

    with numpyro.handlers.seed(rng_seed=cfaepim_MSR_model.seed):
        sampled_Rt = cfaepim_MSR_model.Rt_process.sample(n_steps=100)
    logger.info(f"Rt Process Samples:\n{sampled_Rt}\n")

    logger.info(
        f"First Week Mean Infections:\n{cfaepim_MSR_model.mean_inf_val}\n"
    )

    logger.info(
        f"Initialization Infections Object:\n{cfaepim_MSR_model.I0}\n{dir(cfaepim_MSR_model.I0)}"
    )
    logger.info(
        f"Initialization Infections Sample Method Signature:\n{inspect.signature(cfaepim_MSR_model.I0.sample)}"
    )

    with numpyro.handlers.seed(rng_seed=cfaepim_MSR_model.seed):
        sampled_I0 = cfaepim_MSR_model.I0.sample()
    logger.info(f"Initial Infections Samples:\n{sampled_I0}\n")

    with numpyro.handlers.seed(rng_seed=cfaepim_MSR_model.seed):
        sampled_gen_int = cfaepim_MSR_model.gen_int.sample()
        all_I_t, all_S_t = cfaepim_MSR_model.infections.sample(
            Rt=sampled_Rt[0].value,
            gen_int=sampled_gen_int[0].value,
            P=1000000,
        )
    logger.info(
        f"Infections & Susceptibles\nall_I_t: {all_I_t}\nall_S_t: {all_S_t}"
    )

    logger.info(
        f"Observation Process Object:\n{cfaepim_MSR_model.obs_process}\n{dir(cfaepim_MSR_model.obs_process)}"
    )
    logger.info(
        f"Observation Process Sample Method Signature:\n{inspect.signature(cfaepim_MSR_model.obs_process.sample)}\n"
    )

    with numpyro.handlers.seed(rng_seed=cfaepim_MSR_model.seed):
        sampled_alpha = cfaepim_MSR_model.obs_process.alpha_process.sample()[
            "prediction"
        ]
    logger.info(
        f"Instantaneous Ascertainment Rate Samples:\n{sampled_alpha}\n"
    )

    with numpyro.handlers.seed(rng_seed=cfaepim_MSR_model.seed):
        sampled_obs = cfaepim_MSR_model.obs_process(
            infections=all_I_t,
            delay_distribution=jnp.array(cfaepim_MSR_model.inf_to_hosp_dist),
        )
    logger.info(f"Hospitalization Observation Samples:\n{sampled_obs}\n")


def main():  # numpydoc ignore=GL08
    """
    The `cfaepim` model required a configuration
    file and a dataset. The configuration file must
    follow some detailed specifications, as must the
    dataset. Once these are in place, the model is
    used in the following manner for each state:
    (1) extract the population, the indices of the weeks,
    the hospitalizations during the first week, & the
    covariates, (2) the configuration file and the
    previous content then will be used to produce
    an Rt, infections, and observation process by
    passing them to the `cfaepim` model, (3) the user
    can use argparse to test or compare the forecasts.

    Notes
    -----
    Testing in `cfaepim` includes ensuring the dataset
    and configuration have the correct variables and
    values in a proper range. Testing also ensures that
    each part of the `cfaepim` model works as desired.
    """

    # parser = argparse.ArgumentParser(
    #     description="Forecast, simulate, and analyze the CFAEPIM model."
    # )
    # parser.add_argument(
    #     "--config_path",
    #     type=str,
    #     required=True,
    #     help="Crowd forecasts (sep. w/ space).",
    # )
    # parser.add_argument(
    #     "--data_path",
    #     type=str,
    #     required=True,
    #     help="Crowd forecasts (sep. w/ space).",
    # )
    # parser.add_argument(
    #     "--historical_data",
    #     action="store_true",
    #     help="Load model weights before training.",
    # )
    # args = parser.parse_args()

    # determine number of CPU cores
    num_cores = os.cpu_count()
    numpyro.set_host_device_count(num_cores - (num_cores - 1))

    # load parameters config (2024-01-20)
    config = load_config(config_path="./config/params_2024-01-20.toml")

    # load & display NHSN data w/ population counts (2024-01-20)
    data_path = "./data/2024-01-20/2024-01-20_clean_data.tsv"
    influenza_hosp_data = load_data(data_path=data_path)
    rows, cols = influenza_hosp_data.shape
    display_data(data=influenza_hosp_data, n_col_count=cols)

    run(state="NY", dataset=influenza_hosp_data, config=config)

    # verification: plot single state hospitalizations
    plot_single_location_hosp_data(
        incidence_data=influenza_hosp_data,
        states=["NY"],
        lower_date="2022-01-01",
        upper_date="2024-03-10",
        use_log=False,
        use_legend=True,
        save_as_img=False,
        save_to_pdf=False,
        display=False,
    )

    # # verification: data_observed_hosp_admissions
    # print(f"HOSPITALIZATIONS:\n{data_observed_hosp_admissions}\n\n")

    # # verify and visualize aspects of the model
    # verify_cfaepim_MSR(cfaepim_MSR)

    # model_instance.run(
    #     num_warmup=model_instance.config["n_warmup"],
    #     num_samples=model_instance.config["n_iter"],
    #     rng_key=jax.random.PRNGKey(model_instance.config["seed"]),
    #     data_observed_hosp_admissions=data_observed_hosp_admissions,
    #     nuts_args={
    #         "max_tree_depth": model_instance.config["max_tree_depth"],
    #         "step_size": model_instance.config["adapt_delta"]}
    # )

    # instantiate MSR-cfaepim model
    # simulate data
    # run the model for NY
    # print summary (print_summary)
    # visualize prior predictive (prior_predictive)
    # visualize posterior predictive (posterior_predictive)
    # spread draws (spread_draws)


if __name__ == "__main__":
    main()


# you have a dataset and a configuration file
# you can generate 3 reports, one on the priors, one on
# the model, one on the forecasts; these are intelligently
# looked for and then concatenated; file naming is done
# intelligently.
# you can choose, using argparse, which states are run
# as well as the report date and target end date;
# data is used differently when available
# comparison is done with --historical
#
