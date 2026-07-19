"""Canonical, model-agnostic manipulation source episodes and policy adapters.

The source schema is intentionally upstream of ACT and GR00T.  A raw episode
never becomes imitation data merely because an operator labels it successful;
the adapters require a separately owned, hash-bound admission verdict.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .paths import REPO_ROOT
from .scene import CURRENT_TASK_LAYOUT_ID, CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS


CONTRACT_PATH_V1 = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_source_episode_v1.json"
)
CONTRACT_PATH_V3 = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_source_episode_v3.json"
)
CONTRACT_PATH_V4 = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_source_episode_v4.json"
)
CONTRACT_PATH = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_source_episode_v2.json"
)
KNOWN_CONTRACT_PATHS = (
    CONTRACT_PATH_V4,
    CONTRACT_PATH_V3,
    CONTRACT_PATH,
    CONTRACT_PATH_V1,
)
CONTRACT_SCHEMAS = {
    "chess_pick_place_source_episode_v1": (
        "sim2claw.canonical_manipulation_source_contract.v1"
    ),
    "chess_pick_place_source_episode_v2": (
        "sim2claw.canonical_manipulation_source_contract.v2"
    ),
    "chess_pick_place_source_episode_v3": (
        "sim2claw.canonical_manipulation_source_contract.v3"
    ),
    "chess_pick_place_source_episode_v4": (
        "sim2claw.canonical_manipulation_source_contract.v4"
    ),
}
EPISODE_SCHEMA = "sim2claw.manipulation_source_episode.v1"
SAMPLE_SCHEMA = "sim2claw.manipulation_source_sample.v1"
RECEIPT_SCHEMA = "sim2claw.manipulation_source_recording_receipt.v1"
ADMISSION_SCHEMA = "sim2claw.manipulation_source_admission_verdict.v1"
ACT_ADAPTER_SCHEMA = "sim2claw.canonical_source_to_act.v1"
GROOT_ADAPTER_SCHEMA = "sim2claw.canonical_source_to_groot.v1"
CURRENT_SCENE_ID = "operator_updated_chess_workcell_v3"
CURRENT_BOARD_POSE_ID = "board_robotward_100mm_20260718_v3"

_SCENE_CONTRACTS: dict[str, dict[str, Any]] = {
    "chess_pick_place_source_episode_v1": {
        "scene_id": "operator_updated_chess_workcell_v2",
        "board_pose_id": "board_robotward_72mm_20260718_v2",
        "board_center": [0.04, -0.093],
        "displacement_field": "robotward_displacement_from_previous_pose_m",
        "displacement_m": 0.072,
        "destination_squares": {
            *(f"{file_name}5" for file_name in "abcdef"),
            *(f"{file_name}6" for file_name in "abcdefgh"),
        },
    },
    "chess_pick_place_source_episode_v2": {
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "board_center": [0.04, -0.065],
        "displacement_field": "robotward_displacement_from_reference_pose_m",
        "displacement_m": 0.1,
        "workspace_pose_id": (
            "workspace_board_fiducial_robotward_100mm_20260718_v3"
        ),
        "fiducial_pose_id": "fiducial_robotward_100mm_20260718_v2",
        "fiducial_center": [0.02, 0.18],
        "destination_squares": {
            *(f"{file_name}5" for file_name in "abcdefgh"),
            *(f"{file_name}6" for file_name in "abcdefgh"),
        },
    },
    "chess_pick_place_source_episode_v3": {
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "board_center": [0.04, -0.065],
        "displacement_field": "robotward_displacement_from_reference_pose_m",
        "displacement_m": 0.1,
        "workspace_pose_id": (
            "workspace_board_fiducial_robotward_100mm_20260718_v3"
        ),
        "fiducial_pose_id": "fiducial_robotward_100mm_20260718_v2",
        "fiducial_center": [0.02, 0.18],
        "destination_squares": {
            *(f"{file_name}5" for file_name in "abcdefgh"),
            *(f"{file_name}6" for file_name in "abcdefgh"),
        },
        "reset_id": "c8_standoff_collision_free_reset_v1",
        "left_arm_joint_pose_radians": [
            0.013117630259065333,
            -0.10199701741066777,
            0.1534035836475657,
            1.4968274683932468,
            2.013538628193459,
            1.35,
        ],
    },
    "chess_pick_place_source_episode_v4": {
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "board_center": [0.04, -0.065],
        "displacement_field": "robotward_displacement_from_reference_pose_m",
        "displacement_m": 0.1,
        "workspace_pose_id": (
            "workspace_board_fiducial_robotward_100mm_20260718_v3"
        ),
        "fiducial_pose_id": "fiducial_robotward_100mm_20260718_v2",
        "fiducial_center": [0.02, 0.18],
        "destination_squares": {
            "a1",
            "c1",
            "e1",
            "g1",
            "b2",
            "d2",
            "f2",
            "h2",
            *(f"{file_name}3" for file_name in "abcdefgh"),
            *(f"{file_name}4" for file_name in "abcdefgh"),
        },
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict[str, Any]:
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file())
    ]
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return {
        "file_count": len(entries),
        "entries": entries,
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def source_contract_sha256(path: Path = CONTRACT_PATH) -> str:
    return sha256_file(path)


def admission_payload_sha256(verdict: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in verdict.items()
        if key
        not in {
            "canonical_payload_sha256",
            "receipt_path",
            "receipt_sha256",
        }
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _finite_vector(
    value: Any,
    *,
    size: int,
    label: str,
    allow_null: bool = False,
) -> list[float] | None:
    if value is None and allow_null:
        return None
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{label} must contain exactly {size} values")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} contains a non-finite value")
    return result


def validate_source_contract(contract: dict[str, Any]) -> dict[str, Any]:
    contract_id = str(contract.get("contract_id") or "")
    if contract.get("schema_version") != CONTRACT_SCHEMAS.get(contract_id):
        raise ValueError("unsupported canonical source contract schema")
    if contract_id not in _SCENE_CONTRACTS:
        raise ValueError("unexpected canonical source contract identity")
    if not contract.get("frozen_before_data_export"):
        raise ValueError("source contract must be frozen before data export")

    scene = contract["scene"]
    expected_scene = _SCENE_CONTRACTS[contract_id]
    if scene.get("scene_id") != expected_scene["scene_id"]:
        raise ValueError("canonical source scene identity changed")
    if scene.get("board_pose_id") != expected_scene["board_pose_id"]:
        raise ValueError("canonical source board pose identity changed")
    if scene.get("piece_layout") != CURRENT_TASK_PIECE_LAYOUT:
        raise ValueError("canonical source contract uses the wrong piece layout")
    if scene.get("piece_layout_id") != CURRENT_TASK_LAYOUT_ID:
        raise ValueError("canonical source contract uses the wrong layout identity")
    if scene.get("board_center_in_table_frame_xy_m") != expected_scene["board_center"]:
        raise ValueError("canonical source contract uses the wrong board center")
    if not math.isclose(
        float(scene.get(expected_scene["displacement_field"], -1.0)),
        float(expected_scene["displacement_m"]),
        abs_tol=1e-12,
    ):
        raise ValueError("canonical source contract does not bind its board shift")
    if contract_id in {
        "chess_pick_place_source_episode_v2",
        "chess_pick_place_source_episode_v3",
        "chess_pick_place_source_episode_v4",
    }:
        if scene.get("workspace_pose_id") != expected_scene["workspace_pose_id"]:
            raise ValueError("canonical source workspace pose identity changed")
        if scene.get("fiducial_pose_id") != expected_scene["fiducial_pose_id"]:
            raise ValueError("canonical source fiducial pose identity changed")
        if scene.get("fiducial_center_in_table_frame_xy_m") != expected_scene[
            "fiducial_center"
        ]:
            raise ValueError("canonical source fiducial center changed")
    if contract_id == "chess_pick_place_source_episode_v3":
        reset = contract.get("simulation_reset")
        if not isinstance(reset, dict):
            raise ValueError("source v3 requires a simulation reset contract")
        if reset.get("reset_id") != expected_scene["reset_id"]:
            raise ValueError("source v3 reset identity changed")
        if reset.get("left_arm_joint_pose_radians") != expected_scene[
            "left_arm_joint_pose_radians"
        ]:
            raise ValueError("source v3 reset joint pose changed")
        if int(reset.get("settle_physics_steps", 0)) != 300:
            raise ValueError("source v3 settle duration changed")
        if reset.get("zero_robot_piece_contact_required_during_settle") is not True:
            raise ValueError("source v3 must prohibit reset robot-piece contact")
        if reset.get("all_sixteen_pawns_upright_after_settle_required") is not True:
            raise ValueError("source v3 must require an upright pawn reset")
        if not math.isclose(
            float(reset.get("maximum_piece_displacement_after_settle_m", -1.0)),
            0.002,
            abs_tol=1e-12,
        ):
            raise ValueError("source v3 reset displacement bound changed")
        if reset.get("physical_robot_motion_authority") is not False:
            raise ValueError("source v3 reset may not create physical authority")
    if int(scene.get("active_piece_count", 0)) != 16:
        raise ValueError("pawn workcell must protect all sixteen pieces")
    expected_sources = (
        {
            "brown_pawn_a2",
            "brown_pawn_b1",
            "brown_pawn_c2",
            "brown_pawn_d1",
            "brown_pawn_e2",
            "brown_pawn_f1",
            "brown_pawn_g2",
            "brown_pawn_h1",
        }
        if contract_id == "chess_pick_place_source_episode_v4"
        else {
            "tan_pawn_a8",
            "tan_pawn_b7",
            "tan_pawn_c8",
            "tan_pawn_d7",
            "tan_pawn_e8",
            "tan_pawn_f7",
            "tan_pawn_g8",
            "tan_pawn_h7",
        }
    )
    if set(scene.get("source_piece_ids") or []) != expected_sources:
        raise ValueError("canonical source identities changed")
    expected_destinations = expected_scene["destination_squares"]
    if set(scene.get("destination_squares") or []) != expected_destinations:
        raise ValueError("canonical source destinations are not the reachable empty rows")

    episode = contract["episode"]
    if episode.get("schema_version") != EPISODE_SCHEMA:
        raise ValueError("source episode schema changed")
    if episode.get("sample_schema_version") != SAMPLE_SCHEMA:
        raise ValueError("source sample schema changed")
    if episode.get("receipt_schema_version") != RECEIPT_SCHEMA:
        raise ValueError("source receipt schema changed")
    if episode.get("required_rgb_streams") != ["top", "wrist"]:
        raise ValueError("canonical source requires synchronized top and wrist RGB")
    if episode.get("privileged_state_may_enter_policy_adapter") is not False:
        raise ValueError("privileged evaluator state may not enter policy adapters")

    execution = contract["execution"]
    if (
        int(execution.get("sample_hold_hz", 0)) != 20
        or int(execution.get("physics_steps_per_action", 0)) != 10
        or not math.isclose(
            float(execution.get("physics_timestep_seconds", 0.0)),
            0.005,
            abs_tol=1e-12,
        )
    ):
        raise ValueError("source execution must be exact 20 Hz / 10-step sample-hold")
    if int(execution.get("action_dimension", 0)) != len(ROBOT_JOINTS):
        raise ValueError("source action dimension must match the SO-101")
    if execution.get("action_representation") != "absolute_joint_position_target":
        raise ValueError("source actions must be absolute joint targets")
    if not execution.get("exact_float32_action_replay_required_before_export"):
        raise ValueError("exact action replay must be required before export")

    admission = contract["admission"]
    if admission.get("failed_actions_may_enter_behavior_cloning") is not False:
        raise ValueError("raw failed actions may not enter behavior cloning")
    if int(admission.get("held_out_rows", -1)) != 0:
        raise ValueError("held-out rows must remain zero")
    if not admission.get("corrective_suffix", {}).get(
        "must_start_from_exact_pre_failure_integration_state"
    ):
        raise ValueError("corrective suffixes must start at the exact pre-failure state")
    if not admission.get("corrective_suffix", {}).get(
        "independent_full_episode_replay_must_pass"
    ):
        raise ValueError("corrective suffixes require a passing full replay")

    training = set(contract["splits"]["training_source_piece_ids"])
    held_out = set(contract["splits"]["held_out_source_piece_ids"])
    if training & held_out:
        raise ValueError("training and held-out pawn identities overlap")
    if training | held_out != expected_sources:
        raise ValueError("training and held-out pawn identities are incomplete")
    if int(contract["splits"].get("held_out_training_rows", -1)) != 0:
        raise ValueError("held-out split must contribute zero training rows")
    if contract["authority"].get("old_rook_or_king_evidence_grants_pawn_authority"):
        raise ValueError("old rook/king evidence cannot grant pawn authority")
    return contract


def load_source_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("canonical source contract must be a JSON object")
    return validate_source_contract(payload)


def source_contract_path_for_sha256(expected_sha256: str) -> Path:
    for path in KNOWN_CONTRACT_PATHS:
        if path.is_file() and sha256_file(path) == expected_sha256:
            return path
    raise ValueError("canonical source contract hash is not recognized")


def language_instruction(piece_id: str, source_square: str, destination_square: str) -> str:
    parts = piece_id.split("_")
    if len(parts) != 3 or parts[1] != "pawn" or parts[2] != source_square:
        raise ValueError("piece identity and source square disagree")
    color = parts[0]
    return (
        f"Pick up the {color} pawn on {source_square} and place it upright "
        f"on the empty square {destination_square}."
    )


def build_source_sample(
    *,
    episode_id: str,
    sample_index: int,
    timestamp_monotonic_seconds: float,
    instruction: str,
    raw_sample: dict[str, Any],
    rgb: dict[str, Any],
    action_owner: str,
    assistance: bool,
    intervention: bool,
) -> dict[str, Any]:
    """Build one canonical row without granting it training authority."""

    row = {
        # Preserve source-specific diagnostics while keeping policy adapters on
        # the explicit canonical fields below.
        **raw_sample,
        "schema_version": SAMPLE_SCHEMA,
        "episode_id": episode_id,
        "recording_id": episode_id,
        "sample_index": sample_index,
        "timestamp_monotonic_seconds": timestamp_monotonic_seconds,
        "language_instruction": instruction,
        "rgb": rgb,
        "robot": {
            "joint_position_rad": raw_sample.get("follower_actual_position_rad"),
            "joint_velocity_rad_s": raw_sample.get(
                "follower_actual_velocity_rad_s"
            ),
            "end_effector_pose_world": raw_sample.get(
                "end_effector_pose_world"
            ),
            "gripper_joint_position_rad": raw_sample.get(
                "gripper_joint_position_rad"
            ),
        },
        "goal": {
            "selected_piece_pose_world": raw_sample.get(
                "selected_piece_pose_world"
            ),
            "continuous_target_pose_world": raw_sample.get(
                "continuous_target_pose_world"
            ),
        },
        "action": {
            "representation": "absolute_joint_position_target",
            "joint_target_rad": raw_sample.get("follower_command_rad"),
            "owner": action_owner,
            "assistance": int(assistance),
            "intervention": int(intervention),
        },
        "events": {
            "contacts": list(raw_sample.get("contacts") or []),
            "simulator_events": list(raw_sample.get("simulator_events") or []),
        },
        "evaluator_privileged_state": {
            "inline": False,
            "path": "evaluator_privileged_state.jsonl",
            "row_index": sample_index,
        },
    }
    return validate_source_sample(row)


def _rgb_reference(value: Any, *, stream: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"rgb.{stream} must be an object")
    if value.get("available") is not True:
        raise ValueError(f"rgb.{stream} is required for a canonical source sample")
    path = str(value.get("path") or "")
    if not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError(f"rgb.{stream}.path must be a safe relative path")
    timestamp = float(value.get("timestamp_monotonic_seconds", -1.0))
    if not math.isfinite(timestamp) or timestamp < 0.0:
        raise ValueError(f"rgb.{stream} has an invalid timestamp")
    return value


def validate_source_sample(sample: dict[str, Any]) -> dict[str, Any]:
    if sample.get("schema_version") != SAMPLE_SCHEMA:
        raise ValueError("unsupported canonical source sample schema")
    if int(sample.get("sample_index", -1)) < 0:
        raise ValueError("source sample index must be non-negative")
    timestamp = float(sample.get("timestamp_monotonic_seconds", -1.0))
    if not math.isfinite(timestamp) or timestamp < 0.0:
        raise ValueError("source sample timestamp must be non-negative and finite")
    instruction = str(sample.get("language_instruction") or "").strip()
    if not instruction:
        raise ValueError("source sample language instruction is required")

    rgb = sample.get("rgb")
    if not isinstance(rgb, dict):
        raise ValueError("source sample RGB streams are missing")
    _rgb_reference(rgb.get("top"), stream="top")
    _rgb_reference(rgb.get("wrist"), stream="wrist")

    robot = sample.get("robot")
    if not isinstance(robot, dict):
        raise ValueError("source sample robot state is missing")
    _finite_vector(robot.get("joint_position_rad"), size=6, label="joint_position_rad")
    _finite_vector(robot.get("joint_velocity_rad_s"), size=6, label="joint_velocity_rad_s")
    _finite_vector(
        robot.get("end_effector_pose_world"),
        size=7,
        label="end_effector_pose_world",
    )
    gripper = float(robot.get("gripper_joint_position_rad", math.nan))
    if not math.isfinite(gripper):
        raise ValueError("gripper_joint_position_rad must be finite")

    goal = sample.get("goal")
    if not isinstance(goal, dict):
        raise ValueError("source sample goal state is missing")
    _finite_vector(
        goal.get("selected_piece_pose_world"),
        size=7,
        label="selected_piece_pose_world",
    )
    _finite_vector(
        goal.get("continuous_target_pose_world"),
        size=7,
        label="continuous_target_pose_world",
    )

    action = sample.get("action")
    if not isinstance(action, dict):
        raise ValueError("source sample action is missing")
    _finite_vector(action.get("joint_target_rad"), size=6, label="joint_target_rad")
    if action.get("representation") != "absolute_joint_position_target":
        raise ValueError("source sample action representation changed")
    if action.get("owner") not in {
        "human_teleoperator",
        "geometric_expert",
        "planner",
        "learned_policy",
    }:
        raise ValueError("source sample has an undeclared action owner")
    if int(action.get("assistance", -1)) not in {0, 1}:
        raise ValueError("source sample assistance must be binary")
    if int(action.get("intervention", -1)) not in {0, 1}:
        raise ValueError("source sample intervention must be binary")

    events = sample.get("events")
    if not isinstance(events, dict):
        raise ValueError("source sample events are missing")
    if not isinstance(events.get("contacts"), list):
        raise ValueError("source sample contacts must be a list")
    if not isinstance(events.get("simulator_events"), list):
        raise ValueError("source sample simulator events must be a list")
    privileged = sample.get("evaluator_privileged_state")
    if not isinstance(privileged, dict) or privileged.get("inline") is not False:
        raise ValueError("privileged state must be stored out of line")
    if int(privileged.get("row_index", -1)) != int(sample["sample_index"]):
        raise ValueError("privileged-state row lineage is inconsistent")
    return sample


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} is not an object")
        rows.append(value)
    return rows


def load_source_episode(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = directory.resolve()
    receipt_path = directory / "recording_receipt.json"
    samples_path = directory / "samples.jsonl"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("unsupported canonical source receipt schema")
    if receipt.get("source_episode_schema") != EPISODE_SCHEMA:
        raise ValueError("canonical source episode identity changed")
    contract_path = source_contract_path_for_sha256(
        str(receipt.get("source_contract_sha256") or "")
    )
    contract = load_source_contract(contract_path)
    if receipt.get("task_id") != contract.get("contract_id"):
        raise ValueError("canonical source task identity does not match its contract")
    if receipt.get("scene_id") != contract["scene"]["scene_id"]:
        raise ValueError("canonical source scene does not match its contract")
    if receipt.get("board_pose_id") != contract["scene"]["board_pose_id"]:
        raise ValueError("canonical source board pose does not match its contract")
    if sha256_file(samples_path) != receipt.get("samples_sha256"):
        raise ValueError("canonical source samples do not match their receipt")
    privileged_path = directory / str(receipt.get("evaluator_privileged_state_path") or "")
    if not privileged_path.is_file():
        raise ValueError("evaluator-only privileged state is missing")
    if sha256_file(privileged_path) != receipt.get("evaluator_privileged_state_sha256"):
        raise ValueError("evaluator-only privileged state does not match its receipt")
    initial_privileged_path = directory / str(
        receipt.get("initial_evaluator_privileged_state_path") or ""
    )
    if not initial_privileged_path.is_file():
        raise ValueError("initial evaluator-only privileged state is missing")
    if sha256_file(initial_privileged_path) != receipt.get(
        "initial_evaluator_privileged_state_sha256"
    ):
        raise ValueError("initial evaluator-only state does not match its receipt")
    initial_privileged = json.loads(
        initial_privileged_path.read_text(encoding="utf-8")
    )
    if (
        initial_privileged.get("episode_id") != receipt.get("recording_id")
        or initial_privileged.get("policy_adapter_access") is not False
    ):
        raise ValueError("initial privileged-state lineage or authority changed")
    if tree_manifest(directory / "rgb") != receipt.get("rgb_streams"):
        raise ValueError("canonical source RGB inventory does not match its receipt")
    rows = _jsonl(samples_path)
    if len(rows) != int(receipt.get("sample_count", -1)):
        raise ValueError("canonical source sample count does not match its receipt")
    for expected_index, row in enumerate(rows):
        validate_source_sample(row)
        if int(row["sample_index"]) != expected_index:
            raise ValueError("canonical source sample indices are not contiguous")
        if row.get("episode_id") != receipt.get("recording_id"):
            raise ValueError("canonical source sample episode lineage changed")
        for stream in ("top", "wrist"):
            reference = row["rgb"][stream]
            frame_path = (directory / str(reference["path"])).resolve()
            if not frame_path.is_relative_to(directory) or not frame_path.is_file():
                raise ValueError(f"canonical source {stream} RGB frame is missing")
            if sha256_file(frame_path) != reference.get("sha256"):
                raise ValueError(f"canonical source {stream} RGB frame hash mismatch")
    privileged_rows = _jsonl(privileged_path)
    if len(privileged_rows) != len(rows):
        raise ValueError("privileged-state row count does not match source samples")
    for expected_index, privileged_row in enumerate(privileged_rows):
        if (
            int(privileged_row.get("sample_index", -1)) != expected_index
            or privileged_row.get("episode_id") != receipt.get("recording_id")
            or privileged_row.get("policy_adapter_access") is not False
        ):
            raise ValueError("privileged-state lineage or authority changed")
    return receipt, rows


def _require_admitted(
    directory: Path,
    receipt: dict[str, Any],
    verdict: dict[str, Any],
) -> str:
    if verdict.get("schema_version") != ADMISSION_SCHEMA:
        raise ValueError("unsupported canonical source admission verdict")
    if verdict.get("canonical_payload_sha256") != admission_payload_sha256(verdict):
        raise ValueError("canonical source admission verdict hash mismatch")
    if verdict.get("source_recording_id") != receipt.get("recording_id"):
        raise ValueError("admission verdict references another source episode")
    if verdict.get("source_receipt_sha256") != sha256_file(
        directory / "recording_receipt.json"
    ):
        raise ValueError("admission verdict is not bound to this source receipt")
    if verdict.get("source_samples_sha256") != receipt.get("samples_sha256"):
        raise ValueError("admission verdict is not bound to these source samples")
    if verdict.get("scene_id") != receipt.get("scene_id"):
        raise ValueError("admission verdict used the wrong workcell scene")
    if verdict.get("board_pose_id") != receipt.get("board_pose_id"):
        raise ValueError("admission verdict used the wrong board pose")
    if verdict.get("held_out_membership") is not False:
        raise ValueError("held-out episodes may not enter training adapters")
    if verdict.get("strict_success") is not True:
        raise ValueError("only strict evaluator successes may enter policy adapters")
    if verdict.get("exact_float32_sample_hold_replay_passed") is not True:
        raise ValueError("source episode has not passed exact sample-hold replay")
    if int(verdict.get("physics_steps_per_action", 0)) != 10:
        raise ValueError("admission replay used the wrong sample-hold cadence")
    if int(verdict.get("assistance_frames", -1)) != 0:
        raise ValueError("assisted source actions may not enter ordinary imitation data")
    admission_class = str(verdict.get("admission_class") or "")
    if admission_class == "ordinary_strict_success":
        if verdict.get("all_source_actions_admitted") is not True:
            raise ValueError("ordinary admission must cover the full strict-success episode")
    elif admission_class == "corrective_suffix":
        correction = verdict.get("corrective_suffix")
        if not isinstance(correction, dict):
            raise ValueError("corrective admission is missing suffix lineage")
        for field in (
            "exact_pre_failure_integration_state_matched",
            "failed_prefix_excluded_from_imitation_rows",
            "independent_full_episode_replay_passed",
            "corrective_actions_owned_by_declared_expert_or_teleoperator",
        ):
            if correction.get(field) is not True:
                raise ValueError(f"corrective admission requirement failed: {field}")
    else:
        raise ValueError("admission class is not eligible for imitation data")
    return admission_class


def _row_indices_for_admission(
    rows: list[dict[str, Any]], verdict: dict[str, Any], admission_class: str
) -> Iterable[int]:
    if admission_class == "ordinary_strict_success":
        return range(len(rows))
    correction = verdict["corrective_suffix"]
    start = int(correction.get("start_sample_index", -1))
    end = int(correction.get("end_sample_index_exclusive", -1))
    if start < 0 or end > len(rows) or end <= start:
        raise ValueError("corrective suffix row range is invalid")
    return range(start, end)


def adapt_source_episode(
    directory: Path,
    *,
    adapter: str,
    admission_verdict: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return eligible ACT or GR00T rows without privileged evaluator state."""

    directory = directory.resolve()
    receipt, rows = load_source_episode(directory)
    admission_class = _require_admitted(directory, receipt, admission_verdict)
    indices = _row_indices_for_admission(rows, admission_verdict, admission_class)
    adapted: list[dict[str, Any]] = []
    for source_index in indices:
        row = rows[source_index]
        lineage = {
            "source_recording_id": receipt["recording_id"],
            "source_sample_index": source_index,
            "source_samples_sha256": receipt["samples_sha256"],
            "source_contract_sha256": receipt["source_contract_sha256"],
            "admission_verdict_sha256": admission_verdict[
                "canonical_payload_sha256"
            ],
            "admission_class": admission_class,
        }
        if adapter == "act":
            adapted.append(
                {
                    "schema_version": ACT_ADAPTER_SCHEMA,
                    "observation": {
                        "robot": row["robot"],
                        "goal": row["goal"],
                    },
                    "action_joint_target_rad": row["action"]["joint_target_rad"],
                    "language_metadata": row["language_instruction"],
                    "lineage": lineage,
                }
            )
        elif adapter == "groot":
            adapted.append(
                {
                    "schema_version": GROOT_ADAPTER_SCHEMA,
                    "observation": {
                        "top_rgb_path": row["rgb"]["top"]["path"],
                        "wrist_rgb_path": row["rgb"]["wrist"]["path"],
                        "language_instruction": row["language_instruction"],
                        "joint_position_rad": row["robot"]["joint_position_rad"],
                    },
                    "action_joint_target_rad": row["action"]["joint_target_rad"],
                    "lineage": lineage,
                }
            )
        else:
            raise ValueError("adapter must be 'act' or 'groot'")
    return adapted
