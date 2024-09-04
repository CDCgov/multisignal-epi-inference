"""
pyrenew helper classes
"""

from abc import ABCMeta, abstractmethod
from typing import NamedTuple, get_type_hints

import jax
import jax.numpy as jnp
import jax.random as jr
import matplotlib.pyplot as plt
import numpy as np
import numpyro
import numpyro.util
import polars as pl
from jax.typing import ArrayLike
from numpyro.distributions import constraints
from numpyro.distributions.util import promote_shapes, validate_sample
from numpyro.infer import MCMC, NUTS, Predictive

from pyrenew.mcmcutils import plot_posterior, spread_draws


def _assert_type(arg_name: str, value, expected_type) -> None:
    """
    Matches TypeError arising during validation

    Parameters
    ----------
    arg_name : str
        Name of the argument
    value : object
        The object to be validated
    expected_type : type
        The expected object type

    Raises
    -------
    TypeError
        If `value` is not an instance of `expected_type`.

    Returns
    -------
    None
    """

    if not isinstance(value, expected_type):
        raise TypeError(
            f"{arg_name} must be an instance of {expected_type}. "
            f"Got {type(value)}"
        )


def _assert_sample_and_rtype(
    rp: "RandomVariable", skip_if_none: bool = True
) -> None:
    """
    Return type-checking for RandomVariable's sample function

    Objects passed as `RandomVariable` should (a) have a `sample()` method that
    (b) returns either a tuple or a named tuple.

    Parameters
    ----------
    rp : RandomVariable
        Random variable to check.
    skip_if_none : bool, optional
        When `True` it returns if `rp` is None. Defaults to True.

    Returns
    -------
    None

    Raises
    ------
    Exception
        If rp is not a RandomVariable, does not have a sample function, or
        does not return a tuple. Also occurs if rettype does not initialized
        properly.
    """

    # Addressing the None case
    if (rp is None) and (not skip_if_none):
        Exception(
            "The passed object cannot be None. It should be RandomVariable"
        )
    elif skip_if_none and (rp is None):
        return None

    if not isinstance(rp, RandomVariable):
        raise Exception(f"{rp} is not an instance of RandomVariable.")

    # Otherwise, checking for the sample function (must have one)
    # with a defined rtype.
    try:
        sfun = rp.sample
    except Exception:
        raise Exception(
            f"The RandomVariable {rp} does not have a sample function."
        )  # noqa: E722

    # Getting the return annotation (if any)
    rettype = get_type_hints(sfun).get("return", None)

    if rettype is None:
        raise Exception(
            f"The RandomVariable {rp} does not have return type "
            + "annotation."
        )

    try:
        if not isinstance(rettype(), tuple):
            raise Exception(
                f"The RandomVariable {rp}'s return type annotation is not"
                + "a tuple"
            )
    except Exception:
        raise Exception(
            f"There was a problem when trying to initialize {rettype}."
            + "the rtype of the random variable should be a tuple or a namedtuple"
            + " with default values."
        )

    return None


class SampledValue(NamedTuple):
    """
    A container for a value sampled from a RandomVariable.

    Attributes
    ----------
    value : ArrayLike, optional
        The sampled value.
    t_start : int, optional
        The start time of the value.
    t_unit : int, optional
        The unit of time relative to the model's fundamental
        (smallest) time unit.
    """

    value: ArrayLike | None = None
    t_start: int | None = None
    t_unit: int | None = None

    def __repr__(self):
        return f"SampledValue(value={self.value}, t_start={self.t_start}, t_unit={self.t_unit})"


class RandomVariable(metaclass=ABCMeta):
    """
    Abstract base class for latent and observed random variables.

    Notes
    -----
    RandomVariables in pyrenew can be time-aware, meaning that they can
    have a t_start and t_unit attribute. These attributes
    are expected to be used internally mostly for tasks including padding,
    alignment of time series, and other time-aware operations.

    Both attributes give information about the output of the `sample()` method,
    in other words, the relative time units of the returning value.

    Attributes
    ----------
    t_start : int
        The start of the time series.
    t_unit : int
        The unit of the time series relative to the model's fundamental
        (smallest) time unit. e.g. if the fundamental unit is days,
        then 1 corresponds to units of days and 7 to units of weeks.
    """

    t_start: int = None
    t_unit: int = None

    def __init__(self, **kwargs):
        """
        Default constructor
        """
        pass

    def set_timeseries(
        self,
        t_start: int,
        t_unit: int,
    ) -> None:
        """
        Set the time series start and unit

        Parameters
        ----------
        t_start : int
            The start of the time series relative to the
            model time. It could be negative, indicating
            that the `sample()` method returns timepoints
            that occur prior to the model t = 0.
        t_unit : int
            The unit of the time series relative
            to the model's fundamental (smallest)
            time unit. e.g. if the fundamental unit
            is days, then 1 corresponds to units of
            days and 7 to units of weeks.

        Returns
        -------
        None
        """

        # Either both values are None or both are not None
        assert (t_unit is not None and t_start is not None) or (
            t_unit is None and t_start is None
        ), (
            "Both t_start and t_unit should be None or not None. "
            "Currently, t_start is {t_start} and t_unit is {t_unit}."
        )

        if t_unit is None and t_start is None:
            return None

        # Timeseries unit should be a positive integer
        assert isinstance(
            t_unit, int
        ), f"t_unit should be an integer. It is {type(t_unit)}."

        # Timeseries unit should be a positive integer
        assert (
            t_unit > 0
        ), f"t_unit should be a positive integer. It is {t_unit}."

        # Data starts should be a positive integer
        assert isinstance(
            t_start, int
        ), f"t_start should be an integer. It is {type(t_start)}."

        self.t_start = t_start
        self.t_unit = t_unit

        return None

    @abstractmethod
    def sample(
        self,
        **kwargs,
    ) -> tuple:
        """
        Sample method of the process

        The method design in the class should have at least kwargs.

        Parameters
        ----------
        **kwargs : dict, optional
            Additional keyword arguments passed through to internal `sample()`
            calls, should there be any.

        Returns
        -------
        tuple
        """
        pass

    @staticmethod
    @abstractmethod
    def validate(**kwargs) -> None:
        """
        Validation of kwargs to be implemented in subclasses.
        """
        pass

    def __call__(self, **kwargs):
        """
        Alias for `sample()`.
        """
        return self.sample(**kwargs)


class Model(metaclass=ABCMeta):
    """Abstract base class for models"""

    # Since initialized in none, values not shared across instances
    kernel = None
    mcmc = None

    @abstractmethod
    def __init__(self, **kwargs) -> None:  # numpydoc ignore=GL08
        pass

    @staticmethod
    @abstractmethod
    def validate() -> None:  # numpydoc ignore=GL08
        pass

    @abstractmethod
    def sample(
        self,
        **kwargs,
    ) -> tuple:
        """
        Sample method of the model.

        The method design in the class should have at least kwargs.

        Parameters
        ----------
        **kwargs : dict, optional
            Additional keyword arguments passed through to internal
            `sample()` calls, should there be any.

        Returns
        -------
        tuple
        """
        pass

    def model(self, **kwargs) -> tuple:
        """
        Alias for the sample method.

        Parameters
        ----------
        **kwargs : dict, optional
            Additional keyword arguments passed through to internal `sample()`
            calls, should there be any.

        Returns
        -------
        tuple
        """
        return self.sample(**kwargs)

    def _init_model(
        self,
        num_warmup,
        num_samples,
        nuts_args: dict = None,
        mcmc_args: dict = None,
    ) -> None:
        """
        Creates the NUTS kernel and MCMC model

        Parameters
        ----------
        nuts_args : dict, optional
            Dictionary of arguments passed to NUTS. Defaults to None.
        mcmc_args : dict, optional
            Dictionary of arguments passed to the MCMC sampler. Defaults to
            None.

        Returns
        -------
        None
        """

        if nuts_args is None:
            nuts_args = dict()

        if "find_heuristic_step_size" not in nuts_args:
            nuts_args["find_heuristic_step_size"] = True

        if mcmc_args is None:
            mcmc_args = dict()

        self.kernel = NUTS(
            model=self.model,
            **nuts_args,
        )

        self.mcmc = MCMC(
            self.kernel,
            num_warmup=num_warmup,
            num_samples=num_samples,
            **mcmc_args,
        )

        return None

    def run(
        self,
        num_warmup,
        num_samples,
        rng_key: ArrayLike | None = None,
        nuts_args: dict = None,
        mcmc_args: dict = None,
        **kwargs,
    ) -> None:
        """
        Runs the model

        Parameters
        ----------
        nuts_args : dict, optional
            Dictionary of arguments passed to the
            :class:`numpyro.infer.NUTS` kernel.
            Defaults to None.
        mcmc_args : dict, optional
            Dictionary of arguments passed to the
            :class:`numpyro.infer.MCMC` constructor.
            Defaults to None.

        Returns
        -------
        None
        """

        self._init_model(
            num_warmup=num_warmup,
            num_samples=num_samples,
            nuts_args=nuts_args,
            mcmc_args=mcmc_args,
        )
        if rng_key is None:
            rand_int = np.random.randint(
                np.iinfo(np.int64).min, np.iinfo(np.int64).max
            )
            rng_key = jr.key(rand_int)

        self.mcmc.run(rng_key=rng_key, **kwargs)

        return None

    def print_summary(
        self,
        prob: float = 0.9,
        exclude_deterministic: bool = True,
    ) -> None:
        """
        A wrapper of :meth:`numpyro.infer.MCMC.print_summary`

        Parameters
        ----------
        prob : float, optional
            The width of the credible interval to show. Default 0.9
        exclude_deterministic : bool, optional
            Whether to print deterministic sites in the summary.
            Defaults to True.

        Returns
        -------
        None
        """
        return self.mcmc.print_summary(prob, exclude_deterministic)

    def spread_draws(self, variables_names: list) -> pl.DataFrame:
        """
        A wrapper of mcmcutils.spread_draws

        Parameters
        ----------
        variables_names : list
            A list of variable names to create a table of samples.

        Returns
        -------
        pl.DataFrame
        """

        return spread_draws(self.mcmc.get_samples(), variables_names)

    def plot_posterior(
        self,
        var: list,
        obs_signal: jax.typing.ArrayLike = None,
        xlab: str = None,
        ylab: str = "Signal",
        samples: int = 50,
        figsize: list = [4, 5],
        draws_col: str = "darkblue",
        obs_col: str = "black",
    ) -> plt.Figure:  # numpydoc ignore=RT01
        """A wrapper of pyrenew.mcmcutils.plot_posterior"""
        return plot_posterior(
            var=var,
            draws=self.spread_draws([(var, "time")]),
            xlab=xlab,
            ylab=ylab,
            samples=samples,
            obs_signal=obs_signal,
            figsize=figsize,
            draws_col=draws_col,
            obs_col=obs_col,
        )

    def posterior_predictive(
        self,
        rng_key: ArrayLike | None = None,
        numpyro_predictive_args: dict = {},
        **kwargs,
    ) -> dict:
        """
        A wrapper for :class:`numpyro.infer.Predictive` to generate
        posterior predictive samples.

        Parameters
        ----------
        rng_key : ArrayLike, optional
            Random key for the Predictive function call. Defaults to None.
        numpyro_predictive_args : dict, optional
            Dictionary of arguments to be passed to the
            :class:`numpyro.infer.Predictive` constructor.
        **kwargs
            Additional named arguments passed to the
            `__call__()` method of :class:`numpyro.infer.Predictive`

        Returns
        -------
        dict
        """
        if self.mcmc is None:
            raise ValueError(
                "No posterior samples available. Run model with model.run()."
            )

        if rng_key is None:
            rand_int = np.random.randint(
                np.iinfo(np.int64).min, np.iinfo(np.int64).max
            )
            rng_key = jr.key(rand_int)

        predictive = Predictive(
            model=self.model,
            posterior_samples=self.mcmc.get_samples(),
            **numpyro_predictive_args,
        )

        return predictive(rng_key, **kwargs)

    def prior_predictive(
        self,
        rng_key: ArrayLike | None = None,
        numpyro_predictive_args: dict = {},
        **kwargs,
    ) -> dict:
        """
        A wrapper for numpyro.infer.Predictive to generate prior predictive samples.

        Parameters
        ----------
        rng_key : ArrayLike, optional
            Random key for the Predictive function call. Defaults to None.
        numpyro_predictive_args : dict, optional
            Dictionary of arguments to be passed to the numpyro.infer.Predictive constructor.
        **kwargs
            Additional named arguments passed to the `__call__()` method of numpyro.infer.Predictive

        Returns
        -------
        dict
        """

        if rng_key is None:
            rand_int = np.random.randint(
                np.iinfo(np.int64).min, np.iinfo(np.int64).max
            )
            rng_key = jr.key(rand_int)

        predictive = Predictive(
            model=self.model,
            posterior_samples=None,
            **numpyro_predictive_args,
        )

        return predictive(rng_key, **kwargs)


class CensoredNormal(numpyro.distributions.Distribution):
    """
    Censored normal distribution under which samples
    are truncated to lie within a specified interval.
    This implementation is adapted from
    https://github.com/dylanhmorris/host-viral-determinants/blob/main/src/distributions.py
    """

    arg_constraints = {"loc": constraints.real, "scale": constraints.positive}
    support = constraints.real

    def __init__(
        self,
        loc=0,
        scale=1,
        lower_limit=-jnp.inf,
        upper_limit=jnp.inf,
        validate_args=None,
    ):
        """
        Default constructor

        Parameters
        ----------
        loc : ArrayLike or float, optional
            The mean of the normal distribution.
            Defaults to 0.
        scale : ArrayLike or float, optional
            The standard deviation of the normal
            distribution. Must be positive. Defaults to 1.
        lower_limit : float, optional
            The lower bound of the interval for censoring.
            Defaults to -inf (no lower bound).
        upper_limit : float, optional
            The upper bound of the interval for censoring.
            Defaults to inf (no upper bound).
        validate_args : bool, optional
            If True, checks if parameters are valid.
            Defaults to None.

        Returns
        -------
        None
        """
        self.loc, self.scale = promote_shapes(loc, scale)
        self.lower_limit = lower_limit
        self.upper_limit = upper_limit

        batch_shape = jax.lax.broadcast_shapes(
            jnp.shape(loc), jnp.shape(scale)
        )
        self.normal_ = numpyro.distributions.Normal(
            loc=loc, scale=scale, validate_args=validate_args
        )
        super().__init__(batch_shape=batch_shape, validate_args=validate_args)

    def sample(self, key, sample_shape=()):
        """
        Generates samples from the censored normal distribution.

        Returns
        -------
        Array
            Containing samples from the censored normal distribution.
        """
        assert numpyro.util.is_prng_key(key)
        result = self.normal_.sample(key, sample_shape)
        return jnp.clip(result, min=self.lower_limit, max=self.upper_limit)

    @validate_sample
    def log_prob(self, value):
        """
        Computes the log probability density of a given value(s) under
        the censored normal distribution.

        Returns
        -------
        Array
            Containing log probability of the given value(s)
            under the censored normal distribution
        """
        rescaled_ulim = (self.upper_limit - self.loc) / self.scale
        rescaled_llim = (self.lower_limit - self.loc) / self.scale
        lim_val = jnp.where(
            value <= self.lower_limit,
            jax.scipy.special.log_ndtr(rescaled_llim),
            jax.scipy.special.log_ndtr(-rescaled_ulim),
        )
        # we exploit the fact that for the
        # standard normal, P(x > a) = P(-x < a)
        # to compute the log complementary CDF
        inbounds = jnp.logical_and(
            value > self.lower_limit, value < self.upper_limit
        )
        result = jnp.where(inbounds, self.normal_.log_prob(value), lim_val)

        return result
