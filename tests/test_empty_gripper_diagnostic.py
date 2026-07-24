from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import sim2claw.empty_gripper_diagnostic as diagnostic_module
from sim2claw.cli import build_parser
from sim2claw.empty_gripper_diagnostic import (
    DIAGNOSTIC_SCHEMA,
    EmptyGripperDiagnosticError,
    derive_empty_gripper_diagnostic,
    load_empty_gripper_contract,
)
from sim2claw.joint_limit_comparison import (
    JointLimitComparisonError,
    run_joint_limit_comparison,
)


JOINTS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(
    root: Path,
    *,
    out_of_range: bool = False,
    assistance_index: int | None = None,
) -> Path:
    source = root / "source"
    source.mkdir(parents=True)
    (root / "scene.py").write_bytes(b"scene identity\n")
    (root / "replay.py").write_bytes(b"replay identity\n")
    requested_gripper = (
        ([0.0] * 20 + [100.0] * 20 + [0.0] * 20) * 3
    )
    actual_gripper = [0.0, 0.0, 0.0] + requested_gripper[:-3]
    rows = []
    for index, gripper in enumerate(requested_gripper):
        body = [0.0] * 5
        if index < 60:
            body[0] = min(8.0, index * 0.2)
        if out_of_range:
            body[1] = -106.0
        values = [*body, gripper]
        actual = [*body, actual_gripper[index]]
        rows.append(
            {
                "recording_id": "fixture-recording",
                "timestamp_monotonic_seconds": index * 0.05,
                "assistance": int(index == assistance_index),
                "intervention": 0,
                "current_telemetry_stale": False,
                "current_telemetry_hz": 5.0,
                "follower_requested_degrees": values,
                "follower_command_degrees": values,
                "follower_actual_position_degrees": actual,
                "available_motor_current_raw": {
                    joint: float(4 if joint == "gripper" and gripper > 50 else 1)
                    for joint in JOINTS
                },
            }
        )
    samples = source / "samples.jsonl"
    samples.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    receipt = {
        "recording_id": "fixture-recording",
        "mode": "physical_follower",
        "proof_class": "physical_teleoperation_source_unqualified",
        "skill": "full_episode",
        "outcome_label": "success",
        "source_square": "c2",
        "destination_square": "c1",
        "sample_count": len(rows),
        "overhead_video": {
            "observed_video": {
                "streams": [{"nb_frames": "300"}],
                "format": {"duration": "10.0"},
            }
        },
        "wrist_video": {
            "browser_observed_video": {
                "streams": [{"nb_frames": "50"}],
                "format": {"duration": "10.0"},
            }
        },
    }
    _write_json(source / "recording_receipt.json", receipt)
    contract = {
        "schema_version": (
            "sim2claw.overnight_empty_gripper_diagnostic_contract.v1"
        ),
        "contract_id": "fixture-contract",
        "status": "frozen_before_derived_materialization",
        "source": {
            "recording_directory": "source",
            "recording_id": "fixture-recording",
            "expected_mode": "physical_follower",
            "expected_proof_class": "physical_teleoperation_source_unqualified",
            "expected_raw_label": {
                "skill": "full_episode",
                "outcome_label": "success",
                "source_square": "c2",
                "destination_square": "c1",
            },
            "artifacts_sha256": {
                "recording_receipt.json": _sha(source / "recording_receipt.json"),
                "samples.jsonl": _sha(samples),
            },
        },
        "segmentation": {
            "signal": "follower_requested_degrees[5]",
            "low_threshold_degrees": 10.0,
            "high_threshold_degrees": 90.0,
            "analysis_margin_seconds": 0.25,
            "lag_search_min_seconds": 0.0,
            "lag_search_max_seconds": 0.3,
            "expected_observed_excursions": 3,
            "owner_intended_excursions": 2,
            "owner_intended_sensitivity_cycle_ids": [2, 3],
            "sensitivity_view_is_retrospective_and_non_promoting": True,
        },
        "measurement_gates": {
            "require_zero_assistance": True,
            "require_zero_interventions": True,
            "require_nonstale_current_rows": True,
            "maximum_stable_cycle_body_peak_to_peak_degrees": 6.0,
            "maximum_stable_cycle_gripper_lag_seconds": 0.25,
            "procedure_count_must_match_for_measurement_admission": True,
        },
        "simulator_binding": {
            "scene_source": "scene.py",
            "scene_source_sha256": _sha(root / "scene.py"),
            "replay_source": "replay.py",
            "replay_source_sha256": _sha(root / "replay.py"),
            "action_dtype": "float64",
            "action_field": "follower_command_degrees",
            "action_mutation_allowed": False,
            "preclip_allowed": False,
            "simulator_replays_maximum": 1,
            "candidate_variants": 0,
            "execute_only_if_every_action_is_within_declared_ctrlrange": True,
        },
        "unavailable_observables": ["contact_force", "metric_depth"],
        "authority": {
            "physical_motion": False,
            "physical_capture": False,
            "simulator_parameter_promotion": False,
            "training": False,
            "policy_promotion": False,
            "task_score_change": False,
            "provider_advice_is_evaluator_evidence": False,
        },
    }
    contract_path = root / "contract.json"
    _write_json(contract_path, contract)
    return contract_path


def _comparison_contract(root: Path, diagnostic_root: Path) -> Path:
    calibration = {
        "shoulder_pan": {"range_min": 755, "range_max": 3491},
        "shoulder_lift": {"range_min": 803, "range_max": 3229},
        "elbow_flex": {"range_min": 753, "range_max": 3076},
        "wrist_flex": {"range_min": 839, "range_max": 3284},
        "wrist_roll": {"range_min": 0, "range_max": 4095},
        "gripper": {"range_min": 1482, "range_max": 2324},
    }
    calibration_path = root / "follower-calibration.json"
    _write_json(calibration_path, calibration)
    diagnostic = json.loads((diagnostic_root / "diagnostic.json").read_text())
    body_ranges = {}
    for joint in JOINTS[:-1]:
        minimum, maximum = (
            calibration[joint]["range_min"],
            calibration[joint]["range_max"],
        )
        half = (maximum - minimum) * 180.0 / 4095.0
        body_ranges[joint] = [-half, half]
    contract = {
        "schema_version": (
            "sim2claw.overnight_joint_limit_comparison_contract.v1"
        ),
        "comparison_id": "fixture-joint-limit-comparison",
        "status": "frozen_before_simulator_execution",
        "source": {
            "recording_directory": "source",
            "recording_id": "fixture-recording",
            "samples_sha256": _sha(root / "source/samples.jsonl"),
            "action_field": "follower_command_degrees",
            "action_dtype": "float64",
            "action_shape": [180, 6],
            "action_sha256": diagnostic["simulator_binding"][
                "exact_input_action_sha256"
            ],
            "derived_diagnostic": "diagnostic/diagnostic.json",
            "derived_diagnostic_sha256": _sha(
                diagnostic_root / "diagnostic.json"
            ),
            "derived_receipt": "diagnostic/receipt.json",
            "derived_receipt_sha256": _sha(diagnostic_root / "receipt.json"),
        },
        "calibration_identity": {
            "kind": "lerobot_so101_follower_endpoint_calibration",
            "standard_path": str(calibration_path),
            "sha256": _sha(calibration_path),
            "motor_resolution_counts": 4095,
            "body_normalization": "degrees_about_calibrated_range_midpoint",
            "gripper_normalization": "range_0_100",
            "frozen_range_counts": {
                joint: [
                    calibration[joint]["range_min"],
                    calibration[joint]["range_max"],
                ]
                for joint in JOINTS
            },
            "derived_body_ranges_degrees": body_ranges,
        },
        "simulator": {
            "scene_source": "scene.py",
            "scene_source_sha256": _sha(root / "scene.py"),
            "piece_layout": "sparse_two_sided_pawns",
            "variants": [
                {
                    "id": "current_declared_ranges",
                    "kind": "baseline",
                    "range_mutation": False,
                },
                {
                    "id": "follower_calibrated_ranges_v1",
                    "kind": "candidate",
                    "range_mutation": True,
                    "only_mutated_fields": [
                        "body_joint_range",
                        "body_actuator_ctrlrange",
                    ],
                },
            ],
            "simulator_replays_maximum": 2,
            "candidate_families": 1,
            "adaptive_retries": 0,
            "action_tensor_must_be_byte_identical": True,
            "external_preclip_allowed": False,
            "engine_internal_control_limits_are_the_factor_under_test": True,
        },
        "evaluation": {
            "owner": "independent_cpu_fp32_joint_response_evaluator",
            "aggregate_body_joint_rmse_improvement_minimum_fraction": 0.02,
            "maximum_per_joint_rmse_regression_degrees": 0.25,
            "gripper_rmse_nonregression_required": True,
            "cycle_ids_reported_separately": [1, 2, 3],
            "strict_task_consequence_available": False,
            "promotion_requires_strict_task_consequence": True,
        },
        "authority": {
            "physical_motion": False,
            "physical_capture": False,
            "training": False,
            "simulator_parameter_promotion": False,
            "policy_promotion": False,
            "task_score_change": False,
            "provider_advice_is_evaluator_evidence": False,
        },
    }
    path = root / "comparison-contract.json"
    _write_json(path, contract)
    return path


def test_materialization_is_deterministic_and_preserves_all_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _fixture(tmp_path)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", tmp_path)
    first = derive_empty_gripper_diagnostic(
        tmp_path / "out-1", contract_path=contract
    )
    second = derive_empty_gripper_diagnostic(
        tmp_path / "out-2", contract_path=contract
    )

    assert (tmp_path / "out-1/diagnostic.json").read_bytes() == (
        tmp_path / "out-2/diagnostic.json"
    ).read_bytes()
    assert (tmp_path / "out-1/receipt.json").read_bytes() == (
        tmp_path / "out-2/receipt.json"
    ).read_bytes()
    payload = json.loads((tmp_path / "out-1/diagnostic.json").read_text())
    assert payload["schema_version"] == DIAGNOSTIC_SCHEMA
    assert payload["segmentation"]["observed_excursion_count"] == 3
    assert payload["segmentation"]["owner_intended_excursion_count"] == 2
    assert [row["cycle_id"] for row in payload["segmentation"]["cycles"]] == [
        1,
        2,
        3,
    ]
    assert payload["measurement_admission"]["admitted"] is False
    assert payload["raw_label_is_not_measurement_admission"] is True
    assert payload["owner_intended_five_cycle_sensitivity"][
        "retrospective_non_promoting_view"
    ]
    assert payload["simulator_binding"]["preclip_applied"] is False
    assert payload["simulator_binding"]["action_mutated"] is False
    assert payload["simulator_binding"]["simulator_replays_used"] == 0
    assert first["receipt_sha256"] == second["receipt_sha256"]


def test_out_of_range_action_abstains_without_clipping_or_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _fixture(tmp_path, out_of_range=True)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", tmp_path)
    derive_empty_gripper_diagnostic(tmp_path / "out", contract_path=contract)
    payload = json.loads((tmp_path / "out/diagnostic.json").read_text())

    binding = payload["simulator_binding"]
    assert binding["rows_outside_declared_ctrlrange"] == 180
    assert binding["violations_by_joint"]["shoulder_lift"] == 180
    assert binding["verdict"] == (
        "abstain_exact_action_outside_declared_simulator_ctrlrange"
    )
    assert binding["simulator_replays_used"] == 0
    assert binding["preclip_applied"] is False


def test_source_tamper_and_assistance_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _fixture(tmp_path)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", tmp_path)
    with (tmp_path / "source/samples.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(EmptyGripperDiagnosticError, match="hash changed"):
        derive_empty_gripper_diagnostic(tmp_path / "tampered", contract_path=contract)

    assisted_root = tmp_path / "assisted"
    assisted_contract = _fixture(assisted_root, assistance_index=10)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", assisted_root)
    with pytest.raises(EmptyGripperDiagnosticError, match="Assisted action"):
        derive_empty_gripper_diagnostic(
            assisted_root / "out", contract_path=assisted_contract
        )


def test_contract_rejects_authority_widening(tmp_path: Path) -> None:
    contract_path = _fixture(tmp_path)
    contract = json.loads(contract_path.read_text())
    contract["authority"]["task_score_change"] = True
    _write_json(contract_path, contract)
    with pytest.raises(EmptyGripperDiagnosticError, match="widened authority"):
        load_empty_gripper_contract(contract_path)


def test_cli_exposes_read_only_diagnostic_command() -> None:
    parsed = build_parser().parse_args(
        [
            "empty-gripper-diagnose",
            "--config",
            "contract.json",
            "--output",
            "derived",
        ]
    )
    assert parsed.command == "empty-gripper-diagnose"
    assert parsed.config == Path("contract.json")
    assert parsed.output == Path("derived")


def test_joint_limit_comparison_keeps_actions_identical_and_never_promotes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_contract = _fixture(tmp_path, out_of_range=True)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", tmp_path)
    derive_empty_gripper_diagnostic(
        tmp_path / "diagnostic", contract_path=diagnostic_contract
    )
    import sim2claw.joint_limit_comparison as comparison_module

    monkeypatch.setattr(comparison_module, "REPO_ROOT", tmp_path)
    comparison_contract = _comparison_contract(
        tmp_path, tmp_path / "diagnostic"
    )
    receipt = run_joint_limit_comparison(
        tmp_path / "comparison", contract_path=comparison_contract
    )
    raw = json.loads((tmp_path / "comparison/raw_comparison.json").read_text())
    evaluation = json.loads((tmp_path / "comparison/evaluation.json").read_text())

    assert receipt["simulator_replays_used"] == 2
    assert raw["simulator_replays_used"] == 2
    assert len(raw["variants"]) == 2
    assert raw["variants"][0]["input_action_sha256"] == raw["variants"][1][
        "input_action_sha256"
    ]
    assert all(
        row["external_preclip_applied"] is False for row in raw["variants"]
    )
    assert evaluation["action_tensor_byte_identical"] is True
    assert evaluation["simulator_parameter_promoted"] is False
    assert evaluation["task_score_changed"] is False
    assert evaluation["gates"]["strict_task_consequence"] is False


def test_joint_limit_comparison_rejects_calibration_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_contract = _fixture(tmp_path, out_of_range=True)
    monkeypatch.setattr(diagnostic_module, "REPO_ROOT", tmp_path)
    derive_empty_gripper_diagnostic(
        tmp_path / "diagnostic", contract_path=diagnostic_contract
    )
    import sim2claw.joint_limit_comparison as comparison_module

    monkeypatch.setattr(comparison_module, "REPO_ROOT", tmp_path)
    comparison_contract = _comparison_contract(
        tmp_path, tmp_path / "diagnostic"
    )
    (tmp_path / "follower-calibration.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(JointLimitComparisonError, match="identity changed"):
        run_joint_limit_comparison(
            tmp_path / "comparison", contract_path=comparison_contract
        )


def test_cli_exposes_joint_limit_comparison() -> None:
    parsed = build_parser().parse_args(
        [
            "joint-limit-compare",
            "--config",
            "comparison.json",
            "--output",
            "comparison-output",
        ]
    )
    assert parsed.command == "joint-limit-compare"
