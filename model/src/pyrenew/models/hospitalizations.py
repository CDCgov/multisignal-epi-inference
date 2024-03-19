#!/usr/bin/env/python
# -*- coding: utf-8 -*-

from collections import namedtuple

from pyrenew.metaclasses import Model, RandomProcess, _assert_sample_and_rtype
from pyrenew.models.rtinfectionsrenewal import RtInfectionsRenewalModel
from pyrenew.processes import RtRandomWalkProcess

HospModelSample = namedtuple(
    "HospModelSample",
    [
        "Rt",
        "infections",
        "IHR",
        "latent",
        "sampled",
    ],
    defaults=[None, None, None, None, None],
)
"""Output from HospitalizationsModel.sample()
"""


class HospitalizationsModel(Model):
    """HospitalAdmissions Model (BasicRenewal + HospitalAdmissions)

    This class inherits from pyrenew.models.Model. It extends the
    basic renewal model by adding a hospitalization module, e.g.,
    pyrenew.observations.HospitalAdmissions.
    """

    def __init__(
        self,
        latent_hospitalizations: RandomProcess,
        latent_infections: RandomProcess,
        observed_hospitalizations: RandomProcess = None,
        Rt_process: RandomProcess = RtRandomWalkProcess(),
    ) -> None:
        """Default constructor

        Parameters
        ----------
        latent_hospitalizations : RandomProcess
            Latent process for the hospitalizations.
        observed_hospitalizations : RandomProcess
            Observation process for the hospitalizations.
        latent_infections : RandomProcess
            The infections latent process (passed to RtInfectionsRenewalModel).
        Rt_process : RandomProcess, optional
            Rt process  (passed to RtInfectionsRenewalModel).

        Returns
        -------
        None
        """
        self.basic_renewal = RtInfectionsRenewalModel(
            latent_infections=latent_infections,
            observed_infections=None,
            Rt_process=Rt_process,
        )

        HospitalizationsModel.validate(
            latent_hospitalizations, observed_hospitalizations
        )

        self.latent_hospitalizations = latent_hospitalizations
        self.observed_hospitalizations = observed_hospitalizations

    @staticmethod
    def validate(latent_hospitalizations, observed_hospitalizations) -> None:
        _assert_sample_and_rtype(latent_hospitalizations, skip_if_none=False)
        _assert_sample_and_rtype(observed_hospitalizations, skip_if_none=True)
        return None

    def sample_hospitalizations_latent(
        self,
        random_variables: dict,
        constants: dict = None,
    ) -> tuple:
        return self.latent_hospitalizations.sample(
            random_variables=random_variables,
            constants=constants,
        )

    def sample_hospitalizations_obs(
        self,
        random_variables: dict,
        constants: dict = None,
    ) -> tuple:
        """Sample number of hospitalizations

        Parameters
        ----------
        random_variables : dict
            A dictionary containing `infections` passed to the specified
            sampler.
        constants : dict, optional
            Possible constants for the model.

        Returns
        -------
        tuple
        """

        if self.observed_hospitalizations is None:
            return (None,)

        return self.observed_hospitalizations.sample(
            random_variables=random_variables,
            constants=constants,
        )

    def sample(
        self,
        random_variables: dict = None,
        constants: dict = None,
    ) -> HospModelSample:
        """Sample from the HospitalAdmissions model

        Parameters
        ----------
        random_variables : dict, optional
            A dictionary with random variables passed to
            `pyrenew.models.RtInfectionsRenewalModel` and `sample_hospitalizations`.
        constants : dict, optional
            Possible constants for the model.

        Returns
        -------
        HospModelSample
        """
        if random_variables is None:
            random_variables = dict()

        if constants is None:
            constants = dict()

        # Getting the basline quantities from the basic model
        Rt, infections, *_ = self.basic_renewal.sample(
            constants=constants,
            random_variables=random_variables,
        )

        # Sampling the latent hospitalizations
        (
            IHR,
            latent,
            *_,
        ) = self.sample_hospitalizations_latent(
            random_variables={
                **random_variables,
                **dict(infections=infections),
            },
            constants=constants,
        )

        # Sampling the hospitalizations
        sampled, *_ = self.sample_hospitalizations_obs(
            random_variables={
                **random_variables,
                **dict(latent=latent),
            },
            constants=constants,
        )

        return HospModelSample(
            Rt=Rt,
            infections=infections,
            IHR=IHR,
            latent=latent,
            sampled=sampled,
        )
