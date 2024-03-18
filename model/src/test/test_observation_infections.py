import jax.numpy as jnp
import numpy as np
import numpy.testing as testing
import numpyro as npro
from pyrenew.observations import InfectionsObservation, PoissonObservation
from pyrenew.processes import RtRandomWalkProcess


def test_infections_as_deterministic():
    """
    Check that an InfectionObservation
    can be initialized and sampled from (deterministic)
    """

    np.random.seed(223)
    rt = RtRandomWalkProcess()
    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_rt, *_ = rt.sample(constants={"n_timepoints": 30})

    inf1 = InfectionsObservation(jnp.array([0.25, 0.25, 0.25, 0.25]))

    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        obs = dict(Rt=sim_rt, I0=10)
        inf_sampled1 = inf1.sample(random_variables=obs)
        inf_sampled2 = inf1.sample(random_variables=obs)

    # Should match!
    testing.assert_array_equal(inf_sampled1.predicted, inf_sampled2.predicted)
    testing.assert_array_equal(inf_sampled1.observed, inf_sampled2.observed)


def test_infections_as_random():
    """_summary_"""

    np.random.seed(223)
    rt = RtRandomWalkProcess()
    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_rt, *_ = rt.sample(constants={"n_timepoints": 30})

    inf1 = InfectionsObservation(
        jnp.array([0.25, 0.25, 0.25, 0.25]),
        inf_observation_model=PoissonObservation(
            rate_varname="infections_mean"
        ),
    )

    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        obs = dict(Rt=sim_rt, I0=10)
        inf_sampled0 = inf1.sample(random_variables=obs)

        obs = {**obs, **dict(infections=inf_sampled0)}

        inf_sampled1 = inf1.sample(random_variables=obs)
        inf_sampled2 = inf1.sample(random_variables=obs)

    # Observed shouldn't match (bc/sampled)!
    testing.assert_array_equal(inf_sampled1.predicted, inf_sampled2.predicted)
    assert not all(inf_sampled1.observed == inf_sampled2.observed)