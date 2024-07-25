# -*- coding: utf-8 -*-
# numpydoc ignore=GL08

import numpy as np
import numpy.testing as testing
import numpyro
from jax.typing import ArrayLike
from pyrenew.deterministic import DeterministicVariable
from pyrenew.observation import NegativeBinomialObservation


def test_negativebinom_deterministic_obs():
    """
    Check that a deterministic NegativeBinomialObservation can sample
    """

    negb = NegativeBinomialObservation(
        "negbinom_rv",
        concentration_rv=DeterministicVariable(10, name="concentration"),
    )

    np.random.seed(223)
    rates = np.random.randint(1, 5, size=10)
    with numpyro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_nb1 = negb(mu=rates, obs=rates)
        sim_nb2 = negb(mu=rates, obs=rates)

    assert isinstance(sim_nb1, tuple)
    assert isinstance(sim_nb2, tuple)
    assert isinstance(sim_nb1[0], ArrayLike)
    assert isinstance(sim_nb2[0], ArrayLike)

    testing.assert_array_equal(
        sim_nb1[0],
        sim_nb2[0],
    )


def test_negativebinom_random_obs():
    """
    Check that a random NegativeBinomialObservation can sample
    """

    negb = NegativeBinomialObservation(
        "negbinom_rv",
        concentration_rv=DeterministicVariable(10, "concentration"),
    )

    np.random.seed(223)
    rates = np.repeat(5, 20000)
    with numpyro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_nb1 = negb(mu=rates)
        sim_nb2 = negb(mu=rates)
    assert isinstance(sim_nb1, tuple)
    assert isinstance(sim_nb2, tuple)
    assert isinstance(sim_nb1[0], ArrayLike)
    assert isinstance(sim_nb2[0], ArrayLike)

    testing.assert_array_almost_equal(
        np.mean(sim_nb1[0]),
        np.mean(sim_nb2[0]),
        decimal=1,
    )
