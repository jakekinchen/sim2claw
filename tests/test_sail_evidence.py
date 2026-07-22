from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.sail.contracts import SailContractError, verify_contract
from sim2claw.sail.evidence import compile_campaign, inventory_campaign


REPO_ROOT = Path(__file__).resolve().parents[1]
RETAINED_CAMPAIGN = REPO_ROOT / "configs" / "sail" / "campaign_retired_bg_v1.json"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _binding(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def _sample(recording_id: str, index: int) -> dict:
    base = float(index)
    return {
        "recording_id": recording_id,
        "episode_id": recording_id,
        "follower_requested_degrees": [base + value for value in range(6)],
        "follower_command_degrees": [base + value + 0.1 for value in range(6)],
        "follower_actual_position_degrees": [base + value + 0.2 for value in range(6)],
        "follower_actual_velocity_degrees_s": [float(value) for value in range(6)],
        "available_motor_current_raw": {
            name: float(index + joint_index)
            for joint_index, name in enumerate(
                (
                    "shoulder_pan",
                    "shoulder_lift",
                    "elbow_flex",
                    "wrist_flex",
                    "wrist_roll",
                    "gripper",
                )
            )
        },
        "timestamp_monotonic_seconds": float(index) * 0.05,
        "control_dt_seconds": 0.05,
        "overhead_video_time_seconds": 1.0 + float(index) * 0.05,
    }


def _trace_row(index: int) -> dict:
    action = [0.01 * float(index + value) for value in range(6)]
    mapped = [value + 0.001 for value in action]
    baseline = [value + 0.002 for value in action]
    selected = [value + 0.0015 for value in action]
    mapped_ee = [0.1 + index * 0.01, 0.2, 0.3]
    return {
        "sample_index": index,
        "elapsed_seconds": float(index) * 0.05,
        "applied_action": action,
        "mapped_measured_joint_state": mapped,
        "current_baseline": {
            "simulated_joint_state": baseline,
            "mapped_measured_ee_xyz_m": mapped_ee,
            "simulated_ee_xyz_m": [value + 0.002 for value in mapped_ee],
            "ee_error_m": 0.002,
        },
        "selected_load_bias": {
            "simulated_joint_state": selected,
            "mapped_measured_ee_xyz_m": mapped_ee,
            "simulated_ee_xyz_m": [value + 0.0015 for value in mapped_ee],
            "ee_error_m": 0.0015,
        },
    }


def _fixture_campaign(tmp_path: Path) -> Path:
    recording_id = "fixture-physical-001"
    data_root = tmp_path / "data" / recording_id
    data_root.mkdir(parents=True)
    rows = [_sample(recording_id, 0), _sample(recording_id, 1)]
    samples_path = data_root / "samples.jsonl"
    samples_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    video_path = data_root / "overhead.mp4"
    video_path.write_bytes(b"fixture-video")
    receipt_path = data_root / "receipt.json"
    _write_json(
        receipt_path,
        {
            "recording_id": recording_id,
            "sample_count": 2,
            "proof_class": "physical_teleoperation_source_unqualified",
            "scene_id": "fixture-scene",
            "board_pose_id": "fixture-board",
            "initial_layout_id": "fixture-layout",
            "source_contract_sha256": "1" * 64,
            "outcome_label": "operator_success",
            "backend": {"follower_calibration_sha256": "2" * 64},
        },
    )
    catalog_path = tmp_path / "physical_catalog.json"
    _write_json(
        catalog_path,
        {
            "episodes": [
                {
                    "recording_id": recording_id,
                    "sample_count": 2,
                    "proof_class": "physical_teleoperation_source_unqualified",
                    "assets": {
                        "samples": samples_path.relative_to(tmp_path).as_posix(),
                        "receipt": receipt_path.relative_to(tmp_path).as_posix(),
                        "overhead_video": video_path.relative_to(tmp_path).as_posix(),
                    },
                    "samples_sha256": sha256_file(samples_path),
                    "receipt_sha256": sha256_file(receipt_path),
                    "overhead_video_sha256": sha256_file(video_path),
                }
            ],
            "discarded_recordings": [],
        },
    )
    split_path = tmp_path / "physical_split.json"
    _write_json(
        split_path,
        {
            "split_counts": {"train": 1, "held_out": 0},
            "episodes": [
                {
                    "episode_id": recording_id,
                    "split": "train",
                    "proof_class": "physical_teleoperation_source_unqualified",
                }
            ],
        },
    )
    telemetry_path = tmp_path / "telemetry.json"
    _write_json(telemetry_path, {"expected_inventory": {"episode_count": 1, "sample_count": 2}})
    event_path = tmp_path / "event.json"
    _write_json(event_path, {"authority": {"training_admission": False}})
    action_contract_path = tmp_path / "action_contract.json"
    _write_json(
        action_contract_path,
        {
            "action_invariance": {
                "no_ik_corrections": True,
                "no_post_policy_offsets": True,
                "no_corrective_suffix": True,
                "no_assistance": True,
                "no_candidate_specific_action_mapping": True,
                "no_clipping": True,
                "require_identical_shape_dtype_and_sha256": True,
            }
        },
    )
    fidelity_contract_path = tmp_path / "fidelity_contract.json"
    _write_json(fidelity_contract_path, {"schema_version": "fixture.fidelity.v1"})
    fidelity_receipt_path = tmp_path / "fidelity_receipt.json"
    _write_json(fidelity_receipt_path, {"schema_version": "fixture.fidelity_receipt.v1"})

    trace_path = tmp_path / "trace.json"
    trace_rows = [_trace_row(0), _trace_row(1)]
    action_array = np.ascontiguousarray(
        [row["applied_action"] for row in trace_rows], dtype=np.float64
    )
    action_sha = hashlib.sha256(action_array.tobytes(order="C")).hexdigest()
    _write_json(
        trace_path,
        {
            "schema_version": "fixture.trace.v1",
            "recording_id": recording_id,
            "rows": trace_rows,
        },
    )
    servo_receipt_path = tmp_path / "servo_receipt.json"
    _write_json(
        servo_receipt_path,
        {
            "proof_class": "action_frozen_simulator_servo_load_bias_diagnostic",
            "action_arrays_byte_identical_across_variants": True,
            "traces": [
                {
                    "recording_id": recording_id,
                    "trace_path": str(trace_path),
                    "trace_sha256": sha256_file(trace_path),
                    "action": {"shape": [2, 6], "dtype": "float64", "sha256": action_sha},
                    "metrics": {
                        "current_baseline": {"sample_count": 2, "ee_rms_m": 0.002},
                        "selected_load_bias": {"sample_count": 2, "ee_rms_m": 0.0015},
                    },
                }
            ],
            "confirmation_action_hashes": {
                "fixture-confirmation-001": {
                    "shape": [1, 6],
                    "dtype": "float64",
                    "sha256": "3" * 64,
                }
            },
        },
    )
    context_path = tmp_path / "context.json"
    _write_json(context_path, {"schema_version": "fixture.context.v1"})
    source_paths = {
        "physical_catalog": catalog_path,
        "physical_split": split_path,
        "telemetry_contract": telemetry_path,
        "event_contract": event_path,
        "action_frozen_contract": action_contract_path,
        "fidelity_contract": fidelity_contract_path,
        "servo_load_bias_receipt": servo_receipt_path,
        "fidelity_receipt": fidelity_receipt_path,
    }
    campaign_path = tmp_path / "campaign.json"
    _write_json(
        campaign_path,
        {
            "schema_version": "sim2claw.sail_retained_evidence_campaign.v1",
            "campaign_id": "fixture-retained-v1",
            "workcell_id": "fixture-workcell",
            "source_owner": "fixture-owner",
            "source_bindings": {
                name: _binding(path, tmp_path) for name, path in source_paths.items()
            },
            "context_artifacts": [
                {
                    "id": f"context-{index}",
                    **_binding(context_path, tmp_path),
                    "proof_class": "fixture",
                    "interpretation": "fixture only",
                }
                for index in range(6)
            ],
            "declared_omissions": [],
            "expected_inventory": {
                "physical_episode_count": 1,
                "physical_sample_count": 2,
                "physical_train_episode_count": 1,
                "physical_held_out_episode_count": 0,
                "action_frozen_development_episode_count": 1,
                "already_open_confirmation_episode_count": 1,
                "context_artifact_count": 6,
                "emitted_evidence_count": 3,
            },
            "physical_import": {
                "proof_class": "physical_teleoperation_source_unqualified",
                "action_field": "follower_command_degrees",
                "action_dtype": "float64",
                "action_ordering": "fixture_time_joint_c",
                "joint_names": [
                    "shoulder_pan",
                    "shoulder_lift",
                    "elbow_flex",
                    "wrist_flex",
                    "wrist_roll",
                    "gripper",
                ],
            },
            "simulator_import": {
                "proof_class": "retained_action_frozen_simulator_replay",
                "action_ordering": "fixture_time_joint_c",
                "development_role": "validation",
                "confirmation_role": "already_open_regression",
                "selected_candidate_id": "fixture-candidate",
                "confirmation_selection_use": "none_already_opened_regression_only",
            },
            "determinism": {
                "catalog_sort": "proof_class_then_evidence_id",
                "json_encoding": "utf8_indent2_sort_keys_trailing_newline",
                "array_hash": "sha256_numpy_contiguous_native_float64_c_order",
                "generated_at": "2026-07-21T00:00:00Z",
            },
            "authority": {
                "mutate_sources": False,
                "infer_missing_observations": False,
                "open_new_held_out_data": False,
                "physical_capture": False,
                "robot_motion": False,
                "simulator_promotion": False,
                "training_admission": False,
                "policy_selection": False,
                "physical_transfer": False,
            },
        },
    )
    return campaign_path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _refresh_campaign_binding(campaign_path: Path, name: str, source_path: Path) -> None:
    campaign = _load(campaign_path)
    campaign["source_bindings"][name]["sha256"] = sha256_file(source_path)
    _write_json(campaign_path, campaign)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_missing_source_and_digest_drift_fail_closed(tmp_path: Path) -> None:
    campaign_path = _fixture_campaign(tmp_path)
    campaign = _load(campaign_path)
    catalog_path = tmp_path / campaign["source_bindings"]["physical_catalog"]["path"]
    catalog = _load(catalog_path)
    video_path = tmp_path / catalog["episodes"][0]["assets"]["overhead_video"]
    video_path.unlink()
    with pytest.raises(SailContractError, match="missing"):
        inventory_campaign(campaign_path, repo_root=tmp_path)
    video_path.write_bytes(b"changed-video")
    with pytest.raises(SailContractError, match="digest mismatch"):
        inventory_campaign(campaign_path, repo_root=tmp_path)


def test_proof_class_confusion_is_rejected(tmp_path: Path) -> None:
    campaign_path = _fixture_campaign(tmp_path)
    campaign = _load(campaign_path)
    catalog_path = tmp_path / campaign["source_bindings"]["physical_catalog"]["path"]
    catalog = _load(catalog_path)
    catalog["episodes"][0]["proof_class"] = "physical_task"
    _write_json(catalog_path, catalog)
    _refresh_campaign_binding(campaign_path, "physical_catalog", catalog_path)
    with pytest.raises(SailContractError, match="proof class changed"):
        inventory_campaign(campaign_path, repo_root=tmp_path)


def test_absent_channels_remain_false_masks_and_contracts_verify(tmp_path: Path) -> None:
    campaign_path = _fixture_campaign(tmp_path)
    output = tmp_path / "compiled"
    result = compile_campaign(campaign_path, output, repo_root=tmp_path)
    assert result["counts"]["evidence_count"] == 3
    physical = _load(output / "calibration" / "physical__fixture-physical-001.json")
    verify_contract(physical)
    assert physical["proof_class"] == "physical_teleoperation_source_unqualified"
    assert physical["observations"]["physical_contact_force"]["values"] == [None, None]
    assert physical["observations"]["physical_contact_force"]["available"] == [False, False]
    assert physical["outcomes"]["physical_task_success"]["observed"] is False


def test_action_count_and_hash_must_reconcile(tmp_path: Path) -> None:
    campaign_path = _fixture_campaign(tmp_path)
    campaign = _load(campaign_path)
    servo_path = tmp_path / campaign["source_bindings"]["servo_load_bias_receipt"]["path"]
    servo = _load(servo_path)
    trace_path = Path(servo["traces"][0]["trace_path"])
    trace = _load(trace_path)
    trace["rows"][0]["applied_action"][0] += 1.0
    _write_json(trace_path, trace)
    servo["traces"][0]["trace_sha256"] = sha256_file(trace_path)
    _write_json(servo_path, servo)
    _refresh_campaign_binding(campaign_path, "servo_load_bias_receipt", servo_path)
    with pytest.raises(SailContractError, match="action descriptor sha256 changed"):
        inventory_campaign(campaign_path, repo_root=tmp_path)


def test_repeated_compilation_is_byte_deterministic(tmp_path: Path) -> None:
    campaign_path = _fixture_campaign(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = compile_campaign(campaign_path, first, repo_root=tmp_path)
    second_result = compile_campaign(campaign_path, second, repo_root=tmp_path)
    assert _tree_hashes(first) == _tree_hashes(second)
    assert first_result["catalog_sha256"] == second_result["catalog_sha256"]
    assert first_result["receipt_sha256"] == second_result["receipt_sha256"]


@pytest.mark.skipif(
    not (REPO_ROOT / "datasets" / "manipulation_source_recordings").is_dir(),
    reason="owner-local retained evidence is unavailable",
)
def test_gold_16_retained_inventory() -> None:
    inventory = inventory_campaign(RETAINED_CAMPAIGN)
    assert inventory["status"] == "ready"
    assert inventory["counts"] == {
        "evidence_count": 31,
        "physical_episode_count": 18,
        "physical_sample_count": 7741,
        "action_frozen_development_episode_count": 11,
        "already_open_confirmation_episode_count": 2,
        "by_proof_class": {
            "physical_teleoperation_source_unqualified": 18,
            "retained_action_frozen_simulator_replay": 13,
        },
        "by_split_role": {
            "already_open_regression": 2,
            "held_out": 3,
            "train": 15,
            "validation": 11,
        },
    }
    assert inventory["sources_hash_verified"] is True
    assert inventory["proof_classes_separated"] is True
    assert inventory["training_admitted"] is False
