# -*- coding: utf-8 -*-
# numpydoc ignore=GL08

import jax.numpy as jnp
import numpy as np
import numpy.testing as testing
import numpyro as npro
import numpyro.distributions as dist
from pyrenew import transformation as t
from pyrenew.deterministic import DeterministicPMF
from pyrenew.latent import HospitalAdmissions, Infections
from pyrenew.metaclass import DistributionalRV
from pyrenew.process import RtRandomWalkProcess


def test_admissions_sample():
    """
    Check that a HospitalAdmissions latent process
    can be initialized and sampled from.
    """

    # Generating Rt and Infections to compute the hospital admissions
    np.random.seed(223)

    rt = RtRandomWalkProcess(
        Rt0_dist=dist.TruncatedNormal(loc=1.2, scale=0.2, low=0),
        Rt_transform=t.ExpTransform().inv,
        Rt_rw_dist=dist.Normal(0, 0.025),
    )
    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_rt, *_ = rt.sample(n_timepoints=30)

    gen_int = jnp.array([0.5, 0.1, 0.1, 0.2, 0.1])
    i0 = 10 * jnp.ones_like(gen_int)

    inf1 = Infections()

    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        inf_sampled1 = inf1.sample(Rt=sim_rt, gen_int=gen_int, I0=i0)

    # Testing the hospital admissions
    inf_hosp = DeterministicPMF(
        jnp.array(
            [
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0.25,
                0.5,
                0.1,
                0.1,
                0.05,
            ]
        ),
        name="inf_hosp",
    )

    hosp1 = HospitalAdmissions(
        infection_to_admission_interval_rv=inf_hosp,
        infect_hosp_rate_rv=DistributionalRV(
            dist=dist.LogNormal(jnp.log(0.05), 0.05), name="IHR"
        ),
    )

    with npro.handlers.seed(rng_seed=np.random.randint(1, 600)):
        sim_hosp_1 = hosp1.sample(latent_infections=inf_sampled1[0])

    testing.assert_array_less(
        sim_hosp_1.latent_hospital_admissions,
        inf_sampled1[0],
    )
