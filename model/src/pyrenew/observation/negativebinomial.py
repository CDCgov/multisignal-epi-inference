# -*- coding: utf-8 -*-

import numbers as nums

import numpyro
import numpyro.distributions as dist
from jax.typing import ArrayLike
from pyrenew.metaclass import RandomVariable


class NegativeBinomialObservation(RandomVariable):
    """Negative Binomial observation"""

    def __init__(
        self,
        concentration_prior: dist.Distribution | ArrayLike,
        concentration_suffix: str = "_concentration",
        parameter_name="negbinom_rv",
        eps: float = 1e-10,
    ) -> None:
        """Default constructor

        Parameters
        ----------
        concentration_prior : dist.Distribution | numbers.nums
            Numpyro distribution from which to sample the positive concentration
            parameter of the negative binomial. This parameter is sometimes
            called k, phi, or the "dispersion" or "overdispersion" parameter,
            despite the fact that larger values imply that the distribution
            becomes more Poissonian, while smaller ones imply a greater degree
            of dispersion.
        concentration_suffix : str, optional
            Suffix for the numpy variable.
        parameter_name : str, optional
            Name for the numpy variable.
        eps : float, optional
            Small value to add to the predicted mean to prevent numerical
            instability.

        Returns
        -------
        None
        """

        NegativeBinomialObservation.validate(concentration_prior)

        if isinstance(concentration_prior, dist.Distribution):
            self.sample_prior = lambda: numpyro.sample(
                self.parameter_name + self.concentration_suffix,
                concentration_prior,
            )
        else:
            self.sample_prior = lambda: concentration_prior

        self.parameter_name = parameter_name
        self.concentration_suffix = concentration_suffix
        self.eps = eps

    def sample(
        self,
        predicted: ArrayLike,
        obs: ArrayLike = None,
        **kwargs,
    ) -> tuple:
        """Sample from the negative binomial distribution

        Parameters
        ----------
        predicted : ArrayLike
            Mean parameter of the negative binomial distribution.
        obs : ArrayLike, optional
            Observed data, by default None.
        **kwargs : dict, optional
            Additional keyword arguments passed through to internal `sample()`
            calls, if any

        Returns
        -------
        tuple
        """
        concentration = self.sample_prior()

        return (
            numpyro.sample(
                self.parameter_name,
                dist.NegativeBinomial2(
                    mean=predicted + self.eps,
                    concentration=concentration,
                ),
                obs=obs,
            ),
        )

    @staticmethod
    def validate(concentration_prior) -> None:
        assert isinstance(
            concentration_prior, (dist.Distribution, nums.Number)
        )
        return None
