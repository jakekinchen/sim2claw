"""Compile and verify the read-only realized-action causal proof bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .studio_catalog import media_url


CONTRACT_SCHEMA = "sim2claw.realized_action_studio_proof_contract.v1"
MANIFEST_SCHEMA = "sim2claw.realized_action_studio_proof.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_studio_proof_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_studio_proof_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "realized_action_studio_proof_v1"
JOINT_ORDER = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)


def _bound_source(
    root: Path, entry: Mapping[str, Any], label: str
) -> tuple[Path, dict[str, Any] | None]:
    path = root / str(entry.get("path") or "")
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    payload: dict[str, Any] | None = None
    if path.suffix == ".json":
        payload = load_json_object(path, label=label)
        expected_artifact = entry.get("artifact_sha256")
        if expected_artifact and payload.get("artifact_sha256") != expected_artifact:
            raise FactoryArtifactError(f"{label} artifact rejected")
    return path, payload


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="Studio proof contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise FactoryArtifactError("unsupported Studio proof contract")
    if contract.get("proof_class") != "read_only_causal_evidence_projection":
        raise FactoryArtifactError("Studio proof class widened")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise FactoryArtifactError("Studio proof authority widened")
    rules = contract.get("rules")
    if (
        not isinstance(rules, dict)
        or rules.get("proof_class_may_be_promoted") is not False
        or rules.get("unknown_dimensions_may_be_randomized") is not False
        or rules.get("global_mapping_must_remain_unapproved") is not True
    ):
        raise FactoryArtifactError("Studio proof rules widened")
    sources = contract.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise FactoryArtifactError("Studio proof sources are missing")
    for label, entry in sources.items():
        if not isinstance(entry, dict):
            raise FactoryArtifactError(f"invalid Studio proof source: {label}")
        _bound_source(root, entry, label)
    return contract


def _tensor(
    *,
    root: Path,
    bundle_path: Path,
    tensor: Mapping[str, Any],
) -> np.ndarray:
    path = bundle_path.parent / str(tensor["file"])
    if (
        not path.is_file()
        or not path.resolve().is_relative_to(bundle_path.parent.resolve())
        or sha256_file(path) != tensor.get("file_sha256")
    ):
        raise FactoryArtifactError(f"episode tensor rejected: {path}")
    array = np.fromfile(path, dtype=np.dtype(str(tensor["dtype"])))
    shape = tuple(int(item) for item in tensor["shape"])
    if array.size != int(np.prod(shape)):
        raise FactoryArtifactError(f"episode tensor shape rejected: {path}")
    return array.reshape(shape)


def _read_video_times(path: Path, *, recording_id: str) -> np.ndarray:
    values: list[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise FactoryArtifactError(
                    f"recording sample {index} is invalid"
                ) from error
            if (
                row.get("recording_id") != recording_id
                or int(row.get("sample_index", -1)) != index
            ):
                raise FactoryArtifactError("recording sample order changed")
            values.append(float(row["overhead_video_time_seconds"]))
    return np.asarray(values, dtype=np.float64)


def _rms_rows(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.sqrt(np.mean(np.square(left - right), axis=1))


def _first_divergence(
    receipt: Mapping[str, Any], recording_id: str
) -> dict[str, Any]:
    for episode in receipt.get("episode_results", []):
        if episode.get("recording_id") == recording_id:
            return dict(episode)
    raise FactoryArtifactError("sealed first-divergence episode is missing")


def _cohort_metrics(
    receipt: Mapping[str, Any], cohort: str
) -> dict[str, Any]:
    value = receipt.get("cohort_metrics", {}).get(cohort)
    if not isinstance(value, dict):
        raise FactoryArtifactError(f"effective-plant {cohort} metrics are missing")
    return dict(value)


def compile_realized_action_studio_proof(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build one deterministic browser bundle from already-retained evidence."""

    contract = load_contract(contract_path, root=root)
    sources: dict[str, tuple[Path, dict[str, Any] | None]] = {
        label: _bound_source(root, entry, label)
        for label, entry in contract["sources"].items()
    }
    bundle_path, bundle = sources["episode_twin_bundle"]
    assert bundle is not None
    recording_id = str(contract["recording_id"])
    if (
        bundle.get("recording_id") != recording_id
        or tuple(bundle.get("joint_order", [])) != JOINT_ORDER
    ):
        raise FactoryArtifactError("episode twin identity changed")
    tensors = bundle["tensors"]
    requested = _tensor(
        root=root, bundle_path=bundle_path, tensor=tensors["operator_requested"]
    ).astype(np.float64)
    sent = _tensor(
        root=root, bundle_path=bundle_path, tensor=tensors["gateway_sent"]
    ).astype(np.float64)
    measured = _tensor(
        root=root, bundle_path=bundle_path, tensor=tensors["measured_joints"]
    ).astype(np.float64)
    timestamps = _tensor(
        root=root, bundle_path=bundle_path, tensor=tensors["source_timestamps"]
    ).astype(np.float64)
    applied_path, _ = sources["identified_applied_trace"]
    applied = np.fromfile(applied_path, dtype="<f8").reshape((-1, len(JOINT_ORDER)))

    required_shape = (
        int(contract["rules"]["action_rows_must_match"]),
        int(contract["rules"]["action_columns_must_match"]),
    )
    if any(array.shape != required_shape for array in (requested, sent, measured, applied)):
        raise FactoryArtifactError("Studio action lane shape changed")
    if timestamps.shape != (required_shape[0],):
        raise FactoryArtifactError("Studio timestamp shape changed")

    samples_path, _ = sources["recording_samples"]
    video_times = _read_video_times(samples_path, recording_id=recording_id)
    if video_times.shape != timestamps.shape:
        raise FactoryArtifactError("video/action timeline length changed")

    _, geometry = sources["static_geometry_receipt"]
    _, sage = sources["sage_lite_receipt"]
    _, divergence = sources["first_divergence_receipt"]
    _, plant = sources["effective_plant_receipt"]
    _, contact = sources["contact_receipt"]
    _, mission = sources["mission_receipt"]
    _, mission_trace = sources["mission_trace"]
    _, robustness = sources["robustness_receipt"]
    _, recording = sources["recording_receipt"]
    assert all(
        item is not None
        for item in (
            geometry,
            sage,
            divergence,
            plant,
            contact,
            mission,
            mission_trace,
            robustness,
            recording,
        )
    )
    geometry = dict(geometry or {})
    sage = dict(sage or {})
    divergence = dict(divergence or {})
    plant = dict(plant or {})
    contact = dict(contact or {})
    mission = dict(mission or {})
    mission_trace = dict(mission_trace or {})
    robustness = dict(robustness or {})
    recording = dict(recording or {})

    if (
        mission.get("ledger", {})
        .get("realized_gateway_sent_action_trajectory_real_to_sim", {})
        .get("attempts")
        != contract["rules"]["mission_attempts_must_match"]
        or mission.get("ledger", {})
        .get("realized_gateway_sent_action_trajectory_real_to_sim", {})
        .get("successes")
        != contract["rules"]["mission_successes_must_match"]
        or mission.get("initialization", {}).get("later_observed_state_rows_consumed")
        != contract["rules"]["later_observations_must_match"]
        or contact.get("eligible_dimension_count")
        != contract["rules"]["contact_parameters_must_match"]
    ):
        raise FactoryArtifactError("mission or contact proof boundary changed")
    if geometry.get("summary", {}).get("global_physical_model_mapping_approved"):
        raise FactoryArtifactError("global mapping unexpectedly promoted")
    if robustness.get("uncertainty", {}).get("unknown_dimensions_randomized"):
        raise FactoryArtifactError("unknown dimensions were randomized")

    trace_rows = mission_trace.get("rows")
    if not isinstance(trace_rows, list) or len(trace_rows) != required_shape[0]:
        raise FactoryArtifactError("mission trace row count changed")
    trace_times = np.asarray(
        [float(row["source_timestamp_seconds"]) for row in trace_rows],
        dtype=np.float64,
    )
    if not np.allclose(trace_times, timestamps, rtol=0.0, atol=1e-12):
        raise FactoryArtifactError("mission and source timestamps diverged")
    pawn_xyz = np.asarray(
        [row["selected_pawn_position_m"] for row in trace_rows], dtype=np.float64
    )
    pawn_tilt = np.asarray(
        [row["selected_pawn_tilt_degrees"] for row in trace_rows],
        dtype=np.float64,
    )
    contacts = np.asarray(
        [row["selected_jaw_contact_count"] for row in trace_rows], dtype=np.int64
    )
    pawn_planar_mm = (
        np.linalg.norm(pawn_xyz[:, :2] - pawn_xyz[0, :2], axis=1) * 1000.0
    )
    pawn_height_mm = (pawn_xyz[:, 2] - pawn_xyz[0, 2]) * 1000.0

    markers: list[dict[str, Any]] = []
    for marker in contract["failure_markers"]:
        index = int(marker["sample_index"])
        if not 0 <= index < len(timestamps):
            raise FactoryArtifactError("failure marker is outside the trace")
        markers.append(
            {
                **marker,
                "time_seconds": float(timestamps[index]),
                "video_time_seconds": float(video_times[index]),
                "pawn_planar_displacement_mm": float(pawn_planar_mm[index]),
                "pawn_height_delta_mm": float(pawn_height_mm[index]),
                "pawn_tilt_degrees": float(pawn_tilt[index]),
            }
        )

    plant_validation = _cohort_metrics(plant, "validation")
    plant_sealed = _cohort_metrics(plant, "sealed")
    recording_video = recording.get("overhead_video", {})
    video_entry = contract["sources"]["overhead_video"]
    if recording_video.get("browser_video_sha256") != video_entry["sha256"]:
        raise FactoryArtifactError("recording receipt video binding changed")

    unsigned_manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "available": True,
        "read_only": True,
        "physical_authority": False,
        "title": "Realized-action causal proof",
        "subtitle": "Retained physical D1 to D2 action trajectory versus identified simulator outcome",
        "proof_status": {
            "plant_identification": "PASS_VALIDATED_EFFECTIVE_JOINT_PLANT",
            "contact_identification": "TERMINAL_NEGATIVE",
            "action_to_outcome": "TERMINAL_NEGATIVE_0_OF_1",
            "robustness": "DETERMINISTIC_NEGATIVE_0_OF_3",
            "global_mapping_approved": False,
            "physical_task_attempts_added": 0,
        },
        "claim_boundary": mission["claim_boundary"],
        "recording": {
            "recording_id": recording_id,
            "canonical_move": "D1 → D2",
            "raw_legacy_label": "b2 → b1",
            "sample_count": required_shape[0],
            "joint_order": list(JOINT_ORDER),
            "duration_seconds": float(timestamps[-1]),
            "video": {
                "path": video_entry["path"],
                "sha256": video_entry["sha256"],
                "display_rotation_degrees": int(
                    recording_video["orientation_rotation_degrees"]
                ),
                "action_start_video_offset_seconds": float(
                    recording_video["action_start_video_offset_seconds"]
                ),
                "action_stop_video_offset_seconds": float(
                    recording_video["action_stop_video_offset_seconds"]
                ),
                "diagnostic_only": True,
                "camera_exposure_synchronized": False,
            },
        },
        "timeline": {
            "sample_count": required_shape[0],
            "time_seconds": timestamps.tolist(),
            "video_time_seconds": video_times.tolist(),
            "requested_degrees": requested.tolist(),
            "sent_degrees": sent.tolist(),
            "measured_degrees": measured.tolist(),
            "identified_applied_degrees": applied.tolist(),
            "direct_joint_rms_degrees": _rms_rows(sent, measured).tolist(),
            "identified_joint_rms_degrees": _rms_rows(
                applied, measured
            ).tolist(),
            "pawn_position_m": pawn_xyz.tolist(),
            "pawn_planar_displacement_mm": pawn_planar_mm.tolist(),
            "pawn_height_delta_mm": pawn_height_mm.tolist(),
            "pawn_tilt_degrees": pawn_tilt.tolist(),
            "selected_jaw_contact_count": contacts.tolist(),
        },
        "failure_markers": markers,
        "geometry": {
            "summary": geometry["summary"],
            "channels": geometry["channels"],
        },
        "actuator": {
            "best_sample_association": {
                "shift_samples": 3,
                "causal_latency_claim": False,
            },
            "validation": {
                "direct_joint_rms_degrees": plant_validation[
                    "direct_target"
                ]["overall_joint_rms_degrees"],
                "identified_joint_rms_degrees": plant_validation[
                    "identified_effective_plant_v1"
                ]["overall_joint_rms_degrees"],
                "direct_provisional_ee_rms_mm": plant_validation[
                    "direct_target"
                ]["provisional_ee_rms_mm"],
                "identified_provisional_ee_rms_mm": plant_validation[
                    "identified_effective_plant_v1"
                ]["provisional_ee_rms_mm"],
            },
            "sealed_report_only": {
                "direct_joint_rms_degrees": plant_sealed[
                    "direct_target"
                ]["overall_joint_rms_degrees"],
                "identified_joint_rms_degrees": plant_sealed[
                    "identified_effective_plant_v1"
                ]["overall_joint_rms_degrees"],
                "direct_provisional_ee_rms_mm": plant_sealed[
                    "direct_target"
                ]["provisional_ee_rms_mm"],
                "identified_provisional_ee_rms_mm": plant_sealed[
                    "identified_effective_plant_v1"
                ]["provisional_ee_rms_mm"],
            },
            "claim_boundary": plant["claim_boundary"],
            "sage_claim_boundary": sage["claim_boundary"],
        },
        "first_divergence": _first_divergence(divergence, recording_id),
        "contact": {
            "eligible_dimension_count": contact["eligible_dimension_count"],
            "candidate_dimensions": contact["candidate_dimensions"],
            "new_evidence_required": contact["new_evidence_required"],
            "baseline": contact["baseline"],
            "claim_boundary": contact["claim_boundary"],
        },
        "mission": {
            "verdict": mission["verdict"],
            "successes": 0,
            "attempts": 1,
            "numeric_task_success": mission["numeric_task_success"],
            "promotable_mission_success": mission[
                "promotable_mission_success"
            ],
            "outcome": mission["outcome"],
            "runtime": mission["runtime"],
        },
        "robustness": {
            "path_results": robustness["path_results"],
            "deterministic_path_successes": robustness[
                "deterministic_path_successes"
            ],
            "deterministic_path_attempts": robustness[
                "deterministic_path_attempts"
            ],
            "uncertainty": robustness["uncertainty"],
            "claim_boundary": robustness["claim_boundary"],
        },
        "availability": [
            {"id": "physical_video", "status": "available_diagnostic"},
            {"id": "requested_action", "status": "available_exact"},
            {"id": "gateway_sent_action", "status": "available_exact"},
            {"id": "measured_joint_state", "status": "available_observed"},
            {"id": "identified_applied_state", "status": "available_model"},
            {"id": "simulated_object_path", "status": "available_model"},
            {"id": "physical_metric_object_path", "status": "missing"},
            {"id": "physical_contact_state", "status": "missing"},
            {"id": "global_robot_mapping", "status": "unapproved"},
            {"id": "floor_metric_residual", "status": "missing"},
            {"id": "probabilistic_uncertainty", "status": "unavailable"},
        ],
        "hashes": {
            label: {
                "path": entry["path"],
                "sha256": entry["sha256"],
                **(
                    {"artifact_sha256": entry["artifact_sha256"]}
                    if entry.get("artifact_sha256")
                    else {}
                ),
            }
            for label, entry in contract["sources"].items()
        },
        "authority": contract["authority"],
    }
    manifest = {
        **unsigned_manifest,
        "artifact_sha256": canonical_digest(unsigned_manifest),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = output_directory / "bundle.json"
    atomic_write_json(manifest_path, manifest)
    try:
        manifest_listing_path = manifest_path.relative_to(root).as_posix()
    except ValueError:
        manifest_listing_path = manifest_path.as_posix()

    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "bundle": {
            "path": manifest_listing_path,
            "sha256": sha256_file(manifest_path),
            "artifact_sha256": manifest["artifact_sha256"],
        },
        "acceptance": {
            "requested_sent_measured_applied_rows": required_shape[0],
            "physical_video_bound": True,
            "failure_markers_bound": len(markers),
            "missing_channels_explicit": True,
            "desktop_and_mobile_surface_required": True,
            "proof_class_promoted": False,
        },
        "authority": contract["authority"],
        "claim_boundary": (
            "Deterministic read-only projection of existing C2-C7 evidence. "
            "It performs no replay, fit, promotion, or physical action."
        ),
    }
    receipt = {
        **unsigned_receipt,
        "artifact_sha256": canonical_digest(unsigned_receipt),
    }
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def load_realized_action_studio_proof(
    *,
    root: Path = REPO_ROOT,
    contract_path: Path | None = None,
    output_directory: Path | None = None,
) -> dict[str, Any]:
    """Load only a hash-valid generated proof and add its local media URL."""

    contract_path = contract_path or (
        root / CONTRACT_PATH.relative_to(REPO_ROOT)
    )
    output_directory = output_directory or (
        root / OUTPUT_DIRECTORY.relative_to(REPO_ROOT)
    )
    contract = load_contract(contract_path, root=root)
    receipt_path = output_directory / "receipt.json"
    receipt = load_json_object(receipt_path, label="Studio proof receipt")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise FactoryArtifactError("unsupported Studio proof receipt")
    unsigned_receipt = {
        key: value for key, value in receipt.items() if key != "artifact_sha256"
    }
    if receipt.get("artifact_sha256") != canonical_digest(unsigned_receipt):
        raise FactoryArtifactError("Studio proof receipt changed")
    if receipt.get("contract_sha256") != sha256_file(contract_path):
        raise FactoryArtifactError("Studio proof contract binding changed")
    bundle_path = root / str(receipt.get("bundle", {}).get("path") or "")
    if (
        not bundle_path.is_file()
        or sha256_file(bundle_path) != receipt.get("bundle", {}).get("sha256")
    ):
        raise FactoryArtifactError("Studio proof bundle changed")
    bundle = load_json_object(bundle_path, label="Studio proof bundle")
    unsigned_bundle = {
        key: value for key, value in bundle.items() if key != "artifact_sha256"
    }
    if (
        bundle.get("schema_version") != MANIFEST_SCHEMA
        or bundle.get("artifact_sha256") != canonical_digest(unsigned_bundle)
        or bundle.get("artifact_sha256")
        != receipt.get("bundle", {}).get("artifact_sha256")
    ):
        raise FactoryArtifactError("Studio proof bundle artifact changed")
    if bundle.get("authority") != contract["authority"]:
        raise FactoryArtifactError("Studio proof bundle authority changed")
    video_path = root / str(bundle["recording"]["video"]["path"])
    if (
        not video_path.is_file()
        or sha256_file(video_path)
        != contract["sources"]["overhead_video"]["sha256"]
    ):
        raise FactoryArtifactError("Studio proof video changed")
    bundle["recording"]["video"]["url"] = media_url(video_path, root)
    bundle["receipt_sha256"] = sha256_file(receipt_path)
    bundle["receipt_artifact_sha256"] = receipt["artifact_sha256"]
    return bundle


if __name__ == "__main__":
    result = compile_realized_action_studio_proof()
    print(json.dumps(result, indent=2, sort_keys=True))
