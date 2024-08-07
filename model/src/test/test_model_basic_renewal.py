# -*- coding: utf-8 -*-
# numpydoc ignore=GL08


import jax.numpy as jnp
import jax.random as jr
import numpy as np
import numpyro
import numpyro.distributions as dist
import polars as pl
import pyrenew.transformation as t
import pytest
from pyrenew.deterministic import DeterministicPMF, NullObservation
from pyrenew.latent import (
    InfectionInitializationProcess,
    Infections,
    InitializeInfectionsZeroPad,
)
from pyrenew.metaclass import DistributionalRV, TransformedRandomVariable
from pyrenew.model import RtInfectionsRenewalModel
from pyrenew.observation import PoissonObservation
from pyrenew.process import SimpleRandomWalkProcess


def get_default_rt():
    """
    Helper function to create a default Rt
    RandomVariable for this testing session.

    Returns
    -------
    TransformedRandomVariable :
       A log-scale random walk with fixed
       init value and step size priors
    """
    return TransformedRandomVariable(
        "Rt_rv",
        base_rv=SimpleRandomWalkProcess(
            name="log_rt",
            step_rv=DistributionalRV(
                name="rw_step_rv", dist=dist.Normal(0, 0.025)
            ),
            init_rv=DistributionalRV(
                name="init_log_rt", dist=dist.Normal(0, 0.2)
            ),
        ),
        transforms=t.ExpTransform(),
    )


def test_model_basicrenewal_no_timepoints_or_observations():
    """
    Test that the basic renewal model does not run
    without either n_datapoints or
    observed_admissions
    """

    gen_int = DeterministicPMF(
        name="gen_int", value=jnp.array([0.25, 0.25, 0.25, 0.25])
    )

    I0 = DistributionalRV(name="I0", dist=dist.LogNormal(0, 1))

    latent_infections = Infections()

    observed_infections = PoissonObservation("poisson_rv")

    rt = get_default_rt()

    model1 = RtInfectionsRenewalModel(
        I0_rv=I0,
        gen_int_rv=gen_int,
        latent_infections_rv=latent_infections,
        infection_obs_process_rv=observed_infections,
        Rt_process_rv=rt,
    )

    with numpyro.handlers.seed(rng_seed=223):
        with pytest.raises(ValueError, match="Either"):
            model1.sample(n_datapoints=None, data_observed_infections=None)


def test_model_basicrenewal_both_timepoints_and_observations():
    """
    Test that the basic renewal model does not run with both n_datapoints and observed_admissions passed
    """

    gen_int = DeterministicPMF(
        name="gen_int",
        value=jnp.array([0.25, 0.25, 0.25, 0.25]),
    )

    I0 = DistributionalRV(name="I0", dist=dist.LogNormal(0, 1))

    latent_infections = Infections()

    observed_infections = PoissonObservation("possion_rv")

    rt = get_default_rt()

    model1 = RtInfectionsRenewalModel(
        I0_rv=I0,
        gen_int_rv=gen_int,
        latent_infections_rv=latent_infections,
        infection_obs_process_rv=observed_infections,
        Rt_process_rv=rt,
    )

    with numpyro.handlers.seed(rng_seed=223):
        with pytest.raises(ValueError, match="Cannot pass both"):
            model1.sample(
                n_datapoints=30,
                data_observed_infections=jnp.repeat(jnp.nan, 30),
            )


def test_model_basicrenewal_no_obs_model():
    """
    Test the basic semi-deterministic renewal model runs. Semi-deterministic
    from the perspective of the infections. It returns expected, not sampled.
    """

    gen_int = DeterministicPMF(
        name="gen_int",
        value=jnp.array([0.25, 0.25, 0.25, 0.25]),
    )

    with pytest.raises(ValueError):
        I0 = DistributionalRV(name="I0", dist=1)

    I0 = InfectionInitializationProcess(
        "I0_initialization",
        DistributionalRV(name="I0", dist=dist.LogNormal(0, 1)),
        InitializeInfectionsZeroPad(n_timepoints=gen_int.size()),
        t_unit=1,
    )

    latent_infections = Infections()

    rt = get_default_rt()

    model0 = RtInfectionsRenewalModel(
        gen_int_rv=gen_int,
        I0_rv=I0,
        latent_infections_rv=latent_infections,
        Rt_process_rv=rt,
        # Explicitly use None, this should call the NullObservation
        infection_obs_process_rv=None,
    )

    # Sampling and fitting model 0 (with no obs for infections)
    with numpyro.handlers.seed(rng_seed=223):
        model0_samp = model0.sample(n_datapoints=30)
    model0_samp.Rt
    model0_samp.latent_infections
    model0_samp.observed_infections

    # Generating
    model0.infection_obs_process_rv = NullObservation()
    with numpyro.handlers.seed(rng_seed=223):
        model1_samp = model0.sample(n_datapoints=30)

    np.testing.assert_array_equal(model0_samp.Rt.value, model1_samp.Rt.value)
    np.testing.assert_array_equal(
        model0_samp.latent_infections.value,
        model1_samp.latent_infections.value,
    )
    np.testing.assert_array_equal(
        model0_samp.observed_infections.value,
        model1_samp.observed_infections.value,
    )

    model0.run(
        num_warmup=500,
        num_samples=500,
        rng_key=jr.key(272),
        data_observed_infections=model0_samp.latent_infections.value,
    )

    inf = model0.spread_draws(["all_latent_infections"])
    inf_mean = (
        inf.group_by("draw")
        .agg(pl.col("all_latent_infections").mean())
        .sort(pl.col("draw"))
    )

    # For now the assertion is only about the expected number of rows
    # It should be about the MCMC inference.
    assert inf_mean.to_numpy().shape[0] == 500


def test_model_basicrenewal_with_obs_model():
    """
    Test the basic random renewal model runs. Random
    from the perspective of the infections. It returns sampled, not expected.
    """

    gen_int = DeterministicPMF(
        name="gen_int", value=jnp.array([0.25, 0.25, 0.25, 0.25])
    )

    I0 = InfectionInitializationProcess(
        "I0_initialization",
        DistributionalRV(name="I0", dist=dist.LogNormal(0, 1)),
        InitializeInfectionsZeroPad(n_timepoints=gen_int.size()),
        t_unit=1,
    )

    latent_infections = Infections()

    observed_infections = PoissonObservation("poisson_rv")

    rt = get_default_rt()

    model1 = RtInfectionsRenewalModel(
        I0_rv=I0,
        gen_int_rv=gen_int,
        latent_infections_rv=latent_infections,
        infection_obs_process_rv=observed_infections,
        Rt_process_rv=rt,
    )

    # Sampling and fitting model 1 (with obs infections)
    with numpyro.handlers.seed(rng_seed=223):
        model1_samp = model1.sample(n_datapoints=30)

    model1.run(
        num_warmup=500,
        num_samples=500,
        rng_key=jr.key(22),
        data_observed_infections=model1_samp.observed_infections.value,
    )

    inf = model1.spread_draws(["all_latent_infections"])
    inf_mean = (
        inf.group_by("draw")
        .agg(pl.col("all_latent_infections").mean())
        .sort(pl.col("draw"))
    )

    # For now the assertion is only about the expected number of rows
    # It should be about the MCMC inference.
    assert inf_mean.to_numpy().shape[0] == 500


def test_model_basicrenewal_padding() -> None:  # numpydoc ignore=GL08
    gen_int = DeterministicPMF(
        name="gen_int", value=jnp.array([0.25, 0.25, 0.25, 0.25])
    )

    I0 = InfectionInitializationProcess(
        "I0_initialization",
        DistributionalRV(name="I0", dist=dist.LogNormal(0, 1)),
        InitializeInfectionsZeroPad(n_timepoints=gen_int.size()),
        t_unit=1,
    )

    latent_infections = Infections()

    observed_infections = PoissonObservation("poisson_rv")

    rt = get_default_rt()

    model1 = RtInfectionsRenewalModel(
        I0_rv=I0,
        gen_int_rv=gen_int,
        latent_infections_rv=latent_infections,
        infection_obs_process_rv=observed_infections,
        Rt_process_rv=rt,
    )

    # Sampling and fitting model 1 (with obs infections)
    pad_size = 5
    with numpyro.handlers.seed(rng_seed=223):
        model1_samp = model1.sample(n_datapoints=30, padding=pad_size)

    model1.run(
        num_warmup=500,
        num_samples=500,
        rng_key=jr.key(22),
        data_observed_infections=model1_samp.observed_infections.value,
        padding=5,
    )

    inf = model1.spread_draws(["all_latent_infections"])

    inf_mean = (
        inf.group_by("draw")
        .agg(pl.col("all_latent_infections").mean())
        .sort(pl.col("draw"))
    )

    # For now the assertion is only about the expected number of rows
    # It should be about the MCMC inference.
    assert inf_mean.to_numpy().shape[0] == 500
