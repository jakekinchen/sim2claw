"""CPU/fp32 consequence evaluator for canonical pawn source episodes.

The evaluator replays the exact recorded float32 joint targets under the
deployed 20 Hz / ten-physics-step sample-hold contract.  It protects every one
of the fifteen non-target pawns and owns admission; recorder labels do not.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .grasp import _jaw_body_ids, _piece_bodies, _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    registered_board_center,
)
from .source_episode import (
    ADMISSION_SCHEMA,
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    KNOWN_CONTRACT_PATHS,
    admission_payload_sha256,
    load_source_contract,
    load_source_episode,
    sha256_file,
    source_contract_sha256,
)


EVALUATOR_PATH_V1 = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_pawn_evaluator_v1.json"
)
EVALUATOR_PATH_V2 = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_pawn_evaluator_v2.json"
)
EVALUATOR_PATH = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_pawn_evaluator_v3.json"
)
KNOWN_EVALUATOR_PATHS = (EVALUATOR_PATH, EVALUATOR_PATH_V2, EVALUATOR_PATH_V1)
EVALUATOR_SCHEMAS = {
    "chess_pick_place_pawn_evaluator_v1": (
        "sim2claw.chess_pick_place_pawn_evaluator.v1"
    ),
    "chess_pick_place_pawn_evaluator_v2": (
        "sim2claw.chess_pick_place_pawn_evaluator.v2"
    ),
    "chess_pick_place_pawn_evaluator_v3": (
        "sim2claw.chess_pick_place_pawn_evaluator.v3"
    ),
}


def pawn_evaluator_sha256(path: Path = EVALUATOR_PATH) -> str:
    return sha256_file(path)


def load_pawn_evaluator_contract(path: Path = EVALUATOR_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    evaluator_id = str(contract.get("evaluator_id") or "")
    if contract.get("schema_version") != EVALUATOR_SCHEMAS.get(evaluator_id):
        raise ValueError("unsupported pawn evaluator contract")
    if not contract.get("frozen_before_training"):
        raise ValueError("pawn evaluator must be frozen before training")
    if contract.get("owner") != "separate_cpu_fp32_consequence_evaluator":
        raise ValueError("pawn evaluator ownership changed")
    if contract.get("device") != "cpu" or contract.get("dtype") != "float32":
        raise ValueError("pawn evaluator must remain CPU/fp32")
    scene = contract["scene"]
    expected_scene = {
        "chess_pick_place_pawn_evaluator_v1": (
            "operator_updated_chess_workcell_v2",
            "board_robotward_72mm_20260718_v2",
            [0.04, -0.093],
        ),
        "chess_pick_place_pawn_evaluator_v2": (
            CURRENT_SCENE_ID,
            CURRENT_BOARD_POSE_ID,
            [0.04, -0.065],
        ),
        "chess_pick_place_pawn_evaluator_v3": (
            CURRENT_SCENE_ID,
            CURRENT_BOARD_POSE_ID,
            [0.04, -0.065],
        ),
    }[evaluator_id]
    if (
        scene.get("scene_id") != expected_scene[0]
        or scene.get("board_pose_id") != expected_scene[1]
        or scene.get("piece_layout") != CURRENT_TASK_PIECE_LAYOUT
        or scene.get("board_center_in_table_frame_xy_m") != expected_scene[2]
    ):
        raise ValueError("pawn evaluator workcell identity changed")
    protected = list(scene.get("protected_piece_ids") or [])
    if len(protected) != 16 or len(set(protected)) != 16:
        raise ValueError("pawn evaluator must protect exactly sixteen unique pieces")
    execution = contract["execution"]
    if (
        int(execution.get("sample_hold_hz", 0)) != 20
        or int(execution.get("physics_steps_per_action", 0)) != 10
        or not math.isclose(
            float(execution.get("physics_timestep_seconds", 0.0)),
            0.005,
            abs_tol=1e-12,
        )
        or execution.get("action_dtype") != "float32"
    ):
        raise ValueError("pawn evaluator execution contract changed")
    if not execution.get("exact_final_mjstate_match_required_for_replay_admission"):
        raise ValueError("pawn evaluator must require exact replay-state equality")
    gates = contract["gates"]
    for requirement in (
        "require_selected_piece_identity",
        "require_no_wrong_piece_contact",
        "require_no_final_jaw_contact",
        "require_no_assistance",
        "require_declared_action_owner",
        "require_all_recorded_actions_executed",
    ):
        if gates.get(requirement) is not True:
            raise ValueError(f"pawn evaluator requirement disabled: {requirement}")
    if int(contract["authority"].get("held_out_rows", -1)) != 0:
        raise ValueError("pawn evaluator must keep held-out rows at zero")
    source = None
    for source_path in KNOWN_CONTRACT_PATHS:
        candidate = load_source_contract(source_path)
        if candidate["contract_id"] == execution["source_contract_id"]:
            source = candidate
            break
    if source is None:
        raise ValueError("pawn evaluator references an unknown source contract")
    if source["contract_id"] != execution["source_contract_id"]:
        raise ValueError("pawn evaluator references the wrong source contract")
    if evaluator_id == "chess_pick_place_pawn_evaluator_v3":
        reset = source["simulation_reset"]
        if execution.get("simulation_reset_id") != reset["reset_id"]:
            raise ValueError("pawn evaluator references the wrong simulation reset")
    return contract


def evaluator_path_for_scene(
    scene_id: str, *, source_contract_id: str | None = None
) -> Path:
    for path in KNOWN_EVALUATOR_PATHS:
        contract = json.loads(path.read_text(encoding="utf-8"))
        if (
            contract.get("scene", {}).get("scene_id") == scene_id
            and (
                source_contract_id is None
                or contract.get("execution", {}).get("source_contract_id")
                == source_contract_id
            )
        ):
            return path
    raise ValueError("source scene has no frozen pawn evaluator")


def _gate(measured: Any, comparison: str, threshold: Any) -> dict[str, Any]:
    if comparison == ">=":
        passed = measured >= threshold
    elif comparison == "<=":
        passed = measured <= threshold
    elif comparison == "==":
        passed = measured == threshold
    else:
        raise ValueError(f"unsupported gate comparison: {comparison}")
    return {
        "measured": measured,
        "comparison": comparison,
        "threshold": threshold,
        "passed": bool(passed),
    }


def score_pawn_consequences(
    measurements: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply every frozen gate to already measured consequences.

    This pure scoring boundary supports deterministic negative fixtures without
    granting a fixture, recorder, or training process evaluator authority.
    """

    evaluator = contract or load_pawn_evaluator_contract()
    thresholds = evaluator["gates"]
    gates = {
        "selected_piece_identity": _gate(
            bool(measurements["selected_piece_identity"]), "==", True
        ),
        "minimum_piece_rise": _gate(
            float(measurements["maximum_piece_rise_m"]),
            ">=",
            float(thresholds["minimum_piece_rise_m"]),
        ),
        "final_xy_error": _gate(
            float(measurements["final_xy_error_m"]),
            "<=",
            float(thresholds["maximum_final_xy_error_m"]),
        ),
        "final_height_error": _gate(
            float(measurements["final_height_error_m"]),
            "<=",
            float(thresholds["maximum_final_height_error_m"]),
        ),
        "final_upright_cosine": _gate(
            float(measurements["final_upright_cosine"]),
            ">=",
            float(thresholds["minimum_final_upright_cosine"]),
        ),
        "final_linear_speed": _gate(
            float(measurements["final_linear_speed_m_s"]),
            "<=",
            float(thresholds["maximum_final_linear_speed_m_s"]),
        ),
        "gripper_clearance": _gate(
            float(measurements["gripper_clearance_m"]),
            ">=",
            float(thresholds["minimum_gripper_clearance_m"]),
        ),
        "maximum_other_piece_displacement": _gate(
            float(measurements["maximum_other_piece_displacement_m"]),
            "<=",
            float(thresholds["maximum_other_piece_displacement_m"]),
        ),
        "target_not_ejected": _gate(
            float(measurements["target_displacement_m"]),
            "<=",
            float(thresholds["target_ejection_displacement_m"]),
        ),
        "no_wrong_piece_contact": _gate(
            bool(measurements["wrong_piece_contact"]), "==", False
        ),
        "no_final_jaw_contact": _gate(
            bool(measurements["final_jaw_piece_contact"]), "==", False
        ),
        "no_assistance": _gate(int(measurements["assistance_frames"]), "==", 0),
        "declared_action_owner": _gate(
            bool(measurements["declared_action_owner"]), "==", True
        ),
        "all_recorded_actions_executed": _gate(
            int(measurements["executed_action_count"]),
            "==",
            int(measurements["recorded_action_count"]),
        ),
        "exact_sample_hold_state_replay": _gate(
            bool(measurements["exact_sample_hold_state_replay"]), "==", True
        ),
    }
    return {
        "gates": gates,
        "success": all(bool(gate["passed"]) for gate in gates.values()),
    }


def _integration_state(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    state = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(
        model, data, state, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    return state


def _jaw_piece_contact(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    jaw_bodies: set[int],
    piece_body_ids: set[int],
) -> bool:
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        if bodies & jaw_bodies and bodies & piece_body_ids:
            return True
    return False


def _robot_piece_contact(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    robot_body_ids: set[int],
    piece_body_ids: set[int],
) -> bool:
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        if bodies & robot_body_ids and bodies & piece_body_ids:
            return True
    return False


def evaluate_source_episode(
    directory: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Replay and score one canonical source episode on CPU/fp32."""

    directory = directory.resolve()
    receipt, rows = load_source_episode(directory)
    evaluator_path = evaluator_path_for_scene(
        str(receipt.get("scene_id") or ""),
        source_contract_id=str(receipt.get("task_id") or ""),
    )
    evaluator = load_pawn_evaluator_contract(evaluator_path)
    evaluator_scene = evaluator["scene"]
    if receipt.get("scene_id") != evaluator_scene["scene_id"]:
        raise ValueError("source receipt uses the wrong scene identity")
    if receipt.get("board_pose_id") != evaluator_scene["board_pose_id"]:
        raise ValueError("source receipt uses the wrong board pose identity")
    if receipt.get("piece_layout") != CURRENT_TASK_PIECE_LAYOUT:
        raise ValueError("source receipt uses the wrong pawn layout")
    if int(receipt.get("sample_hz", 0)) != 20:
        raise ValueError("source receipt is not a 20 Hz episode")

    initial_path = directory / str(
        receipt["initial_evaluator_privileged_state_path"]
    )
    initial_payload = json.loads(initial_path.read_text(encoding="utf-8"))
    initial_state = np.asarray(
        initial_payload["state"]["integration_state_float64"], dtype=np.float64
    )
    privileged_rows = [
        json.loads(line)
        for line in (
            directory / str(receipt["evaluator_privileged_state_path"])
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    scene_id = str(receipt["scene_id"])
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(scene_id),
        include_visual_props=scene_id == CURRENT_SCENE_ID,
    ).compile()
    if not math.isclose(float(model.opt.timestep), 0.005, abs_tol=1e-12):
        raise ValueError("runtime MuJoCo timestep differs from the evaluator contract")
    data = mujoco.MjData(model)
    expected_state_size = mujoco.mj_stateSize(
        model, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    if initial_state.shape != (expected_state_size,):
        raise ValueError("initial integration state has the wrong size")
    mujoco.mj_setState(
        model, data, initial_state, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    mujoco.mj_forward(model, data)

    actuator_ids: list[int] = []
    for joint in ROBOT_JOINTS:
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}"
        )
        if actuator_id < 0:
            raise ValueError(f"runtime model is missing left_{joint}")
        actuator_ids.append(actuator_id)
    actuator_array = np.asarray(actuator_ids, dtype=np.int32)
    bounds = model.actuator_ctrlrange[actuator_array]

    piece_bodies = _piece_bodies(model)
    protected_names = set(evaluator["scene"]["protected_piece_ids"])
    if set(piece_bodies) != protected_names:
        raise ValueError("runtime pawn inventory differs from the frozen evaluator")
    target_name = str(receipt.get("piece_id") or "")
    if target_name not in protected_names:
        raise ValueError("source receipt selected an undeclared pawn")
    target_body = piece_bodies[target_name]
    other_body_ids = {
        body_id for name, body_id in piece_bodies.items() if name != target_name
    }
    jaw_bodies = _jaw_body_ids(model, "left")
    pinch_local = _pinch_offset(model, data, "left")
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_target_position = initial_positions[target_name]
    destination_square = str(receipt.get("destination_square") or "")
    if not destination_square:
        raise ValueError("source receipt is missing its destination square")
    target_position = board_square_center(
        destination_square,
        board_center_in_table_frame_xy_m=registered_board_center(scene_id),
    )
    target_pose = np.asarray(
        [*target_position, 1.0, 0.0, 0.0, 0.0], dtype=np.float64
    )

    maximum_height = float(data.xpos[target_body][2])
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""
        ).startswith("left_")
    }
    wrong_piece_contact = False
    selected_pose_matches: list[bool] = []
    target_pose_matches: list[bool] = []
    replay_state_matches: list[bool] = []
    executed = 0
    for row, privileged_row in zip(rows, privileged_rows, strict=True):
        action = np.asarray(row["action"]["joint_target_rad"], dtype=np.float32)
        if action.shape != (6,) or not np.isfinite(action).all():
            raise ValueError("source action is not a finite float32 six-vector")
        clipped = np.clip(action, bounds[:, 0], bounds[:, 1]).astype(np.float64)
        data.ctrl[actuator_array] = clipped
        for _ in range(10):
            mujoco.mj_step(model, data)
            wrong_piece_contact = wrong_piece_contact or _robot_piece_contact(
                model, data, robot_body_ids, other_body_ids
            )
            maximum_height = max(maximum_height, float(data.xpos[target_body][2]))
        expected_state = np.asarray(
            privileged_row["state"]["integration_state_float64"],
            dtype=np.float64,
        )
        replay_state_matches.append(
            expected_state.shape == (expected_state_size,)
            and np.array_equal(_integration_state(model, data), expected_state)
        )
        recorded_selected_pose = np.asarray(
            row["goal"]["selected_piece_pose_world"], dtype=np.float64
        )
        authoritative_selected_pose = np.asarray(
            [*data.xpos[target_body], *data.xquat[target_body]], dtype=np.float64
        )
        selected_pose_matches.append(
            recorded_selected_pose.shape == (7,)
            and np.array_equal(recorded_selected_pose, authoritative_selected_pose)
        )
        target_pose_matches.append(
            np.array_equal(
                np.asarray(
                    row["goal"]["continuous_target_pose_world"], dtype=np.float64
                ),
                target_pose,
            )
        )
        executed += 1

    final_position = np.asarray(data.xpos[target_body], dtype=np.float64)
    final_rotation = np.asarray(data.xmat[target_body], dtype=np.float64).reshape(3, 3)
    final_linear_speed = float(
        np.linalg.norm(np.asarray(data.cvel[target_body][3:], dtype=np.float64))
    )
    other_displacements = {
        name: float(np.linalg.norm(data.xpos[body_id] - initial_positions[name]))
        for name, body_id in piece_bodies.items()
        if name != target_name
    }
    worst_other_piece = max(other_displacements, key=other_displacements.get)
    final_jaw_contact = _jaw_piece_contact(
        model, data, jaw_bodies, set(piece_bodies.values())
    )
    declared_owners = {
        "human_teleoperator",
        "geometric_expert",
        "planner",
        "learned_policy",
    }
    measurements = {
        "selected_piece_identity": all(selected_pose_matches)
        and all(target_pose_matches),
        "maximum_piece_rise_m": maximum_height
        - float(initial_target_position[2]),
        "final_xy_error_m": float(
            np.linalg.norm(final_position[:2] - target_pose[:2])
        ),
        "final_height_error_m": float(abs(final_position[2] - target_pose[2])),
        "final_upright_cosine": float(final_rotation[2, 2]),
        "final_linear_speed_m_s": final_linear_speed,
        "gripper_clearance_m": float(
            np.linalg.norm(
                _pinch_point(model, data, "left", pinch_local) - final_position
            )
        ),
        "maximum_other_piece_displacement_m": other_displacements[
            worst_other_piece
        ],
        "target_displacement_m": float(
            np.linalg.norm(final_position - initial_target_position)
        ),
        "wrong_piece_contact": wrong_piece_contact,
        "final_jaw_piece_contact": final_jaw_contact,
        "assistance_frames": sum(int(row["action"]["assistance"]) for row in rows),
        "declared_action_owner": all(
            row["action"]["owner"] in declared_owners for row in rows
        ),
        "executed_action_count": executed,
        "recorded_action_count": len(rows),
        "exact_sample_hold_state_replay": all(replay_state_matches),
    }
    scored = score_pawn_consequences(measurements, evaluator)
    evaluator_identity = {
        "evaluator_module_sha256": sha256_file(Path(__file__)),
        "grasp_module_sha256": sha256_file(REPO_ROOT / "src/sim2claw/grasp.py"),
        "scene_module_sha256": sha256_file(REPO_ROOT / "src/sim2claw/scene.py"),
        "source_episode_module_sha256": sha256_file(
            REPO_ROOT / "src/sim2claw/source_episode.py"
        ),
    }
    verdict = {
        "schema_version": ADMISSION_SCHEMA,
        "evaluator_contract_schema": evaluator["schema_version"],
        "evaluator_contract_sha256": pawn_evaluator_sha256(evaluator_path),
        "evaluator_identity": evaluator_identity,
        "source_contract_sha256": receipt["source_contract_sha256"],
        "source_recording_id": receipt["recording_id"],
        "source_receipt_sha256": sha256_file(directory / "recording_receipt.json"),
        "source_samples_sha256": receipt["samples_sha256"],
        "scene_id": receipt["scene_id"],
        "board_pose_id": receipt["board_pose_id"],
        "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
        "selected_piece_id": target_name,
        "protected_other_piece_count": 15,
        "worst_displaced_other_piece": worst_other_piece,
        "other_piece_displacements_m": other_displacements,
        "measurements": measurements,
        "gates": scored["gates"],
        "strict_success": scored["success"],
        "terminal_outcome": (
            "pawn_released_upright_on_target"
            if scored["success"]
            else "pawn_pick_place_consequence_gate_failed"
        ),
        "admission_class": (
            "ordinary_strict_success" if scored["success"] else "counterexample_only"
        ),
        "all_source_actions_admitted": bool(scored["success"]),
        "exact_float32_sample_hold_replay_passed": bool(
            measurements["exact_sample_hold_state_replay"]
        ),
        "physics_steps_per_action": 10,
        "assistance_frames": measurements["assistance_frames"],
        "held_out_membership": False,
        "training_rows_authorized": len(rows) if scored["success"] else 0,
        "training_cannot_promote": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    verdict["canonical_payload_sha256"] = admission_payload_sha256(verdict)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verdict["receipt_path"] = str(output_path)
        verdict["receipt_sha256"] = sha256_file(output_path)
    return verdict
