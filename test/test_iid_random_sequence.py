# numpydoc ignore=GL08

import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
import pytest
from scipy.stats import kstest

from pyrenew.process import IIDRandomSequence, StandardNormalSequence
from pyrenew.randomvariable import (
    DistributionalVariable,
    StaticDistributionalVariable,
)


@pytest.mark.parametrize(
    ["distribution", "n"],
    [
        [dist.Normal(0, 1), 1000],
        [dist.Cauchy(2, 325.0), 13532],
        [dist.Normal(jnp.array([2.0, 3.0, -5.235]), 0.25), 622],
    ],
)
def test_iidrandomsequence_with_dist_rv(distribution, n):
    """
    Check that an IIDRandomSequence can be
    initialized and sampled from when the element_rv is
    a distributional RV, including with array-valued
    distributions
    """
    element_rv = DistributionalVariable("el_rv", distribution=distribution)
    rseq = IIDRandomSequence(element_rv=element_rv)
    if distribution.batch_shape == () or distribution.batch_shape == (1,):
        expected_shape = (n,)
    else:
        expected_shape = tuple([n] + [x for x in distribution.batch_shape])

    with numpyro.handlers.seed(rng_seed=62):
        ans_vec = rseq.sample(n=n, vectorize=True)
        ans_serial = rseq.sample(n=n, vectorize=False)

    # check that samples are the right type
    for ans in [ans_serial, ans_vec]:
        # check that the samples are of the right shape
        assert ans.shape == expected_shape

    # vectorized and unvectorized sampling should
    # not give the same answer
    # but they should give similar distributions
    assert all(ans_serial.flatten() != ans_vec.flatten())

    if expected_shape == (n,):
        kstest_out = kstest(ans_serial, ans_vec)
        assert kstest_out.pvalue > 0.01


@pytest.mark.parametrize(
    ["shape", "n"],
    [[None, 352], [(), 72352], [(5,), 5432], [(3, 23, 2), 10352]],
)
def test_standard_normal_sequence(shape, n):
    """
    Test the StandardNormalSequence RandomVariable
    class.
    """
    norm_seq = StandardNormalSequence(
        "test_norm_elements", element_shape=shape
    )

    # should be implemented with a DistributionalVariable
    # that is a standard normal
    assert isinstance(norm_seq.element_rv, StaticDistributionalVariable)
    if shape is None or shape == ():
        assert isinstance(norm_seq.element_rv.distribution, dist.Normal)
        el_dist = norm_seq.element_rv.distribution
    else:
        assert isinstance(
            norm_seq.element_rv.distribution, dist.ExpandedDistribution
        )
        assert isinstance(
            norm_seq.element_rv.distribution.base_dist, dist.Normal
        )
        el_dist = norm_seq.element_rv.distribution.base_dist
    assert el_dist.loc == 0.0
    assert el_dist.scale == 1.0

    # should be sampleable
    with numpyro.handlers.seed(rng_seed=67):
        ans = norm_seq(n=n)

    # samples should have shape (n,) + the element_rv sample shape
    expected_sample_shape = (n,) + shape if shape is not None else (n,)
    assert jnp.shape(ans) == expected_sample_shape

    with numpyro.handlers.seed(rng_seed=35):
        ans = norm_seq.sample(n=50000)

    # samples should be approximately standard normal
    kstest_out = kstest(ans.flatten(), "norm", (0, 1))

    assert kstest_out.pvalue > 0.01
