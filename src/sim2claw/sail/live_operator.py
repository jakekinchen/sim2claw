"""Public facade for the modular SAIL live decision/evidence operator."""

from __future__ import annotations

from .live_adapters import build_trusted_adapter_request
from .live_contracts import load_live_campaign_contract
from .live_decision import (
    apply_live_sparse_closure,
    build_live_belief_graph,
    rank_live_acquisition,
    update_discrete_structure_posterior,
    validate_live_residual_evidence,
)
from .live_receipts import (
    build_live_evaluator_identity,
    verify_live_operator_migration_receipt,
    verify_live_operator_receipt,
)
from .live_runtime import run_live_operator
from .live_state import resolve_live_campaign_state_path
from .live_types import (
    CANONICAL_STATE_ROOT,
    CONFIG_SCHEMA,
    LiveCampaignContract,
    LiveIntervention,
    LiveMechanism,
    LiveOperatorError,
)


__all__ = [
    "CANONICAL_STATE_ROOT",
    "CONFIG_SCHEMA",
    "LiveCampaignContract",
    "LiveIntervention",
    "LiveMechanism",
    "LiveOperatorError",
    "apply_live_sparse_closure",
    "build_live_belief_graph",
    "build_live_evaluator_identity",
    "build_trusted_adapter_request",
    "load_live_campaign_contract",
    "rank_live_acquisition",
    "resolve_live_campaign_state_path",
    "run_live_operator",
    "update_discrete_structure_posterior",
    "validate_live_residual_evidence",
    "verify_live_operator_migration_receipt",
    "verify_live_operator_receipt",
]
