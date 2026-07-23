"""Shared immutable types and version identities for the SAIL live operator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .contracts import SailContractError
from .mechanisms import MechanismPlugin


CONFIG_SCHEMA = "sim2claw.sail_live_campaign.v2"
RECEIPT_SCHEMA = "sim2claw.sail_live_operator_receipt.v3"
CANONICAL_STATE_ROOT = "outputs/sail/live-campaign-state-v1"
STATE_KEY_SCHEMA = "sim2claw.sail_live_campaign_state_key.v1"


class LiveOperatorError(SailContractError):
    """A live campaign escaped its frozen evidence, budget, or authority."""


@dataclass(frozen=True)
class LiveMechanism:
    mechanism_id: str
    family: str
    prior_probability: float
    plugin: MechanismPlugin


@dataclass(frozen=True)
class LiveIntervention:
    intervention_id: str
    kind: str
    availability: str
    maximum_trials: int
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class LiveCampaignContract:
    path: Path
    payload: Mapping[str, Any]
    source_paths: Mapping[str, Path]
    mechanisms: tuple[LiveMechanism, ...]
    interventions: tuple[LiveIntervention, ...]
    action_sha256: str
    evaluator_digest: str
    intervention_set_digest: str
    config_digest: str
    residual_artifact: Mapping[str, Any]

    @property
    def campaign_id(self) -> str:
        return str(self.payload["campaign_id"])

    @property
    def budget(self) -> Mapping[str, Any]:
        return self.payload["budget"]

    @property
    def hypothesis_priors(self) -> dict[str, float]:
        return {
            row.mechanism_id: row.prior_probability for row in self.mechanisms
        }


__all__ = [
    "CANONICAL_STATE_ROOT",
    "CONFIG_SCHEMA",
    "RECEIPT_SCHEMA",
    "STATE_KEY_SCHEMA",
    "LiveCampaignContract",
    "LiveIntervention",
    "LiveMechanism",
    "LiveOperatorError",
]
