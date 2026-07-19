"""Real deterministic component adapters for LF-01 through LF-07.

The functions in this module execute existing repository components and return
evidence objects.  They contain no model calls and grant no physical authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .iphone_3dgs import (
    PROOF_CLASS as IPHONE_3DGS_PROOF_CLASS,
    SCHEMA_VERSION as IPHONE_3DGS_SCHEMA,
    PipelineConfig,
    inspect_gaussian_ply,
    run_iphone_3dgs,
)
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .recorded_replay import load_sysid_config, simulate_and_align, write_replay_receipt
from .render import write_rgb_png
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    TELEOP_PAWN_SOURCE_SQUARES,
    TELEOP_TAN_PAWN_SQUARES,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    scene_summary,
)
from .source_episode import load_source_episode, tree_manifest
from .system_identification import (
    freeze_episode_split,
    inspect_recording_catalog_inputs,
    load_manifest_episodes,
    load_split_manifest,
    run_system_identification,
)


def _inside(repo_root: Path, declared: str, *, label: str) -> Path:
    path = Path(declared)
    if not declared or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be repo-relative: {declared!r}")
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        raise ValueError(f"{label} escapes the repository: {declared}")
    return resolved


def _canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def _resolve_executable(value: str, *, label: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        resolved = candidate.resolve(strict=True)
    else:
        located = shutil.which(value)
        if located is None:
            raise ValueError(f"{label} executable is unavailable: {value}")
        resolved = Path(located).resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError(f"{label} is not executable: {resolved}")
    return resolved


def validate_reconstruction_receipt(
    receipt_path: Path, *, repo_root: Path
) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    receipt = load_json_object(receipt_path, label="iPhone 3DGS receipt")
    if receipt.get("schema_version") != IPHONE_3DGS_SCHEMA:
        raise ValueError("unsupported iPhone 3DGS receipt schema")
    declared_digest = str(receipt.get("canonical_payload_sha256", ""))
    unsigned = dict(receipt)
    unsigned.pop("canonical_payload_sha256", None)
    if declared_digest != _canonical_payload_sha256(unsigned):
        raise ValueError("iPhone 3DGS receipt canonical digest mismatch")
    if receipt.get("proof_class") != IPHONE_3DGS_PROOF_CLASS:
        raise ValueError("iPhone 3DGS receipt proof class changed")
    source = receipt.get("source")
    artifact = receipt.get("artifact")
    split = receipt.get("split")
    dependencies = receipt.get("runtime_dependencies")
    if not all(isinstance(item, dict) for item in (source, artifact, split, dependencies)):
        raise ValueError("iPhone 3DGS receipt is incomplete")
    source_path = Path(str(source["path"])).expanduser().resolve()
    artifact_path = Path(str(artifact["path"])).expanduser().resolve()
    if not source_path.is_file() or sha256_file(source_path) != source.get("sha256"):
        raise ValueError("iPhone 3DGS source video identity mismatch")
    if not artifact_path.is_relative_to(repo_root.resolve()):
        raise ValueError("reused iPhone 3DGS artifact must remain below the project root")
    if not {"artifacts", "private"} <= set(artifact_path.parts):
        raise ValueError("reused iPhone 3DGS artifact is outside artifacts/private")
    observed_artifact = inspect_gaussian_ply(artifact_path)
    for key in ("bytes", "sha256", "splat_count", "format"):
        if observed_artifact[key] != artifact.get(key):
            raise ValueError(f"iPhone 3DGS artifact {key} mismatch")
    training = set(str(item) for item in split.get("training", []))
    heldout = set(str(item) for item in split.get("heldout", []))
    if not training or not heldout or training & heldout:
        raise ValueError("iPhone 3DGS split is empty or overlapping")
    for label, dependency in dependencies.items():
        if not isinstance(dependency, dict):
            raise ValueError(f"iPhone 3DGS dependency is invalid: {label}")
        path = Path(str(dependency.get("path", ""))).expanduser().resolve()
        if not path.is_file() or sha256_file(path) != dependency.get("sha256"):
            raise ValueError(f"iPhone 3DGS dependency identity mismatch: {label}")
    return {
        "schema_version": "sim2claw.factory_visual_context_result.v1",
        "mode": "reused",
        "reconstruction_id": f"iphone-3dgs-{declared_digest[:20]}",
        "receipt_path": receipt_path.relative_to(repo_root.resolve()).as_posix(),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_canonical_sha256": declared_digest,
        "source_sha256": source["sha256"],
        "artifact": {"path": str(artifact_path), **observed_artifact},
        "training_frame_count": len(training),
        "held_out_frame_count": len(heldout),
        "relative_scale_only": True,
        "metric_authority": False,
        "collision_authority": False,
        "physical_authority": False,
    }


def execute_visual_context(
    declaration: Mapping[str, Any],
    *,
    repo_root: Path,
    attempt_dir: Path,
) -> dict[str, Any]:
    receipt_value = declaration.get("receipt")
    if receipt_value:
        receipt_path = _inside(
            repo_root, str(receipt_value), label="visual context receipt"
        )
        return validate_reconstruction_receipt(receipt_path, repo_root=repo_root)
    mode = str(declaration.get("mode", "optional"))
    if mode != "run":
        if declaration.get("required") is True:
            raise ValueError("required visual context needs a receipt or mode=run")
        return {
            "schema_version": "sim2claw.factory_visual_context_result.v1",
            "mode": "not_provided_optional",
            "reason": str(declaration.get("reason", "")),
            "relative_scale_only": True,
            "metric_authority": False,
            "collision_authority": False,
            "physical_authority": False,
        }
    video = _inside(repo_root, str(declaration.get("video", "")), label="source video")
    tools = declaration.get("tools")
    if not isinstance(tools, dict):
        raise ValueError("visual context run requires a tools object")
    output = attempt_dir / "artifacts" / "private" / "iphone-3dgs"
    receipt = run_iphone_3dgs(
        PipelineConfig(
            video=video,
            output=output,
            ffmpeg_binary=_resolve_executable(str(tools.get("ffmpeg", "ffmpeg")), label="ffmpeg"),
            ffprobe_binary=_resolve_executable(str(tools.get("ffprobe", "ffprobe")), label="ffprobe"),
            colmap_binary=_resolve_executable(str(tools.get("colmap", "colmap")), label="COLMAP"),
            brush_binary=_resolve_executable(str(tools.get("brush", "brush")), label="Brush"),
            keyframes=int(declaration.get("keyframes", 80)),
            holdout_fraction=float(declaration.get("holdout_fraction", 0.125)),
            max_resolution=int(declaration.get("max_resolution", 1920)),
            training_steps=int(declaration.get("training_steps", 30_000)),
            max_splats=int(declaration.get("max_splats", 2_000_000)),
            seed=int(declaration.get("seed", 42)),
        )
    )
    result = validate_reconstruction_receipt(
        output / "receipt.json", repo_root=repo_root
    )
    return {**result, "mode": "executed", "producer_receipt": receipt}


def build_twin_candidate(
    declaration: Mapping[str, Any],
    *,
    repo_root: Path,
    implementation_sha256: str,
) -> dict[str, Any]:
    capture_path = _inside(
        repo_root, str(declaration.get("capture_config", "")), label="capture config"
    )
    mass_path = _inside(
        repo_root, str(declaration.get("mass_profile", "")), label="mass profile"
    )
    capture = load_json_object(capture_path, label="capture config")
    mass = load_json_object(mass_path, label="mass profile")
    if mass.get("schema_version") != "sim2claw.so101_mass_profile.v1":
        raise ValueError("unsupported SO-101 mass-profile schema")
    scene_id = str(declaration.get("scene_id", ""))
    capture_scene_id = str(
        (((capture.get("simulation_estimates") or {}).get("board") or {}).get("scene_id"))
        or ""
    )
    if not scene_id or capture_scene_id != scene_id:
        raise ValueError(
            f"twin scene identity mismatch: declared={scene_id!r}, capture={capture_scene_id!r}"
        )
    dependencies = [
        {
            "role": "capture_and_measurement_config",
            "path": capture_path.relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(capture_path),
        },
        {
            "role": "mass_profile",
            "path": mass_path.relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(mass_path),
        },
    ]
    proposal = {
        "schema_version": "sim2claw.factory_twin_candidate.v1",
        "scene_id": scene_id,
        "proof_class": str(declaration.get("proof_class", "simulation_candidate")),
        "authored_by": str(declaration.get("authored_by", "repo_native_existing_candidate")),
        "implementation_sha256": implementation_sha256,
        "dependencies": dependencies,
        "uncertainties": list(
            declaration.get(
                "uncertainties",
                [
                    "contact_friction_unmeasured",
                    "compliance_unmeasured",
                    "attachment_com_and_inertia_estimated",
                    "workspace_pose_not_physical_calibration",
                ],
            )
        ),
        "measured_values_remain_distinct_from_estimates": True,
        "accepted": False,
        "acceptance_owned_by": "twin_validator",
        "physical_authority": False,
    }
    return {
        **proposal,
        "twin_candidate_id": f"twin-{canonical_digest(proposal)[:20]}",
    }


def validate_twin_candidate(
    candidate: Mapping[str, Any],
    *,
    repo_root: Path,
    attempt_dir: Path,
    settle_steps: int = 250,
) -> dict[str, Any]:
    dependencies = {
        str(item.get("role")): item
        for item in candidate.get("dependencies", [])
        if isinstance(item, dict)
    }
    capture = dependencies.get("capture_and_measurement_config")
    mass = dependencies.get("mass_profile")
    if capture is None or mass is None:
        raise ValueError("twin candidate dependency manifest is incomplete")
    capture_path = _inside(repo_root, str(capture["path"]), label="capture config")
    mass_path = _inside(repo_root, str(mass["path"]), label="mass profile")
    if sha256_file(capture_path) != capture.get("sha256") or sha256_file(
        mass_path
    ) != mass.get("sha256"):
        raise ValueError("twin candidate dependency bytes changed")
    spec = build_scene_spec(
        config_path=capture_path,
        mass_profile_path=mass_path,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        scan_overlay=False,
    )
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    initial_qpos = np.asarray(data.qpos, dtype=np.float64).copy()
    trace_rows: list[dict[str, Any]] = []
    for step in range(settle_steps + 1):
        if step:
            mujoco.mj_step(model, data)
        if step % 25 == 0 or step == settle_steps:
            trace_rows.append(
                {
                    "step": step,
                    "qpos": [float(value) for value in data.qpos],
                    "qvel": [float(value) for value in data.qvel],
                    "contact_count": int(data.ncon),
                }
            )
    finite_state = bool(
        np.isfinite(np.asarray(data.qpos)).all()
        and np.isfinite(np.asarray(data.qvel)).all()
        and np.isfinite(np.asarray(data.qacc)).all()
    )
    geom_sizes_finite = bool(np.isfinite(np.asarray(model.geom_size)).all())
    body_mass_finite_nonnegative = bool(
        np.isfinite(np.asarray(model.body_mass)).all()
        and (np.asarray(model.body_mass) >= 0).all()
    )
    ctrlrange = np.asarray(model.actuator_ctrlrange)
    control_ranges_ordered = bool(
        ctrlrange.shape == (model.nu, 2)
        and np.isfinite(ctrlrange).all()
        and (ctrlrange[:, 0] < ctrlrange[:, 1]).all()
    )
    robot_joints = [f"left_{name}" for name in ROBOT_JOINTS]
    articulation_complete = all(
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) >= 0
        and mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name) >= 0
        for name in robot_joints
    )
    task_pieces = [
        *(f"brown_pawn_{square}" for square in TELEOP_PAWN_SOURCE_SQUARES),
        *(f"tan_pawn_{square}" for square in TELEOP_TAN_PAWN_SQUARES),
    ]
    task_fixtures_complete = all(
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) >= 0
        and mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{name}_free") >= 0
        for name in task_pieces
    )
    task_targets_finite = all(
        np.isfinite(np.asarray(board_square_center(square), dtype=np.float64)).all()
        for square in (
            *TELEOP_PAWN_SOURCE_SQUARES,
            *TELEOP_TAN_PAWN_SQUARES,
        )
    )
    baseline_qacc = np.asarray(data.qacc, dtype=np.float64).copy()
    actuation_response_delta = 0.0
    if control_ranges_ordered and model.nu:
        original_control = np.asarray(data.ctrl, dtype=np.float64).copy()
        actuator = 0
        span = float(ctrlrange[actuator, 1] - ctrlrange[actuator, 0])
        data.ctrl[actuator] = float(
            np.clip(
                original_control[actuator] + 0.05 * span,
                ctrlrange[actuator, 0],
                ctrlrange[actuator, 1],
            )
        )
        if data.ctrl[actuator] == original_control[actuator]:
            data.ctrl[actuator] = float(original_control[actuator] - 0.05 * span)
        mujoco.mj_forward(model, data)
        actuation_response_delta = float(
            np.max(np.abs(np.asarray(data.qacc, dtype=np.float64) - baseline_qacc))
        )
        data.ctrl[:] = original_control
        mujoco.mj_forward(model, data)
    cameras = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_CAMERA, index)
        for index in range(model.ncam)
    ]
    required_cameras = {"photo_reference", "workcell", "overhead"}
    cameras_complete = required_cameras <= set(cameras)
    renderer = mujoco.Renderer(model, height=96, width=96)
    try:
        renderer.update_scene(data, camera="photo_reference")
        image = renderer.render()
    finally:
        renderer.close()
    render_path = attempt_dir / "twin_validation" / "photo_reference.png"
    write_rgb_png(render_path, image)
    contact_pairs = []
    for index in range(data.ncon):
        contact = data.contact[index]
        contact_pairs.append(
            {
                "geom1": mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, int(contact.geom1)
                ),
                "geom2": mujoco.mj_id2name(
                    model, mujoco.mjtObj.mjOBJ_GEOM, int(contact.geom2)
                ),
                "distance_m": float(contact.dist),
            }
        )
    summary = scene_summary(
        config_path=capture_path,
        mass_profile_path=mass_path,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
    )
    scene_identity_matches = (
        summary["board"]["scene_id"] == candidate.get("scene_id")
    )
    maximum_penetration_m = max(
        (max(0.0, -float(row["distance_m"])) for row in contact_pairs),
        default=0.0,
    )
    provenance_complete = bool(
        candidate.get("schema_version") == "sim2claw.factory_twin_candidate.v1"
        and len(str(candidate.get("implementation_sha256") or "")) == 64
        and candidate.get("measured_values_remain_distinct_from_estimates") is True
        and candidate.get("accepted") is False
        and candidate.get("acceptance_owned_by") == "twin_validator"
        and candidate.get("physical_authority") is False
    )
    gates = {
        "compile_and_finite_dynamics": finite_state,
        "geometry_arrays_finite": geom_sizes_finite,
        "body_masses_finite_nonnegative": body_mass_finite_nonnegative,
        "actuator_ranges_finite_and_ordered": control_ranges_ordered,
        "robot_articulation_complete": articulation_complete,
        "task_piece_fixtures_complete": task_fixtures_complete,
        "task_target_coordinates_finite": task_targets_finite,
        "actuation_sensitivity_nonzero": actuation_response_delta > 1e-9,
        "collision_penetration_bounded": maximum_penetration_m <= 0.01,
        "required_render_cameras_present": cameras_complete,
        "scene_identity_matches": scene_identity_matches,
        "render_nonempty": render_path.stat().st_size > 0,
        "provenance_and_authority_complete": provenance_complete,
    }
    return {
        "schema_version": "sim2claw.factory_twin_validation.v1",
        "twin_candidate_id": str(candidate.get("twin_candidate_id", "")),
        "scene_id": str(candidate.get("scene_id", "")),
        "model_dimensions": {
            "nbody": model.nbody,
            "ngeom": model.ngeom,
            "njnt": model.njnt,
            "nq": model.nq,
            "nv": model.nv,
            "nu": model.nu,
            "ncam": model.ncam,
        },
        "settle_steps": settle_steps,
        "maximum_absolute_qpos_change": float(
            np.max(np.abs(np.asarray(data.qpos) - initial_qpos))
        ),
        "gates": gates,
        "passed": all(gates.values()),
        "trace_sha256": canonical_digest(trace_rows),
        "trace_samples": trace_rows,
        "render": {
            "path": render_path.relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(render_path),
            "camera": "photo_reference",
            "width": 96,
            "height": 96,
        },
        "cameras": cameras,
        "contacts_after_settle": contact_pairs,
        "sensitivity": {
            "actuator_index": 0,
            "maximum_absolute_qacc_delta": actuation_response_delta,
            "minimum_required_delta": 1e-9,
        },
        "collision": {
            "maximum_penetration_m": maximum_penetration_m,
            "maximum_allowed_penetration_m": 0.01,
        },
        "task_fixtures": {
            "piece_body_ids": task_pieces,
            "target_squares": sorted(
                set(TELEOP_PAWN_SOURCE_SQUARES)
                | set(TELEOP_TAN_PAWN_SQUARES)
            ),
        },
        "scene_summary": summary,
        "uncertainties_preserved": list(candidate.get("uncertainties", [])),
        "validation_owner": "twin_validator",
        "physical_authority": False,
    }


def inspect_demonstration_inputs(
    *,
    catalog_path: Path,
    config_path: Path,
    repo_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    report = inspect_recording_catalog_inputs(
        catalog_path,
        repo_root=repo_root,
        config_path=config_path,
        inspection_scope="explicit_repo_root",
        output_path=output_path,
    )
    return report


def inspect_canonical_source_episodes(
    episode_directories: list[str], *, repo_root: Path
) -> dict[str, Any]:
    """Load exact canonical episodes and retain raw-to-canonical byte lineage."""

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for declared in episode_directories:
        directory = _inside(repo_root, declared, label="canonical source episode")
        if not directory.is_dir():
            raise ValueError(f"canonical source episode is not a directory: {declared}")
        receipt, samples = load_source_episode(directory)
        episode_id = str(receipt.get("recording_id", ""))
        if not episode_id or episode_id in seen:
            raise ValueError("canonical source episodes need unique recording ids")
        seen.add(episode_id)
        rows.append(
            {
                "episode_id": episode_id,
                "directory": directory.relative_to(repo_root.resolve()).as_posix(),
                "recording_receipt_sha256": sha256_file(
                    directory / "recording_receipt.json"
                ),
                "samples_sha256": str(receipt["samples_sha256"]),
                "sample_count": len(samples),
                "source_contract_sha256": str(receipt["source_contract_sha256"]),
                "scene_id": str(receipt["scene_id"]),
                "board_pose_id": str(receipt["board_pose_id"]),
                "tree_manifest_sha256": canonical_digest(tree_manifest(directory)),
                "training_admitted": False,
            }
        )
    unsigned = {
        "schema_version": "sim2claw.factory_canonical_source_inventory.v1",
        "episode_count": len(rows),
        "episodes": rows,
        "conflicts": [],
        "silent_repairs": 0,
        "training_admitted": False,
    }
    return {**unsigned, "inventory_sha256": canonical_digest(unsigned)}


def freeze_and_replay_ready_episodes(
    *,
    catalog_path: Path,
    config_path: Path,
    output_directory: Path,
    repo_root: Path,
    strategy: str,
    held_out_column: str | None = None,
) -> dict[str, Any]:
    split_path = output_directory / "split_manifest.json"
    manifest = freeze_episode_split(
        catalog_path,
        config_path,
        split_path,
        strategy=strategy,
        held_out_column=held_out_column,
    )
    config = load_sysid_config(config_path)
    loaded_manifest = load_split_manifest(split_path, config=config)
    episodes = load_manifest_episodes(loaded_manifest, config)
    replay_rows: list[dict[str, Any]] = []
    for role in ("train", "held_out"):
        for episode in episodes[role]:
            replay = simulate_and_align(
                episode,
                config,
                model_base_directory=config_path.parent,
            )
            replay_root = output_directory / "exact_replays" / role / episode.episode_id
            receipt = write_replay_receipt(replay, config, replay_root)
            receipt_path = replay_root / receipt["receipt_path"]
            replay_rows.append(
                {
                    "episode_id": episode.episode_id,
                    "role": role,
                    "receipt_path": receipt_path.relative_to(
                        repo_root.resolve()
                    ).as_posix(),
                    "receipt_sha256": sha256_file(receipt_path),
                    "source_sha256": episode.source_sha256,
                }
            )
    return {
        "schema_version": "sim2claw.factory_replay_readiness.v1",
        "split_id": manifest["split_id"],
        "split_manifest_path": split_path.relative_to(repo_root.resolve()).as_posix(),
        "split_manifest_sha256": sha256_file(split_path),
        "split_counts": manifest["split_counts"],
        "assignment_digest_sha256": manifest["assignment_digest_sha256"],
        "exact_replay_count": len(replay_rows),
        "exact_replays": replay_rows,
        "held_out_rows_opened": 0,
        "training_rows_emitted": 0,
        "split_owner": manifest["owner"],
        "physical_authority": False,
    }


def run_calibration_fit(
    *,
    split_manifest_path: Path,
    config_path: Path,
    output_directory: Path,
    repo_root: Path,
    baseline_twin_id: str,
    backend: str = "auto",
) -> dict[str, Any]:
    fit = run_system_identification(
        split_manifest_path,
        config_path=config_path,
        output_directory=output_directory,
        backend=backend,
    )
    receipt_path = output_directory / str(fit["receipt_path"])
    candidate_id_payload = {
        "baseline_twin_id": baseline_twin_id,
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "sysid_config_sha256": sha256_file(config_path),
        "candidate_parameters": fit["candidate_parameters"],
    }
    return {
        "schema_version": "sim2claw.factory_calibration_fit.v1",
        "baseline_twin_id": baseline_twin_id,
        "candidate_twin_id": f"calibrated-twin-{canonical_digest(candidate_id_payload)[:20]}",
        "split_manifest_path": split_manifest_path.relative_to(
            repo_root.resolve()
        ).as_posix(),
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "sysid_config_path": config_path.relative_to(repo_root.resolve()).as_posix(),
        "sysid_config_sha256": sha256_file(config_path),
        "fit_receipt_path": receipt_path.relative_to(repo_root.resolve()).as_posix(),
        "fit_receipt_sha256": sha256_file(receipt_path),
        "fit": fit,
        "trainer_or_runner_can_promote": False,
        "physical_authority": False,
    }


def run_independent_calibration_evaluator(
    *,
    split_manifest_path: Path,
    config_path: Path,
    fit_receipt_path: Path,
    output_directory: Path,
    repo_root: Path,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "calibration_evaluation.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2claw.learning_factory_calibration_eval",
            "--split",
            str(split_manifest_path),
            "--config",
            str(config_path),
            "--fit-receipt",
            str(fit_receipt_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    stdout_path = output_directory / "evaluator.stdout.log"
    stderr_path = output_directory / "evaluator.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            "independent calibration evaluator failed; "
            f"see {stderr_path.relative_to(repo_root.resolve())}"
        )
    evaluation = load_json_object(output_path, label="calibration evaluation")
    declared_digest = str(evaluation.get("artifact_sha256", ""))
    unsigned = dict(evaluation)
    unsigned.pop("artifact_sha256", None)
    if declared_digest != canonical_digest(unsigned):
        raise ValueError("independent calibration evaluation digest mismatch")
    return {
        **evaluation,
        "process": {
            "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
            "exit_code": completed.returncode,
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "output_path": output_path.relative_to(repo_root.resolve()).as_posix(),
            "output_sha256": sha256_file(output_path),
        },
    }


def run_independent_goal_act_evaluator(
    *,
    checkpoint_path: Path,
    training_receipt_path: Path,
    cohort_path: Path,
    task_contract_path: Path,
    output_directory: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Invoke the goal-conditioned policy evaluator as a separate process."""

    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / "goal_act_evaluation.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2claw.goal_act_evaluator",
            "--checkpoint",
            str(checkpoint_path),
            "--training-receipt",
            str(training_receipt_path),
            "--cohort",
            str(cohort_path),
            "--task-contract",
            str(task_contract_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    stdout_path = output_directory / "evaluator.stdout.log"
    stderr_path = output_directory / "evaluator.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode not in {0, 2} or not output_path.is_file():
        raise RuntimeError(
            "independent goal ACT evaluator failed; "
            f"see {stderr_path.relative_to(repo_root.resolve())}"
        )
    evaluation = load_json_object(output_path, label="goal ACT evaluation")
    declared_digest = str(evaluation.get("artifact_sha256", ""))
    unsigned = dict(evaluation)
    unsigned.pop("artifact_sha256", None)
    if declared_digest != canonical_digest(unsigned):
        raise ValueError("independent goal ACT evaluation digest mismatch")
    expected_exit = 0 if evaluation.get("verdict") == "admitted" else 2
    if completed.returncode != expected_exit:
        raise ValueError("goal ACT evaluator exit code disagrees with its verdict")
    return {
        **evaluation,
        "process": {
            "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
            "exit_code": completed.returncode,
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "output_path": output_path.relative_to(repo_root.resolve()).as_posix(),
            "output_sha256": sha256_file(output_path),
        },
    }


def run_independent_promotion(
    *,
    project_path: Path,
    stage_results: dict[str, dict[str, Any]],
    task_contract_path: Path,
    output_directory: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Join factory evidence in a separate promotion/rejection process."""

    resolved_root = repo_root.resolve()
    resolved_project = (
        project_path.resolve()
        if project_path.is_absolute()
        else (resolved_root / project_path).resolve()
    )
    try:
        subprocess_project = resolved_project.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ValueError("promotion project path escapes the repository") from error
    output_directory.mkdir(parents=True, exist_ok=True)
    input_manifest_path = output_directory / "promotion_inputs.json"
    atomic_write_json(
        input_manifest_path,
        {
            "schema_version": "sim2claw.factory_promotion_inputs.v1",
            "stage_result_paths": {
                stage: str(result["result_path"])
                for stage, result in sorted(stage_results.items())
            },
            "stage_result_sha256": {
                stage: str(result["result_sha256"])
                for stage, result in sorted(stage_results.items())
            },
        },
    )
    process_output = output_directory / "independent"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2claw.learning_factory_promotion",
            "--project",
            subprocess_project,
            "--input-manifest",
            str(input_manifest_path),
            "--task-contract",
            str(task_contract_path),
            "--output-directory",
            str(process_output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    stdout_path = output_directory / "promotion.stdout.log"
    stderr_path = output_directory / "promotion.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    receipt_path = process_output / "promotion_receipt.json"
    if completed.returncode not in {0, 2} or not receipt_path.is_file():
        stderr_tail = completed.stderr.strip()[-2000:] or "<empty stderr>"
        raise RuntimeError(
            "independent promotion process failed; "
            f"see {stderr_path.relative_to(repo_root.resolve())}; "
            f"exit_code={completed.returncode}; stderr_tail={stderr_tail}"
        )
    receipt = load_json_object(receipt_path, label="independent promotion receipt")
    unsigned = dict(receipt)
    declared = str(unsigned.pop("artifact_sha256", ""))
    if declared != canonical_digest(unsigned):
        raise ValueError("independent promotion receipt digest mismatch")
    expected_exit = 0 if receipt.get("state") == "promoted" else 2
    if completed.returncode != expected_exit:
        raise ValueError("promotion process exit code disagrees with its state")
    package_manifest = process_output / "skill_package/package_manifest.json"
    package = None
    if package_manifest.is_file():
        package = load_json_object(package_manifest, label="skill package manifest")
        package = {
            **package,
            "manifest_path": package_manifest.relative_to(repo_root.resolve()).as_posix(),
            "manifest_file_sha256": sha256_file(package_manifest),
        }
    return {
        **receipt,
        "promotion_receipt_path": receipt_path.relative_to(repo_root.resolve()).as_posix(),
        "promotion_receipt_file_sha256": sha256_file(receipt_path),
        "skill_package": package,
        "process": {
            "python_executable_sha256": sha256_file(Path(sys.executable).resolve()),
            "exit_code": completed.returncode,
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "input_manifest_sha256": sha256_file(input_manifest_path),
        },
    }
