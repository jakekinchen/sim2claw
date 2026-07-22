#!/usr/bin/env python3
"""Run the frozen B-G pawn-centering simulator diagnostic with a GR00T policy.

The checkpoint was trained from unqualified physical teleoperation recordings.
This runner therefore reports simulated task consequences and policy behavior,
but never promotes the checkpoint or claims a calibrated physical transfer.
Any actuator clipping is recorded and makes policy success non-admissible under
the frozen reward contract.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

# NVIDIA's pinned runtime is Python 3.10, where datetime.UTC is not exposed.
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc  # type: ignore[attr-defined]

from gr00t.policy.server_client import PolicyClient
from sim2claw.contact_prior import (
    apply_contact_variant,
    compiled_contact_identity,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from sim2claw.groot_execution import aggregate_temporal_action
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _id,
    _piece_bodies,
    _trace_row,
)
from sim2claw.pawn_bg_reward import (
    CONTRACT_PATH,
    aggregate_scores,
    load_reward_contract,
    score_episode,
    sha256_file,
)
from sim2claw.pawn_bg_source_fit_visuals import (
    _apply_bg_visual_layout,
    _c922_angle_camera,
    _configure_fixed_camera,
    _load_c922_angle_contract,
)
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)


SCHEMA_VERSION = "sim2claw.groot_n17_physical_bg_centering_diagnostic.v1"
SAMPLE_COUNT = 317
PHYSICS_STEPS_PER_ACTION = 10
SETTLE_PHYSICS_STEPS = 200
QUERY_STRIDE = 8
CAMERA_NAME = "workcell"
CONTACT_VARIANT = "nominal_uncalibrated"
INFERENCE_SEED = 190719
PROPOSAL_COUNT = 5
ACTION_AGGREGATION = "median"
NOISE_SCALE = 0.5
NUM_INFERENCE_TIMESTEPS = 4
TEMPORAL_AGGREGATION = "mean"
BRIDGE_MODES = (
    "frozen_scene_identity",
    "training_source_aligned_stage_d_diagnostic",
)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_exploratory_checkpoint(
    manifest_path: Path, checkpoint_path: Path
) -> dict[str, Any]:
    """Rehash the checkpoint using the campaign's immutable v1 manifest."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canonical = dict(manifest)
    recorded_canonical = canonical.pop("canonical_payload_sha256", None)
    if manifest.get("schema_version") != "sim2claw.groot_checkpoint_manifest.v1":
        raise ValueError("unsupported exploratory checkpoint manifest")
    if canonical_sha256(canonical) != recorded_canonical:
        raise ValueError("checkpoint manifest canonical digest is invalid")
    if manifest.get("global_step") != 5000:
        raise ValueError("pawn-centering eval requires checkpoint 5000")
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("checkpoint manifest inventory is empty")
    expected = {str(row["path"]): row for row in inventory}
    actual = {
        path.relative_to(checkpoint_path).as_posix(): path
        for path in checkpoint_path.rglob("*")
        if path.is_file()
    }
    if set(actual) != set(expected):
        raise ValueError("checkpoint directory inventory differs from manifest")
    for relative, path in actual.items():
        row = expected[relative]
        if path.stat().st_size != int(row["size_bytes"]):
            raise ValueError(f"checkpoint file size drifted: {relative}")
        if _sha256(path) != row["sha256"]:
            raise ValueError(f"checkpoint file digest drifted: {relative}")
    return {
        "manifest_path": str(manifest_path.resolve(strict=True)),
        "manifest_sha256": _sha256(manifest_path),
        "canonical_payload_sha256": recorded_canonical,
        "checkpoint_path": str(checkpoint_path.resolve(strict=True)),
        "global_step": 5000,
        "file_count": len(actual),
        "total_size_bytes": sum(path.stat().st_size for path in actual.values()),
        "complete_file_inventory_verified": True,
    }


def implementation_inventory() -> list[dict[str, str]]:
    paths = (
        Path(__file__).resolve(strict=True),
        CONTRACT_PATH.resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/pawn_bg_reward.py").resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/pawn_bg_demo_sim.py").resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/scene.py").resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/contact_prior.py").resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/groot_execution.py").resolve(strict=True),
        (REPO_ROOT / "src/sim2claw/pawn_bg_source_fit_visuals.py").resolve(strict=True),
        (REPO_ROOT / "configs/tasks/pawn_b_g_language_semantics_v1.json").resolve(strict=True),
        (REPO_ROOT / "configs/evaluations/pawn_rank12_bidirectional_v2.json").resolve(strict=True),
        (REPO_ROOT / "configs/simulation/rubber_tip_contact_sensitivity_v1.json").resolve(strict=True),
        (REPO_ROOT / "configs/experiments/pawn_bg_c922_angle_transfer_v1.json").resolve(strict=True),
        (REPO_ROOT / "configs/optimization/pawn_bg_workcell_fit_v1.json").resolve(strict=True),
    )
    return [
        {
            "path": (
                path.relative_to(REPO_ROOT).as_posix()
                if path.is_relative_to(REPO_ROOT)
                else str(path)
            ),
            "sha256": sha256_file(path),
        }
        for path in paths
    ]


def _write_png(path: Path, pixels: np.ndarray) -> None:
    from PIL import Image

    Image.fromarray(np.asarray(pixels, dtype=np.uint8)).save(path)


def _instruction(source: str, destination: str) -> str:
    return (
        f"Pick up the brown pawn on {source} and place it upright on "
        f"the empty square {destination}."
    )


def _load_source_aligned_bridge(
    *, dataset_root: Path, workcell_fit_receipt_path: Path
) -> dict[str, Any]:
    """Load the fixed training-source alignment without granting it authority."""

    import pyarrow.parquet as pq

    dataset_root = dataset_root.resolve(strict=True)
    dataset_receipt_path = dataset_root / "dataset_receipt.json"
    dataset_receipt = json.loads(dataset_receipt_path.read_text(encoding="utf-8"))
    canonical = dict(dataset_receipt)
    recorded_canonical = canonical.pop("canonical_payload_sha256", None)
    if (
        dataset_receipt.get("schema_version")
        != "sim2claw.groot_n17_physical_bg_exploratory_receipt.v1"
        or dataset_receipt.get("episode_count") != 18
        or dataset_receipt.get("held_out_rows") != 0
        or dataset_receipt.get("all_training_rows_evaluator_admitted") is not False
    ):
        raise ValueError("source-aligned bridge received the wrong training dataset")
    if canonical_sha256(canonical) != recorded_canonical:
        raise ValueError("training dataset receipt canonical digest is invalid")
    payload_manifest = dataset_receipt.get("payload_manifest")
    if not isinstance(payload_manifest, dict) or not payload_manifest:
        raise ValueError("training dataset receipt has no payload inventory")
    for relative, identity in payload_manifest.items():
        path = dataset_root / relative
        if (
            not path.is_file()
            or path.stat().st_size != int(identity["size_bytes"])
            or _sha256(path) != identity["sha256"]
        ):
            raise ValueError(f"training dataset payload drifted: {relative}")

    episodes_path = dataset_root / "meta/episodes.jsonl"
    episode_rows = [
        json.loads(line)
        for line in episodes_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(episode_rows) != 18:
        raise ValueError("training dataset episode inventory changed")
    reset_states_by_instruction: dict[str, list[np.ndarray]] = {}
    for episode_index, episode in enumerate(episode_rows):
        tasks = episode.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != 1:
            raise ValueError("training episode task identity changed")
        parquet_path = (
            dataset_root
            / "data/chunk-000"
            / f"episode_{episode_index:06d}.parquet"
        )
        table = pq.read_table(parquet_path, columns=["observation.state"])
        first_state = np.asarray(
            table["observation.state"][0].as_py(), dtype=np.float64
        )
        if first_state.shape != (6,) or not np.isfinite(first_state).all():
            raise ValueError("training episode has an invalid initial state")
        reset_states_by_instruction.setdefault(str(tasks[0]), []).append(first_state)
    task_resets = {
        instruction: np.median(np.stack(states), axis=0)
        for instruction, states in reset_states_by_instruction.items()
    }

    workcell_fit_receipt_path = workcell_fit_receipt_path.resolve(strict=True)
    workcell = json.loads(workcell_fit_receipt_path.read_text(encoding="utf-8"))
    if (
        workcell.get("schema_version")
        != "sim2claw.pawn_bg_workcell_fit_receipt.v1"
        or workcell.get("selected_candidate") != "stage_d_lift"
        or workcell.get("held_out_opened") is not False
    ):
        raise ValueError("source-aligned bridge requires the sealed stage-D receipt")
    selected = workcell.get("selected_parameters")
    if not isinstance(selected, dict):
        raise ValueError("workcell fit receipt has no selected parameters")
    offsets = np.asarray(selected.get("joint_zero_offsets_rad"), dtype=np.float64)
    envelope = np.asarray(selected.get("joint_range_envelope_rad"), dtype=np.float64)
    signs = selected.get("body_joint_signs")
    if (
        offsets.shape != (5,)
        or envelope.shape != (5, 2)
        or signs != [1, 1, 1, 1, 1]
        or not np.isfinite(offsets).all()
        or not np.isfinite(envelope).all()
        or np.any(envelope[:, 0] >= envelope[:, 1])
    ):
        raise ValueError("workcell fit adapter parameters are invalid")
    return {
        "mode": "training_source_aligned_stage_d_diagnostic",
        "dataset": {
            "root": str(dataset_root),
            "receipt_path": str(dataset_receipt_path),
            "receipt_sha256": _sha256(dataset_receipt_path),
            "canonical_payload_sha256": recorded_canonical,
            "complete_payload_inventory_verified": True,
            "episode_count": 18,
            "held_out_rows": 0,
            "evaluator_admitted": False,
        },
        "workcell_fit": {
            "receipt_path": str(workcell_fit_receipt_path),
            "receipt_sha256": _sha256(workcell_fit_receipt_path),
            "selected_candidate": "stage_d_lift",
            "held_out_opened_during_this_evaluation": False,
            "training_event_rms_m": workcell["kinematic"][
                "stage_d_lift_kinematic"
            ]["event_rms_distance_m"],
            "claim_boundary": workcell["claim_boundary"],
        },
        "board_center_in_table_frame_xy_m": tuple(
            float(value)
            for value in selected["board_center_in_table_frame_xy_m"]
        ),
        "board_yaw_relative_to_table_degrees": float(
            selected["board_yaw_relative_to_table_degrees"]
        ),
        "body_joint_zero_offsets_rad": offsets,
        "joint_range_envelope_rad": envelope,
        "task_reset_states": task_resets,
        "visual_layout_mode": "owner_corrected_visual_only",
        "camera_mode": "c922_angle_transfer_rotated_180_visual_only",
        "assistance_used_for_frozen_policy_score": True,
        "promotion_eligible": False,
        "physical_calibration_approved": False,
    }


def _initialize_episode(
    contract: dict[str, Any], source: str, instruction: str,
    bridge: dict[str, Any] | None,
) -> tuple[
    mujoco.MjModel,
    mujoco.MjData,
    np.ndarray,
    np.ndarray,
    dict[str, int],
    int,
    int,
    set[int],
    set[int],
    dict[str, np.ndarray],
    dict[str, Any],
    dict[str, Any],
]:
    aligned = bridge is not None
    board_center = (
        bridge["board_center_in_table_frame_xy_m"]
        if aligned
        else registered_board_center(contract["scene_binding"]["scene_id"])
    )
    board_yaw = (
        float(bridge["board_yaw_relative_to_table_degrees"])
        if aligned
        else None
    )
    spec = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
        **(
            {"board_yaw_relative_to_table_degrees": board_yaw}
            if board_yaw is not None
            else {}
        ),
    )
    visual_layout = _apply_bg_visual_layout(spec) if aligned else None
    variant = load_simulator_variant(
        CONTACT_VARIANT, contract_snapshot=read_contact_prior_snapshot()
    )
    application = apply_contact_variant(spec, variant)
    model = spec.compile()
    if not np.isclose(float(model.opt.timestep), 0.005, atol=1e-12):
        raise ValueError("runtime MuJoCo timestep changed")
    actuator_ids = np.asarray(
        [
            _id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}")
            for joint in ROBOT_JOINTS
        ],
        dtype=np.int32,
    )
    joint_ids = np.asarray(
        [
            _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
            for joint in ROBOT_JOINTS
        ],
        dtype=np.int32,
    )
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids],
        dtype=np.int32,
    )
    if aligned:
        for index, (low, high) in enumerate(
            np.asarray(bridge["joint_range_envelope_rad"], dtype=np.float64)
        ):
            joint_id = int(joint_ids[index])
            actuator_id = int(actuator_ids[index])
            model.jnt_range[joint_id, 0] = min(model.jnt_range[joint_id, 0], low)
            model.jnt_range[joint_id, 1] = max(model.jnt_range[joint_id, 1], high)
            model.actuator_ctrlrange[actuator_id, 0] = min(
                model.actuator_ctrlrange[actuator_id, 0], low
            )
            model.actuator_ctrlrange[actuator_id, 1] = max(
                model.actuator_ctrlrange[actuator_id, 1], high
            )
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)

    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = _id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = _id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(
        board_square_center(
            source,
            board_center_in_table_frame_xy_m=board_center,
            **(
                {"board_yaw_relative_to_table_degrees": board_yaw}
                if board_yaw is not None
                else {}
            ),
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    reset_state = None
    if aligned:
        reset_state = bridge["task_reset_states"].get(instruction)
        if reset_state is None:
            raise ValueError(
                f"source-aligned diagnostic has no training reset for {instruction}"
            )
        reset_state = np.asarray(reset_state, dtype=np.float64).copy()
        mapped_reset = reset_state.copy()
        mapped_reset[:5] += np.asarray(
            bridge["body_joint_zero_offsets_rad"], dtype=np.float64
        )
        bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
        if np.any(mapped_reset < bounds[:, 0]) or np.any(mapped_reset > bounds[:, 1]):
            raise ValueError("source-aligned reset exceeds expanded simulator ranges")
        data.qpos[qpos_addresses] = mapped_reset
        data.ctrl[actuator_ids] = mapped_reset
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    if aligned:
        angle_camera = _c922_angle_camera(_load_c922_angle_contract(), board_center)
        _configure_fixed_camera(model, data, angle_camera)
    else:
        angle_camera = None
    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    fixed_geom = _id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1"
    )
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        _id(model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"),
    }
    return (
        model,
        data,
        actuator_ids,
        qpos_addresses,
        piece_bodies,
        selected_body,
        selected_dof,
        robot_body_ids,
        jaw_body_ids,
        initial_positions,
        {
            "variant_id": variant.variant_id,
            "variant_sha256": variant.variant_sha256,
            "compiled_identity": compiled_contact_identity(model, application),
        },
        {
            "board_center_in_table_frame_xy_m": list(board_center),
            "board_yaw_relative_to_table_degrees": board_yaw,
            "visual_layout": visual_layout,
            "camera": (
                {
                    "mode": bridge["camera_mode"],
                    "camera_position_world": np.asarray(
                        angle_camera["camera_position_world"]
                    ).tolist(),
                    "vertical_fov_degrees": angle_camera["vertical_fov_degrees"],
                    "rotate_render_degrees": 180,
                }
                if aligned
                else {
                    "mode": "scene_workcell_camera",
                    "rotate_render_degrees": 0,
                }
            ),
            "model_training_reset_state": (
                reset_state.tolist() if reset_state is not None else None
            ),
        },
    )


def run_episode(
    *,
    client: PolicyClient,
    contract: dict[str, Any],
    skill: dict[str, Any],
    output: Path,
    case_index: int,
    bridge: dict[str, Any] | None,
) -> dict[str, Any]:
    source = str(skill["source_square"])
    destination = str(skill["destination_square"])
    skill_id = str(skill["skill_id"])
    instruction = _instruction(source, destination)
    (
        model,
        data,
        actuator_ids,
        qpos_addresses,
        piece_bodies,
        selected_body,
        selected_dof,
        robot_body_ids,
        jaw_body_ids,
        initial_positions,
        contact_identity,
        geometry_identity,
    ) = _initialize_episode(contract, source, instruction, bridge)
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
    initial_height = float(data.xpos[selected_body][2])
    target = np.asarray(
        board_square_center(
            destination,
            board_center_in_table_frame_xy_m=geometry_identity[
                "board_center_in_table_frame_xy_m"
            ],
            **(
                {
                    "board_yaw_relative_to_table_degrees": geometry_identity[
                        "board_yaw_relative_to_table_degrees"
                    ]
                }
                if geometry_identity["board_yaw_relative_to_table_degrees"]
                is not None
                else {}
            ),
        ),
        dtype=np.float64,
    )
    reset_info = client.reset(
        options={
            "inference_seed": INFERENCE_SEED,
            "proposal_count": PROPOSAL_COUNT,
            "action_aggregation": ACTION_AGGREGATION,
            "noise_scale": NOISE_SCALE,
            "num_inference_timesteps": NUM_INFERENCE_TIMESTEPS,
        }
    )
    expected_reset = {
        "rng_reset": True,
        "inference_seed": INFERENCE_SEED,
        "proposal_count": PROPOSAL_COUNT,
        "action_aggregation": ACTION_AGGREGATION,
        "noise_scale": NOISE_SCALE,
        "num_inference_timesteps": NUM_INFERENCE_TIMESTEPS,
    }
    for key, expected in expected_reset.items():
        if reset_info.get(key) != expected:
            raise RuntimeError(f"policy server acknowledged the wrong {key}")

    renderer = mujoco.Renderer(model, height=256, width=256)
    trace: list[dict[str, Any]] = [
        _trace_row(
            model,
            data,
            selected_body=selected_body,
            selected_dof=selected_dof,
            piece_bodies=piece_bodies,
            initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids,
            jaw_body_ids=jaw_body_ids,
        )
    ]
    states: list[np.ndarray] = []
    requested_actions: list[np.ndarray] = []
    simulator_control_requests: list[np.ndarray] = []
    applied_actions: list[np.ndarray] = []
    action_chunks: list[tuple[int, np.ndarray]] = []
    query_receipts: list[dict[str, Any]] = []
    clipping_rows = 0
    clipping_values = 0
    case_output = output / f"{case_index:02d}-{skill_id}"
    case_output.mkdir()
    aligned = bridge is not None

    def policy_frame(raw: np.ndarray) -> np.ndarray:
        if not aligned:
            return raw
        return np.ascontiguousarray(raw[::-1, ::-1])

    def policy_state(simulator_state: np.ndarray) -> np.ndarray:
        result = np.asarray(simulator_state, dtype=np.float32).copy()
        if aligned:
            result[:5] -= np.asarray(
                bridge["body_joint_zero_offsets_rad"], dtype=np.float32
            )
        return result

    def simulator_request(model_action: np.ndarray) -> np.ndarray:
        result = np.asarray(model_action, dtype=np.float64).copy()
        if aligned:
            result[:5] += np.asarray(
                bridge["body_joint_zero_offsets_rad"], dtype=np.float64
            )
        return result

    try:
        renderer.update_scene(data, camera=CAMERA_NAME)
        initial_raw_frame = renderer.render().copy()
        initial_frame = policy_frame(initial_raw_frame)
        _write_png(case_output / "initial.png", initial_frame)
        if aligned:
            _write_png(case_output / "initial_raw_simulator.png", initial_raw_frame)
        for sample_step in range(SAMPLE_COUNT):
            renderer.update_scene(data, camera=CAMERA_NAME)
            frame = policy_frame(renderer.render().copy())
            simulator_state = np.asarray(
                data.qpos[qpos_addresses], dtype=np.float32
            ).copy()
            state = policy_state(simulator_state)
            states.append(state)
            if sample_step % QUERY_STRIDE == 0:
                observation = {
                    "video": {"front": frame[None, None, ...]},
                    "state": {
                        "single_arm": state[None, None, :5],
                        "gripper": state[None, None, 5:],
                    },
                    "language": {
                        "annotation.human.task_description": [[instruction]]
                    },
                }
                predicted, query_info = client.get_action(
                    observation,
                    options={"sample_step": sample_step},
                )
                arm = np.asarray(predicted["single_arm"], dtype=np.float32)[0]
                gripper = np.asarray(predicted["gripper"], dtype=np.float32)[0]
                chunk = np.concatenate([arm, gripper], axis=-1)
                if (
                    chunk.ndim != 2
                    or chunk.shape[0] < QUERY_STRIDE
                    or chunk.shape[1] != 6
                    or not np.isfinite(chunk).all()
                ):
                    raise RuntimeError(f"policy returned invalid action chunk {chunk.shape}")
                action_chunks.append((sample_step, chunk.copy()))
                query_receipts.append(
                    {
                        "sample_step": sample_step,
                        "query_seed": query_info.get("query_seed"),
                        "proposal_seeds": query_info.get("proposal_seeds"),
                        "consensus": query_info.get("consensus"),
                    }
                )
            action, _ = aggregate_temporal_action(
                action_chunks,
                sample_step=sample_step,
                method=TEMPORAL_AGGREGATION,
            )
            requested = np.asarray(action, dtype=np.float32)
            control_request = simulator_request(requested)
            applied = np.clip(control_request, bounds[:, 0], bounds[:, 1])
            clipped = control_request != applied
            clipping_rows += int(np.any(clipped))
            clipping_values += int(np.count_nonzero(clipped))
            requested_actions.append(requested.copy())
            simulator_control_requests.append(control_request.copy())
            applied_actions.append(np.asarray(applied, dtype=np.float64).copy())
            data.ctrl[actuator_ids] = applied
            for _ in range(PHYSICS_STEPS_PER_ACTION):
                mujoco.mj_step(model, data)
                trace.append(
                    _trace_row(
                        model,
                        data,
                        selected_body=selected_body,
                        selected_dof=selected_dof,
                        piece_bodies=piece_bodies,
                        initial_piece_positions=initial_positions,
                        robot_body_ids=robot_body_ids,
                        jaw_body_ids=jaw_body_ids,
                    )
                )
        for _ in range(SETTLE_PHYSICS_STEPS):
            mujoco.mj_step(model, data)
            trace.append(
                _trace_row(
                    model,
                    data,
                    selected_body=selected_body,
                    selected_dof=selected_dof,
                    piece_bodies=piece_bodies,
                    initial_piece_positions=initial_positions,
                    robot_body_ids=robot_body_ids,
                    jaw_body_ids=jaw_body_ids,
                )
            )
        renderer.update_scene(data, camera=CAMERA_NAME)
        final_raw_frame = renderer.render().copy()
        _write_png(case_output / "final.png", policy_frame(final_raw_frame))
        if aligned:
            _write_png(case_output / "final_raw_simulator.png", final_raw_frame)
    finally:
        renderer.close()

    requested_array = np.asarray(requested_actions, dtype=np.float32)
    simulator_request_array = np.asarray(
        simulator_control_requests, dtype=np.float64
    )
    applied_array = np.asarray(applied_actions, dtype=np.float64)
    state_array = np.asarray(states, dtype=np.float32)
    trace_payload = json.dumps(
        trace, sort_keys=True, separators=(",", ":")
    ).encode()
    trace_sha256 = hashlib.sha256(trace_payload).hexdigest()
    np.savez_compressed(
        case_output / "rollout.npz",
        states=state_array,
        requested_actions=requested_array,
        simulator_control_requests=simulator_request_array,
        applied_actions=applied_array,
    )
    (case_output / "trace.json").write_bytes(trace_payload + b"\n")
    assistance_used = aligned or clipping_rows > 0
    score = score_episode(
        contract,
        skill_id=skill_id,
        trace=trace,
        target_position_xyz_m=target,
        initial_piece_height_m=initial_height,
        evaluation_mode="learned_policy",
        action_owner="model",
        assistance_used=assistance_used,
    )
    result = {
        "skill_id": skill_id,
        "source_square": source,
        "destination_square": destination,
        "instruction": instruction,
        "inference_seed": INFERENCE_SEED,
        "sample_count": SAMPLE_COUNT,
        "query_count": len(query_receipts),
        "query_receipts": query_receipts,
        "selected_sim_piece_body": BASELINE_PIECE_BY_FILE[source[0]],
        "bridge_mode": (
            bridge["mode"] if aligned else "frozen_scene_identity"
        ),
        "geometry_identity": geometry_identity,
        "action_adapter": (
            {
                "adapter_id": "stage_d_lift_fixed_zero_offsets_training_fit_v1",
                "transform": "sim_body_action = model_body_action + fixed_offsets; gripper identity",
                "body_joint_zero_offsets_rad": np.asarray(
                    bridge["body_joint_zero_offsets_rad"]
                ).tolist(),
                "physical_calibration_approved": False,
                "promotion_eligible": False,
            }
            if aligned
            else {
                "adapter_id": "identity_physical_radians_to_simulator_joint_controls_unqualified_v1",
                "transform": "identity",
                "physical_calibration_approved": False,
                "promotion_eligible": False,
            }
        ),
        "actuator_bounds": bounds.tolist(),
        "requested_action_min": requested_array.min(axis=0).tolist(),
        "requested_action_max": requested_array.max(axis=0).tolist(),
        "simulator_control_request_min": simulator_request_array.min(axis=0).tolist(),
        "simulator_control_request_max": simulator_request_array.max(axis=0).tolist(),
        "action_rows_clipped": clipping_rows,
        "action_values_clipped": clipping_values,
        "strict_no_action_clipping_pass": clipping_rows == 0,
        "assistance_used_for_frozen_policy_score": assistance_used,
        "state_sha256": hashlib.sha256(state_array.tobytes()).hexdigest(),
        "requested_actions_sha256": hashlib.sha256(requested_array.tobytes()).hexdigest(),
        "simulator_control_requests_sha256": hashlib.sha256(
            simulator_request_array.tobytes()
        ).hexdigest(),
        "applied_actions_sha256": hashlib.sha256(applied_array.tobytes()).hexdigest(),
        "trace_sha256": trace_sha256,
        "trace_row_count": len(trace),
        "contact_identity": contact_identity,
        "score": score,
    }
    (case_output / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5562)
    parser.add_argument("--case-limit", type=int, default=12)
    parser.add_argument(
        "--bridge-mode", choices=BRIDGE_MODES, default="frozen_scene_identity"
    )
    parser.add_argument("--training-dataset", type=Path)
    parser.add_argument("--workcell-fit-receipt", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.case_limit <= 12:
        raise SystemExit("--case-limit must be between 1 and 12")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite output: {args.output}")
    checkpoint = args.checkpoint.resolve(strict=True)
    checkpoint_manifest = args.checkpoint_manifest.resolve(strict=True)
    checkpoint_receipt = verify_exploratory_checkpoint(
        checkpoint_manifest, checkpoint
    )
    contract = load_reward_contract()
    bridge: dict[str, Any] | None = None
    if args.bridge_mode == "training_source_aligned_stage_d_diagnostic":
        if args.training_dataset is None or args.workcell_fit_receipt is None:
            raise SystemExit(
                "source-aligned mode requires --training-dataset and "
                "--workcell-fit-receipt"
            )
        bridge = _load_source_aligned_bridge(
            dataset_root=args.training_dataset,
            workcell_fit_receipt_path=args.workcell_fit_receipt,
        )
    elif args.training_dataset is not None or args.workcell_fit_receipt is not None:
        raise SystemExit(
            "training dataset and workcell receipt are only accepted in "
            "source-aligned mode"
        )
    initial_implementation = implementation_inventory()
    args.output.mkdir(parents=True)
    client = PolicyClient(
        host=args.host, port=args.port, timeout_ms=120_000, strict=False
    )
    if not client.ping():
        raise RuntimeError("GR00T policy server did not answer ping")

    results: list[dict[str, Any]] = []
    for index, skill in enumerate(
        contract["ordered_skills"][: args.case_limit]
    ):
        print(f"running {index + 1}/{args.case_limit}: {skill['skill_id']}", flush=True)
        result = run_episode(
            client=client,
            contract=contract,
            skill=skill,
            output=args.output,
            case_index=index,
            bridge=bridge,
        )
        results.append(result)
        print(
            json.dumps(
                {
                    "skill_id": result["skill_id"],
                    "task_success": result["score"]["task_consequence_success"],
                    "policy_success": result["score"]["policy_success"],
                    "reward": result["score"]["diagnostic_reward"],
                    "center_distance_m": result["score"]["final_center_distance_m"],
                    "clipped_rows": result["action_rows_clipped"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

    final_implementation = implementation_inventory()
    if final_implementation != initial_implementation:
        raise RuntimeError("evaluation implementation changed during inference")
    bridge_receipt = None
    if bridge is not None:
        bridge_receipt = {
            "mode": bridge["mode"],
            "dataset": bridge["dataset"],
            "workcell_fit": bridge["workcell_fit"],
            "board_center_in_table_frame_xy_m": list(
                bridge["board_center_in_table_frame_xy_m"]
            ),
            "board_yaw_relative_to_table_degrees": bridge[
                "board_yaw_relative_to_table_degrees"
            ],
            "body_joint_zero_offsets_rad": np.asarray(
                bridge["body_joint_zero_offsets_rad"]
            ).tolist(),
            "joint_range_envelope_rad": np.asarray(
                bridge["joint_range_envelope_rad"]
            ).tolist(),
            "task_reset_states": {
                key: np.asarray(value).tolist()
                for key, value in bridge["task_reset_states"].items()
            },
            "visual_layout_mode": bridge["visual_layout_mode"],
            "camera_mode": bridge["camera_mode"],
            "uses_training_conditioned_reset": True,
            "uses_training_fitted_workcell": True,
            "held_out_opened_during_this_evaluation": False,
            "reward_thresholds_reused_diagnostically": True,
            "frozen_evaluation_admissible": False,
            "promotion_eligible": False,
            "physical_calibration_approved": False,
        }
    frozen_mode = bridge is None
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "proof_class": (
            "learned_policy_simulation_diagnostic_nonpromoting"
            if frozen_mode
            else "training_source_aligned_policy_simulation_diagnostic_nonpromoting"
        ),
        "checkpoint": checkpoint_receipt,
        "reward_contract_path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "reward_contract_sha256": sha256_file(CONTRACT_PATH),
        "implementation_inventory": initial_implementation,
        "implementation_inventory_sha256": canonical_sha256(initial_implementation),
        "bridge": bridge_receipt,
        "fixed_run_configuration": {
            "camera": CAMERA_NAME,
            "camera_authority": (
                "scene_workcell_camera_not_c922_calibrated"
                if frozen_mode
                else "training_fitted_c922_angle_transfer_visual_only_not_evaluator_authority"
            ),
            "contact_variant": CONTACT_VARIANT,
            "inference_seed": INFERENCE_SEED,
            "sample_count": SAMPLE_COUNT,
            "sample_hz": 20,
            "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
            "settle_physics_steps": SETTLE_PHYSICS_STEPS,
            "query_stride": QUERY_STRIDE,
            "proposal_count": PROPOSAL_COUNT,
            "action_aggregation": ACTION_AGGREGATION,
            "noise_scale": NOISE_SCALE,
            "num_inference_timesteps": NUM_INFERENCE_TIMESTEPS,
            "temporal_aggregation": TEMPORAL_AGGREGATION,
        },
        "case_limit": args.case_limit,
        "full_frozen_suite_completed": args.case_limit == 12 and frozen_mode,
        "frozen_evaluation_admissible": frozen_mode,
        "results": results,
        "strict_no_action_clipping_all_cases": all(
            result["strict_no_action_clipping_pass"] for result in results
        ),
        "policy_adapter_calibrated": False,
        "promotion_eligible": False,
        "physical_authority": False,
        "sim_to_real_error_measured": False,
        "claim_boundary": (
            (
                "This is a checkpoint-5000 learned-policy diagnostic in the frozen "
                "current simulator scene using an unqualified identity action adapter. "
                "It cannot promote the checkpoint or authorize physical execution."
            )
            if frozen_mode
            else (
                "This source-aligned checkpoint-5000 diagnostic intentionally uses "
                "training-conditioned resets, a training-fitted stage-D workcell and "
                "joint adapter, a visual-only C922 angle transfer, and a review-only "
                "piece appearance correction. Frozen reward thresholds are reused only "
                "to describe consequences. The result is not a frozen policy eval, "
                "cannot promote the checkpoint, and cannot authorize physical execution."
            )
        ),
    }
    if args.case_limit == 12:
        scores = [result["score"] for result in results]
        report["aggregate"] = aggregate_scores(contract, scores)
    canonical = dict(report)
    report["canonical_payload_sha256"] = canonical_sha256(canonical)
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report.get("aggregate", report["results"][-1]["score"]), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
