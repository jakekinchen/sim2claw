from __future__ import annotations

import json

import mujoco

from sim2claw.pawn_bg_f2_deformable_cap_compatibility import (
    CONTRACT_PATH,
    compile_signature,
    legacy_shoulder_spec_mutator,
    load_contract,
)
from sim2claw.scene import build_scene_spec


def test_contract_freezes_order_runtime_and_external_authority() -> None:
    contract = load_contract()
    assert [row["candidate_id"] for row in contract["candidate_order"]] == [
        "rigid_legacy_shoulder_control",
        "flex_10_kpa",
        "flex_25_kpa",
        "flex_63_kpa",
        "flex_158_kpa",
        "flex_400_kpa",
    ]
    assert contract["historical_runtime_identity"]["contact_cone"] == "elliptic"
    assert not any(contract["authority"].values())


def test_legacy_shoulder_mutator_changes_only_named_box_sizes() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    spec = build_scene_spec(piece_layout="sparse_two_sided_pawns")
    before = {}
    for body_name in ("left_shoulder", "right_shoulder"):
        body = spec.body(body_name)
        assert body is not None
        matches = [
            geom
            for geom in body.geoms
            if geom.type == mujoco.mjtGeom.mjGEOM_BOX
            and list(geom.size) == [0.0124, 0.015, 0.01]
        ]
        assert len(matches) == 1
        before[body_name] = matches[0]
    legacy_shoulder_spec_mutator(contract)(spec)
    assert [float(value) for value in before["left_shoulder"].size] == [
        0.023,
        0.015,
        0.01,
    ]
    assert [float(value) for value in before["right_shoulder"].size] == [
        0.023,
        0.015,
        0.01,
    ]


def test_rigid_compile_signature_matches_historical_model() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    signature = compile_signature(candidate_id="rigid_legacy_shoulder_control")
    assert signature["compiled_model_sha256"] == contract[
        "rigid_compatibility_reference"
    ]["compiled_model_sha256"]
    assert signature["cone"] == "mjCONE_ELLIPTIC"
    assert signature["solver"] == "mjSOL_NEWTON"
    assert signature["integrator"] == "mjINT_IMPLICITFAST"
    assert signature["timestep_seconds"] == 0.0022500000000000003
