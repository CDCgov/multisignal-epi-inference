# -*- coding: utf-8 -*-

import jax
import jax.numpy as jnp
from numpy.typing import ArrayLike
from pyrenew.convolve import new_convolve_scanner, new_double_scanner

"""
infection

Functions for sampling timeseries of
infections
"""


def sample_infections_rt(
    I0: ArrayLike, Rt: ArrayLike, reversed_generation_interval_pmf: ArrayLike
):
    """
    Sample infections according to a
    renewal process with a time-varying
    reproduction number R(t)

    Parameters
    ----------
    I0: ArrayLike
        Array of initial infections of the
        same length as the generation inferval
        pmf vector.

    Rt: ArrayLike
        Timeseries of R(t) values

    reversed_generation_interval_pmf: ArrayLike
        discrete probability mass vector
        representing the generation interval
        of the infection process, where the final
        entry represents an infection 1 time unit in the
        past, the second-to-last entry represents
        an infection two time units in the past, etc.

    Returns
    --------
    The timeseries of infections, as a JAX array
    """
    incidence_func = new_convolve_scanner(reversed_generation_interval_pmf)

    latest, all_infections = jax.lax.scan(incidence_func, I0, Rt)

    return all_infections


def logistic_susceptibility_adjustment(
    I_raw_t: float,
    frac_susceptible: float,
    n_population: float,
):
    """
    Apply the logistic susceptibility
    adjustment to a potential new
    incidence I_unadjusted proposed in
    equation 6 of Bhatt et al 2023 [1]_

    Parameters
    ----------
    I_raw_t : float
        The "unadjusted" incidence at time t,
        i.e. the incidence given an infinite
        number of available susceptible individuals.

    frac_susceptible : float
        fraction of remainin susceptible individuals
        in the population

    n_population : float
        Total size of the population.

    Returns
    -------
    float:
        The adjusted value of I(t)

    .. [1] Bhatt, Samir, et al.
    "Semi-mechanistic Bayesian modelling of
    COVID-19 with renewal processes."
    Journal of the Royal Statistical Society
    Series A: Statistics in Society 186.4 (2023): 601-615.
    https://doi.org/10.1093/jrsssa/qnad030
    """
    approx_frac_infected = 1 - jnp.exp(-I_raw_t / n_population)
    return n_population * frac_susceptible * approx_frac_infected


def sample_infections_with_feedback(
    I0: ArrayLike,
    Rt_raw: ArrayLike,
    infection_feedback_strength: ArrayLike,
    generation_interval_pmf: ArrayLike,
    infection_feedback_pmf: ArrayLike,
):
    """
    Sample infections according to
    a renewal process with infection
    feedback (generalizing Asher 2018:
    https://doi.org/10.1016/j.epidem.2017.02.009)

    Parameters
    ----------
    I0: ArrayLike
        Array of initial infections of the
        same length as the generation inferval
        pmf vector.

    Rt_raw: ArrayLike
        Timeseries of raw R(t) values not
        adjusted by infection feedback

    infection_feedback_strength: ArrayLike
        Strength of the infection feedback.
        Either a scalar (constant feedback
        strength in time) or a vector representing
        the infection feedback strength at a
        given point in time.

    generation_interval_pmf: ArrayLike
        discrete probability mass vector
        representing the generation interval
        of the infection process

    infection_feedback_pmf: ArrayLike
        discrete probability mass vector
        whose `i`th entry represents the
        relative contribution to infection
        feedback from infections that occurred
        `i` days in the past.

    Returns
    -------
    A tuple `(Rt_adjusted, infections)`,
    where `Rt_adjusted` is the infection-feedback-adjusted
    timeseries of the reproduction number R(t) and
    infections is the incident infection timeseries.
    """
    feedback_scanner = new_double_scanner(
        (infection_feedback_pmf, generation_interval_pmf),
        (jnp.exp, lambda x: x),
    )
    latest, infs_and_R = jax.lax.scan(
        feedback_scanner, I0, (infection_feedback_strength, Rt_raw)
    )
    return infs_and_R
