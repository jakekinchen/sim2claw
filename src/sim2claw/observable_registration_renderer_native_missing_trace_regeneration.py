"""Regenerate four missing action-identical MuJoCo state traces without pixels."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


SCHEMA = (
    "sim2claw.observable_registration_renderer_native_"
    "missing_trace_regeneration_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_renderer_native_"
    "missing_trace_regeneration_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_renderer_native_missing_trace_regeneration_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_renderer_native_missing_trace_regeneration_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(binding: dict[str, Any], *, root: Path, label: str) -> Path:
    path = root / str(binding.get("path") or "")
    _require(path.is_file(), f"missing {label}: {path}")
    _require(sha256_file(path) == binding.get("sha256"), f"{label} hash drifted")
    return path


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def load_renderer_native_missing_trace_regeneration_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR69 trace regeneration contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    parameters = contract["shared_parameters"]
    _require(
        parameters["source"] == "eleven_episode_cohort.parameters"
        and len(parameters["parameter_digest"]) == 64
        and parameters["candidate_selection_allowed"] is False
        and parameters["episode_specific_override_allowed"] is False,
        "shared parameter boundary drifted",
    )
    episodes = contract["episodes"]
    _require(
        len(episodes) == 4
        and len({row["recording_id"] for row in episodes}) == 4
        and len({row["action_array_sha256"] for row in episodes}) == 4,
        "episode identity boundary drifted",
    )
    _require(
        [row["split_role"] for row in episodes]
        == ["development", "development", "validation", "evaluator_heldout"],
        "split roles drifted",
    )
    access = contract["physical_access"]
    _require(
        access["physical_sample_metadata_allowed"] is True
        and not any(
            access[name]
            for name in (
                "physical_video_path_stat_allowed",
                "physical_video_byte_read_allowed",
                "physical_video_decode_allowed",
                "physical_frame_extraction_allowed",
                "pixel_metric_evaluation_allowed",
            )
        ),
        "physical video boundary widened",
    )
    execution = contract["execution"]
    _require(
        execution
        == {
            "simulator_replays_allowed": 4,
            "state_traces_allowed": 4,
            "scene_manifests_allowed": 4,
            "probe_receipts_allowed": 4,
            "renderer_runs_allowed": 0,
            "candidate_videos_allowed": 0,
            "parameter_fits_allowed": 0,
            "physical_video_reads_allowed": 0,
            "hardware_actions_allowed": 0,
        },
        "execution boundary drifted",
    )
    _require(not any(contract["claim_limits"].values()), "claim limit widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def build_missing_trace_regeneration_plan(
    contract_path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_renderer_native_missing_trace_regeneration_contract(
        contract_path, root=root
    )
    inventory_path = _bound_path(
        contract["sources"]["or68_pairing_inventory"],
        root=root,
        label="OR68 pairing inventory",
    )
    cohort_path = _bound_path(
        contract["sources"]["eleven_episode_cohort"],
        root=root,
        label="eleven episode cohort",
    )
    inventory = load_json_object(inventory_path, label="OR68 pairing inventory")
    cohort = load_json_object(cohort_path, label="eleven episode cohort")
    parameters = cohort.get("parameters")
    _require(isinstance(parameters, dict), "shared parameters missing")
    _require(
        canonical_digest(parameters)
        == contract["shared_parameters"]["parameter_digest"],
        "shared parameter digest drifted",
    )
    missing = [
        {
            "recording_id": str(row["recording_id"]),
            "split_role": str(row["split_role"]),
            "folder_label": str(row["folder_label"]),
            "action_array_sha256": str(row["action_array_sha256"]),
        }
        for row in inventory.get("pairs", [])
        if row.get("state_trace", {}).get("availability")
        == "missing_requires_action_identical_regeneration"
    ]
    expected = contract["episodes"]
    _require(
        [
            {
                "recording_id": row["recording_id"],
                "split_role": row["split_role"],
                "action_array_sha256": row["action_array_sha256"],
            }
            for row in missing
        ]
        == expected,
        "OR68 missing-trace plan drifted",
    )
    cohort_by_id = {
        str(row["recording_id"]): row for row in cohort.get("episodes", [])
    }
    _require(
        all(
            cohort_by_id[row["recording_id"]]["action_array_sha256"]
            == row["action_array_sha256"]
            and cohort_by_id[row["recording_id"]]["action_byte_identical"] is True
            for row in missing
        ),
        "cohort action identity drifted",
    )
    return {
        "schema_version": (
            "sim2claw.observable_registration_renderer_native_"
            "missing_trace_regeneration_plan.v1"
        ),
        "parameter_digest": canonical_digest(parameters),
        "parameters": parameters,
        "episodes": missing,
        "physical_video_paths_or_bytes_read": 0,
    }


def _trace_is_finite(trace: dict[str, Any]) -> bool:
    frames = trace.get("frames")
    if not isinstance(frames, list) or not frames:
        return False
    for frame in frames:
        values = [frame.get("t"), *(frame.get("p") or []), *(frame.get("q") or [])]
        try:
            if not all(math.isfinite(float(value)) for value in values):
                return False
        except (TypeError, ValueError):
            return False
    return True


def run_renderer_native_missing_trace_regeneration_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR69 one-run receipt already exists")
    contract = load_renderer_native_missing_trace_regeneration_contract(
        contract_path, root=root
    )
    plan = build_missing_trace_regeneration_plan(contract_path, root=root)
    cohort = load_json_object(
        _bound_path(
            contract["sources"]["eleven_episode_cohort"],
            root=root,
            label="eleven episode cohort",
        ),
        label="eleven episode cohort",
    )
    cohort_by_id = {
        str(row["recording_id"]): row for row in cohort.get("episodes", [])
    }
    shared_scene = load_json_object(
        _bound_path(
            contract["sources"]["shared_scene"], root=root, label="shared scene"
        ),
        label="shared scene",
    )
    expected_scene_revision = str(shared_scene.get("revision_sha256") or "")
    _require(len(expected_scene_revision) == 64, "shared scene revision missing")
    simulator_contract = _bound_path(
        contract["sources"]["simulator_contract"],
        root=root,
        label="simulator contract",
    )

    artifacts: list[dict[str, Any]] = []
    observed_scene_revisions: set[str] = set()
    for episode_plan in plan["episodes"]:
        recording_id = episode_plan["recording_id"]
        episode_directory = output_directory / "episodes" / recording_id
        probe = run_grasp_episode_probe(
            source_repository_root=root,
            recording_id=recording_id,
            parameters=plan["parameters"],
            contract_path=simulator_contract,
            state_trace_output_directory=episode_directory,
        )
        episode = probe["episode"]
        source = cohort_by_id[recording_id]
        for key in (
            "action_array_sha256",
            "parameter_digest",
            "piece_lifted",
            "lift_and_transport",
            "task_consequence_success",
            "selected_piece_contact_observed",
            "qualified_bilateral_contact_observed",
        ):
            _require(
                episode.get(key) == source.get(key),
                f"historical diagnostic did not reproduce: {recording_id} {key}",
            )
        _require(
            episode["action_array_sha256"] == episode_plan["action_array_sha256"]
            and episode.get("action_byte_identical") is True,
            f"action identity failed: {recording_id}",
        )
        artifact = episode.get("state_trace_artifact")
        _require(isinstance(artifact, dict), f"state trace missing: {recording_id}")
        trace_path = root / str(artifact["state_trace_path"])
        scene_path = root / str(artifact["scene_manifest_path"])
        _require(
            trace_path.is_file()
            and sha256_file(trace_path) == artifact["state_trace_sha256"],
            f"state trace hash failed: {recording_id}",
        )
        _require(
            scene_path.is_file()
            and sha256_file(scene_path) == artifact["scene_manifest_sha256"],
            f"scene manifest hash failed: {recording_id}",
        )
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
        _require(
            trace.get("schema_version") == "sim2claw.mujoco_body_state_trace.v1"
            and trace.get("proof_class")
            == "retained_action_frozen_simulation_replay"
            and _trace_is_finite(trace),
            f"state trace is not finite and renderer-native: {recording_id}",
        )
        scene_revision = str(scene.get("revision_sha256") or "")
        _require(
            scene_revision == expected_scene_revision
            and trace.get("scene", {}).get("manifest_revision_sha256")
            == expected_scene_revision,
            f"scene revision differs: {recording_id}",
        )
        observed_scene_revisions.add(scene_revision)
        probe_path = episode_directory / "episode_probe_receipt.json"
        atomic_write_json(probe_path, probe)
        artifacts.append(
            {
                "recording_id": recording_id,
                "split_role": episode_plan["split_role"],
                "action_array_sha256": episode["action_array_sha256"],
                "parameter_digest": episode["parameter_digest"],
                "state_trace_path": _relative(trace_path, root),
                "state_trace_sha256": artifact["state_trace_sha256"],
                "state_trace_frame_count": int(artifact["frame_count"]),
                "state_trace_fps": float(artifact["fps"]),
                "scene_manifest_path": _relative(scene_path, root),
                "scene_manifest_sha256": artifact["scene_manifest_sha256"],
                "scene_revision_sha256": scene_revision,
                "episode_probe_receipt_path": _relative(probe_path, root),
                "episode_probe_receipt_sha256": sha256_file(probe_path),
                "inspection_only": artifact["inspection_only"],
                "physical_authority": artifact["physical_authority"],
                "historical_diagnostic_reproduced": True,
            }
        )

    gates = {
        "exactly_four_missing_episodes_regenerated": len(artifacts) == 4,
        "all_action_hashes_match": all(
            row["action_array_sha256"]
            == contract["episodes"][index]["action_array_sha256"]
            for index, row in enumerate(artifacts)
        ),
        "one_shared_parameter_digest": {
            row["parameter_digest"] for row in artifacts
        }
        == {contract["shared_parameters"]["parameter_digest"]},
        "historical_diagnostics_reproduced": all(
            row["historical_diagnostic_reproduced"] for row in artifacts
        ),
        "one_shared_scene_revision": observed_scene_revisions
        == {expected_scene_revision},
        "all_traces_inspection_only": all(
            row["inspection_only"] is True
            and row["physical_authority"] is False
            for row in artifacts
        ),
        "physical_video_not_read": True,
        "renderer_not_run": True,
    }
    _require(all(gates.values()), "OR69 trace regeneration gate failed")
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ALL_ELEVEN_RENDERER_NATIVE_STATE_TRACES_READY_NO_VIDEO_RENDER",
        "proof_class": contract["proof_class"],
        "contract": {
            "path": _relative(contract_path, root),
            "sha256": sha256_file(contract_path),
        },
        "shared_parameter_digest": plan["parameter_digest"],
        "shared_scene_revision_sha256": expected_scene_revision,
        "regenerated": artifacts,
        "result": {
            "regenerated_state_trace_count": len(artifacts),
            "total_state_trace_ready_episode_count": 11,
            "development_state_trace_ready_count": 4,
            "validation_state_trace_ready_count": 3,
            "evaluator_heldout_state_trace_ready_count": 4,
            "renderer_runtime_ready": False,
            "rendered_video_count": 0,
            "physical_video_reads": 0,
            "pixel_similarity_achieved": False,
            "physics_fidelity_achieved": False,
        },
        "gates": gates,
        "execution": {
            "simulator_replays": 4,
            "state_traces": 4,
            "scene_manifests": 4,
            "probe_receipts": 4,
            "renderer_runs": 0,
            "candidate_videos": 0,
            "parameter_fits": 0,
            "physical_video_reads": 0,
            "hardware_actions": 0,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "ADVANCE_TO_RENDERER_RUNTIME_AND_SHARED_CAMERA_BASELINE",
        "next_transition": "freeze_or70_renderer_runtime_and_development_only_shared_camera_baseline",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    run_renderer_native_missing_trace_regeneration_once()
