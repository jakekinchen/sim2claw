from __future__ import annotations

from sim2claw.pawn_bg_f2_deformable_cap_source_boundary import (
    compile_signature,
    load_contract,
    load_raw_contract,
)


def test_source_boundary_contract_inherits_unchanged_family_and_gates() -> None:
    raw = load_raw_contract()
    contract = load_contract()
    assert raw["source_boundary_reconstruction"][
        "historical_compatibility_uses_only_source_boundary_metric"
    ]
    assert raw["source_boundary_reconstruction"][
        "strict_evaluator_uses_full_integration_step_trace"
    ]
    assert [row["candidate_id"] for row in contract["candidate_order"]] == [
        "rigid_legacy_shoulder_control",
        "flex_10_kpa",
        "flex_25_kpa",
        "flex_63_kpa",
        "flex_158_kpa",
        "flex_400_kpa",
    ]
    assert contract["supplemental_gates"]["maximum_tilt_degrees_every_step"] == 10.0
    assert not any(contract["authority"].values())


def test_source_boundary_rigid_compile_signature_is_historical_model() -> None:
    contract = load_contract()
    signature = compile_signature(candidate_id="rigid_legacy_shoulder_control")
    assert signature["compiled_model_sha256"] == contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]
    assert signature["nflex"] == 0
    assert signature["timestep_seconds"] == 0.0022500000000000003
