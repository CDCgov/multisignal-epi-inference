# numpydoc ignore=GL08

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax.typing import ArrayLike

from pyrenew.convolve import new_convolve_scanner, new_double_convolve_scanner
from pyrenew.transformation import ExpTransform, IdentityTransform


def compute_infections_from_rt(
    I0: ArrayLike,
    Rt: ArrayLike,
    reversed_generation_interval_pmf: ArrayLike,
) -> jnp.ndarray:
    """
    Generate infections according to a
    renewal process with a time-varying
    reproduction number :math:`\\mathcal{R}(t)`

    Parameters
    ----------
    I0 : ArrayLike
        Array of initial infections of the
        same length as the generation interval
        pmf vector.
    Rt : ArrayLike
        Timeseries of :math:`\\mathcal{R}(t)` values
    reversed_generation_interval_pmf : ArrayLike
        discrete probability mass vector
        representing the generation interval
        of the infection process, where the final
        entry represents an infection 1 time unit in the
        past, the second-to-last entry represents
        an infection two time units in the past, etc.

    Returns
    -------
    jnp.ndarray
        The timeseries of infections.
    """
    incidence_func = new_convolve_scanner(
        reversed_generation_interval_pmf, IdentityTransform()
    )

    latest, all_infections = jax.lax.scan(f=incidence_func, init=I0, xs=Rt)

    return all_infections


def logistic_susceptibility_adjustment(
    I_raw_t: float,
    frac_susceptible: float,
    n_population: float,
) -> float:
    """
    Apply the logistic susceptibility
    adjustment to a potential new
    incidence ``I_raw_t`` proposed in
    equation 6 of `Bhatt et al 2023
    <https://doi.org/10.1093/jrsssa/qnad030>`_.

    Parameters
    ----------
    I_raw_t : float
        The "unadjusted" incidence at time t,
        i.e. the incidence given an infinite
        number of available susceptible individuals.
    frac_susceptible : float
        fraction of remaining susceptible individuals
        in the population
    n_population : float
        Total size of the population.

    Returns
    -------
    float
        The adjusted value of :math:`I(t)`.
    """
    approx_frac_infected = 1 - jnp.exp(-I_raw_t / n_population)
    return n_population * frac_susceptible * approx_frac_infected


def compute_infections_from_rt_with_feedback(
    I0: ArrayLike,
    Rt_raw: ArrayLike,
    infection_feedback_strength: ArrayLike,
    reversed_generation_interval_pmf: ArrayLike,
    reversed_infection_feedback_pmf: ArrayLike,
) -> tuple:
    r"""
    Generate infections according to
    a renewal process with infection
    feedback (generalizing `Asher 2018
    <https://doi.org/10.1016/j.epidem.2017.02.009>`_).

    Parameters
    ----------
    I0 : ArrayLike
        Array of initial infections of the
        same length as the generation interval
        pmf vector.
    Rt_raw : ArrayLike
        Timeseries of raw :math:`\mathcal{R}(t)` values not
        adjusted by infection feedback
    infection_feedback_strength : ArrayLike
        Strength of the infection feedback.
        Either a scalar (constant feedback
        strength in time) or a vector representing
        the infection feedback strength at a
        given point in time.
    reversed_generation_interval_pmf : ArrayLike
        discrete probability mass vector
        representing the generation interval
        of the infection process, where the final
        entry represents an infection 1 time unit in the
        past, the second-to-last entry represents
        an infection two time units in the past, etc.
    reversed_infection_feedback_pmf : ArrayLike
        discrete probability mass vector
        representing the infection feedback
        process, where the final entry represents
        the relative contribution to infection
        feedback from infections that occurred
        1 time unit in the past, the second-to-last
        entry represents the contribution from infections
        that occurred 2 time units in the past, etc.

    Returns
    -------
    tuple
        A tuple ``(infections, Rt_adjusted)``,
        where ``Rt_adjusted`` is the infection-feedback-adjusted
        timeseries of the reproduction number :math:`\mathcal{R}(t)`
        and ``infections`` is the incident infection timeseries.

    Notes
    -----
    This function implements the following renewal process:

    .. math::
        \begin{aligned}
        I(t) & = \mathcal{R}(t)\sum_{\tau=1}^{T_g}I(t - \tau)g(\tau) \\
        \mathcal{R}(t) & = \mathcal{R}^u(t)\exp\left(\gamma(t)\
            \sum_{\tau=1}^{T_f}I(t - \tau)f(\tau)\right)
        \end{aligned}

    where :math:`\mathcal{R}(t)` is the reproductive number,
    :math:`\gamma(t)` is the infection feedback strength,
    :math:`T_g` is the max-length of the
    generation interval, :math:`\mathcal{R}^u(t)` is the raw reproduction
    number, :math:`f(t)` is the infection feedback pmf, and :math:`T_f`
    is the max-length of the infection feedback pmf.

    Note that negative :math:`\gamma(t)` implies
    that recent incident infections reduce :math:`\mathcal{R}(t)`
    below its raw value in the absence of feedback, while
    positive :math:`\gamma` implies that recent incident infections
    *increase* :math:`\mathcal{R}(t)` above its raw value, and
    :math:`\gamma(t)=0` implies no feedback.

    In general, negative :math:`\gamma` is the more common modeling
    choice, as it can be used to model susceptible depletion,
    reductions in contact rate due to awareness of high incidence,
    et cetera.
    """
    feedback_scanner = new_double_convolve_scanner(
        arrays_to_convolve=(
            reversed_infection_feedback_pmf,
            reversed_generation_interval_pmf,
        ),
        transforms=(ExpTransform(), IdentityTransform()),
    )
    latest, infs_and_R_adj = jax.lax.scan(
        f=feedback_scanner,
        init=I0,
        xs=(infection_feedback_strength, Rt_raw),
    )

    infections, R_adjustment = infs_and_R_adj
    Rt_adjusted = R_adjustment * Rt_raw
    return infections, Rt_adjusted
