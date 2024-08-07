"""
Test the InfectionsWithFeedback class
"""

import jax.numpy as jnp
import numpy as np
import numpyro
import pyrenew.latent as latent
from jax.typing import ArrayLike
from numpy.testing import assert_array_almost_equal, assert_array_equal
from pyrenew.deterministic import DeterministicPMF, DeterministicVariable


def _infection_w_feedback_alt(
    gen_int: ArrayLike,
    Rt: ArrayLike,
    I0: ArrayLike,
    inf_feedback_strength: ArrayLike,
    inf_feedback_pmf: ArrayLike,
) -> tuple:
    """
    Calculate the infections with feedback.
    Parameters
    ----------
    gen_int : ArrayLike
        Generation interval.
    Rt : ArrayLike
        Reproduction number.
    I0 : ArrayLike
        Initial infections.
    inf_feedback_strength : ArrayLike
        Infection feedback strength.
    inf_feedback_pmf : ArrayLike
        Infection feedback pmf.

    Returns
    -------
    tuple
    """

    Rt = np.array(Rt)  # coerce from jax to use numpy-like operations
    T = len(Rt)
    len_gen = len(gen_int)
    I_vec = np.concatenate([I0, np.zeros(T)])
    Rt_adj = np.zeros(T)

    for t in range(T):
        Rt_adj[t] = Rt[t] * np.exp(
            inf_feedback_strength[t]
            * np.dot(I_vec[t : t + len_gen], np.flip(inf_feedback_pmf))
        )

        I_vec[t + len_gen] = Rt_adj[t] * np.dot(
            I_vec[t : t + len_gen], np.flip(gen_int)
        )

    return {"post_initialization_infections": I_vec[I0.size :], "rt": Rt_adj}


def test_infectionsrtfeedback():
    """
    Test the InfectionsWithFeedback matching the Infections class.
    """

    Rt = jnp.array([0.5, 0.6, 0.7, 0.8, 2, 0.5, 2.25])
    I0 = jnp.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    gen_int = jnp.array([0.4, 0.25, 0.25, 0.1, 0.0, 0.0, 0.0])

    # By doing the infection feedback strength 0, Rt = Rt_adjusted
    # So infection should be equal in both
    inf_feed_strength = DeterministicVariable(
        name="inf_feed_strength", value=jnp.zeros_like(Rt)
    )
    inf_feedback_pmf = DeterministicPMF(name="inf_feedback_pmf", value=gen_int)

    # Test the InfectionsWithFeedback class
    InfectionsWithFeedback = latent.InfectionsWithFeedback(
        infection_feedback_strength=inf_feed_strength,
        infection_feedback_pmf=inf_feedback_pmf,
    )

    infections = latent.Infections()

    with numpyro.handlers.seed(rng_seed=0):
        samp1 = InfectionsWithFeedback(
            gen_int=gen_int,
            Rt=Rt,
            I0=I0,
        )

        samp2 = infections(
            gen_int=gen_int,
            Rt=Rt,
            I0=I0,
        )

    assert_array_equal(
        samp1.post_initialization_infections.value,
        samp2.post_initialization_infections.value,
    )
    assert_array_equal(samp1.rt.value, Rt)

    return None


def test_infectionsrtfeedback_feedback():
    """
    Test the InfectionsWithFeedback with feedback
    """

    Rt = jnp.array([0.5, 0.6, 1.5, 2.523, 0.7, 0.8])
    I0 = jnp.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    gen_int = jnp.array([0.4, 0.25, 0.25, 0.1, 0.0, 0.0, 0.0])

    inf_feed_strength = DeterministicVariable(
        name="inf_feed_strength", value=jnp.repeat(0.5, len(Rt))
    )
    inf_feedback_pmf = DeterministicPMF(name="inf_feedback_pmf", value=gen_int)

    # Test the InfectionsWithFeedback class
    InfectionsWithFeedback = latent.InfectionsWithFeedback(
        infection_feedback_strength=inf_feed_strength,
        infection_feedback_pmf=inf_feedback_pmf,
    )

    infections = latent.Infections()

    with numpyro.handlers.seed(rng_seed=0):
        samp1 = InfectionsWithFeedback(
            gen_int=gen_int,
            Rt=Rt,
            I0=I0,
        )

        samp2 = infections(
            gen_int=gen_int,
            Rt=Rt,
            I0=I0,
        )

    res = _infection_w_feedback_alt(
        gen_int=gen_int,
        Rt=Rt,
        I0=I0,
        inf_feedback_strength=inf_feed_strength()[0].value,
        inf_feedback_pmf=inf_feedback_pmf()[0].value,
    )

    assert not jnp.array_equal(
        samp1.post_initialization_infections.value,
        samp2.post_initialization_infections.value,
    )
    assert_array_almost_equal(
        samp1.post_initialization_infections.value,
        res["post_initialization_infections"],
    )
    assert_array_almost_equal(samp1.rt.value, res["rt"])

    return None
