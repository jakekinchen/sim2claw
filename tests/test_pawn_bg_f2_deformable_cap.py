from pathlib import Path

import mujoco
import numpy as np

from sim2claw.contact_prior import read_contact_prior_snapshot
from sim2claw.pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from sim2claw.pawn_bg_f2_deformable_cap import (
    _model_invariant_digest,
    flex_cap_spec_mutator,
    load_contract,
)
from sim2claw.pawn_bg_grasp_coordinate_descent import (
    CONTRACT_PATH as GRASP_CONTRACT_PATH,
    _custom_variant,
    load_grasp_coordinate_contract,
)
from sim2claw.pawn_bg_workcell_fit import build_workcell_model


REPO_ROOT = Path(__file__).resolve().parents[1]


def _models() -> tuple[mujoco.MjModel, mujoco.MjModel]:
    contract = load_contract()
    train, events = _load_partition(REPO_ROOT, "train")
    _parent, workcell, _stage, _details = _reconstruct_stage_d(train, events)
    grasp = load_grasp_coordinate_contract()
    snapshot = read_contact_prior_snapshot(
        REPO_ROOT / grasp["source"]["contact_prior_path"]
    )
    variant = _custom_variant(
        parameters=contract["rigid_parameters"],
        contract_path=GRASP_CONTRACT_PATH,
        contact_snapshot=snapshot,
    )
    rigid = build_workcell_model(workcell, contact_variant=variant)["model"]
    flex = build_workcell_model(
        workcell,
        contact_variant=variant,
        spec_mutator=flex_cap_spec_mutator(contract, 10000.0),
    )["model"]
    return rigid, flex


def test_contract_freezes_exact_episode_action_family_and_false_authority() -> None:
    contract = load_contract()
    assert contract["source_bindings"]["recording_id"] == (
        "20260719T032620Z-0c7e3d86"
    )
    assert contract["source_bindings"]["action_sha256"] == (
        "ff5845e886aa7f6e65ffa978f758ccb2777fcaac8a71bd51cd02171f61ebdb34"
    )
    assert [row["candidate_id"] for row in contract["candidate_order"]] == [
        "rigid_0p91_control",
        "flex_10_kpa",
        "flex_25_kpa",
        "flex_63_kpa",
        "flex_158_kpa",
        "flex_400_kpa",
    ]
    assert all(value is False for value in contract["authority"].values())


def test_flex_caps_compile_with_explicit_face_pins_and_isolated_contact_bit() -> None:
    _rigid, model = _models()
    assert model.nflex == 2
    for name, pinned_front in (
        ("or134_fixed_cap", True),
        ("or134_moving_cap", False),
    ):
        flex_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, name)
        node_start = int(model.flex_nodeadr[flex_id])
        node_count = int(model.flex_nodenum[flex_id])
        node_bodies = np.asarray(
            model.flex_nodebodyid[node_start : node_start + node_count], dtype=int
        )
        parent_name = (
            "left_gripper"
            if name == "or134_fixed_cap"
            else "left_moving_jaw_so101_v1"
        )
        parent_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, parent_name
        )
        assert node_count == 8
        if pinned_front:
            np.testing.assert_array_equal(node_bodies[:4], parent_id)
            assert np.all(node_bodies[4:] != parent_id)
        else:
            assert np.all(node_bodies[:4] != parent_id)
            np.testing.assert_array_equal(node_bodies[4:], parent_id)
        assert int(model.flex_contype[flex_id]) == 128
        assert int(model.flex_conaffinity[flex_id]) == 0
        assert int(model.flex_selfcollide[flex_id]) == 0
        assert int(model.flex_internal[flex_id]) == 0


def test_only_authorized_named_model_deltas_change() -> None:
    rigid, flex = _models()
    assert _model_invariant_digest(rigid, 128) == _model_invariant_digest(flex, 128)
    for geom_id in range(flex.ngeom):
        name = mujoco.mj_id2name(flex, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or ""
        if name.startswith((
            "left_rubber_tip_fixed_",
            "left_rubber_tip_moving_",
        )):
            assert int(flex.geom_contype[geom_id]) == 0
            assert int(flex.geom_conaffinity[geom_id]) == 0
            assert float(flex.geom_rgba[geom_id, 3]) == 0.0


def test_caps_have_no_forbidden_contact_during_zero_action_settle() -> None:
    _rigid, model = _models()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    for _ in range(100):
        mujoco.mj_step(model, data)
    cap_ids = {
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, "or134_fixed_cap"),
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, "or134_moving_cap"),
    }
    for contact_index in range(data.ncon):
        flex_ids = set(int(value) for value in data.contact[contact_index].flex)
        assert not bool(flex_ids & cap_ids)
