"""Structure-Adaptive Interventional Loop Closure contracts and safeguards."""

from .contracts import (
    SailContractError,
    assert_action_invariant,
    seal_contract,
    validate_contract,
    verify_contract,
    verify_source_binding,
)
from .belief_graph import build_belief_graph, compile_belief_graph, validate_graph
from .evidence import compile_campaign, inventory_campaign, load_campaign
from .residuals import build_residual_field, compile_residuals
from .structural_surprise import compile_structural_surprise, evaluate_surprise
from .mechanisms import load_mechanism_registry
from .posterior import compile_mechanisms, fit_structure_particle

__all__ = [
    "SailContractError",
    "assert_action_invariant",
    "seal_contract",
    "validate_contract",
    "verify_contract",
    "verify_source_binding",
    "compile_campaign",
    "inventory_campaign",
    "load_campaign",
    "build_residual_field",
    "compile_residuals",
    "build_belief_graph",
    "compile_belief_graph",
    "validate_graph",
    "compile_structural_surprise",
    "evaluate_surprise",
    "load_mechanism_registry",
    "compile_mechanisms",
    "fit_structure_particle",
]
