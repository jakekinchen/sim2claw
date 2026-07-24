from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.overnight_calibration_publication import (
    OvernightCalibrationPublicationError,
    verify_overnight_calibration_publication,
)


AUTHORITY = {
    "provider_advice_is_evaluator_evidence": False,
    "simulator_parameter_promotion": False,
    "task_score_change": False,
    "training": False,
    "physical_capture": False,
    "physical_motion": False,
}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _receipt(unsigned: dict[str, object]) -> dict[str, object]:
    return {**unsigned, "receipt_sha256": canonical_digest(unsigned)}


def _publication_fixture(root: Path) -> Path:
    recording_id = "fixture-recording"
    action_sha256 = "a" * 64
    diag_contract = root / "configs/evaluations/diag.json"
    comparison_contract = root / "configs/evaluations/comparison.json"
    _write_json(diag_contract, {"schema_version": "fixture-diag-contract"})
    _write_json(
        comparison_contract, {"schema_version": "fixture-comparison-contract"}
    )

    diag_root = root / "outputs/diag"
    comparison_root = root / "outputs/comparison"
    diagnostic = {
        "source_recording_id": recording_id,
        "proof_class": "derived_empty_gripper_cycle_diagnostic",
        "segmentation": {
            "procedure_count_matches": False,
            "observed_excursion_count": 6,
            "owner_intended_excursion_count": 5,
        },
        "authority": AUTHORITY,
    }
    diagnostic_path = diag_root / "diagnostic.json"
    _write_json(diagnostic_path, diagnostic)
    diagnostic_receipt = _receipt(
        {
            "source_recording_id": recording_id,
            "proof_class": "derived_empty_gripper_cycle_diagnostic",
            "diagnostic_sha256": sha256_file(diagnostic_path),
            "simulator_replays_used": 0,
            "simulator_parameter_promoted": False,
            "task_score_changed": False,
            "authority": AUTHORITY,
        }
    )
    diagnostic_receipt_path = diag_root / "receipt.json"
    _write_json(diagnostic_receipt_path, diagnostic_receipt)

    trace_bindings: dict[str, str] = {}
    variants = []
    for index, name in enumerate(
        ("current_declared_ranges.jsonl", "follower_calibrated_ranges_v1.jsonl")
    ):
        trace_path = comparison_root / name
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(f'{{"sample":{index}}}\n', encoding="utf-8")
        digest = sha256_file(trace_path)
        trace_bindings[name] = digest
        variants.append(
            {
                "variant_id": (
                    "current_declared_ranges"
                    if index == 0
                    else "follower_calibrated_ranges_v1"
                ),
                "input_action_sha256": action_sha256,
                "external_preclip_applied": False,
                "raw_trace_path": name,
                "raw_trace_sha256": digest,
            }
        )
    raw = {
        "source_recording_id": recording_id,
        "exact_action_sha256": action_sha256,
        "simulator_replays_used": 2,
        "adaptive_retries": 0,
        "variants": variants,
        "authority": AUTHORITY,
    }
    raw_path = comparison_root / "raw.json"
    _write_json(raw_path, raw)
    evaluation = {
        "action_tensor_byte_identical": True,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "verdict": "diagnostic_joint_range_tie_or_loss_no_promotion",
        "gates": {"strict_task_consequence": False},
    }
    evaluation_path = comparison_root / "evaluation.json"
    _write_json(evaluation_path, evaluation)
    comparison_receipt = _receipt(
        {
            "source_recording_id": recording_id,
            "proof_class": "action_frozen_simulator_joint_range_diagnostic",
            "exact_action_sha256": action_sha256,
            "raw_comparison_sha256": sha256_file(raw_path),
            "evaluation_sha256": sha256_file(evaluation_path),
            "simulator_replays_used": 2,
            "simulator_parameter_promoted": False,
            "task_score_changed": False,
            "authority": AUTHORITY,
        }
    )
    comparison_receipt_path = comparison_root / "receipt.json"
    _write_json(comparison_receipt_path, comparison_receipt)

    publication = {
        "schema_version": "sim2claw.overnight_calibration_publication.v1",
        "status": "frozen_after_single_authorized_comparison",
        "source_recording_id": recording_id,
        "proof_classes": [
            "derived_empty_gripper_cycle_diagnostic",
            "action_frozen_simulator_joint_range_diagnostic",
        ],
        "diagnostic": {
            "output_root": "outputs/diag",
            "contract_path": "configs/evaluations/diag.json",
            "contract_sha256": sha256_file(diag_contract),
            "diagnostic_path": "diagnostic.json",
            "diagnostic_sha256": sha256_file(diagnostic_path),
            "receipt_path": "receipt.json",
            "receipt_sha256": sha256_file(diagnostic_receipt_path),
            "embedded_receipt_sha256": diagnostic_receipt["receipt_sha256"],
            "simulator_replays_used": 0,
        },
        "comparison": {
            "output_root": "outputs/comparison",
            "contract_path": "configs/evaluations/comparison.json",
            "contract_sha256": sha256_file(comparison_contract),
            "raw_comparison_path": "raw.json",
            "raw_comparison_sha256": sha256_file(raw_path),
            "evaluation_path": "evaluation.json",
            "evaluation_sha256": sha256_file(evaluation_path),
            "receipt_path": "receipt.json",
            "receipt_sha256": sha256_file(comparison_receipt_path),
            "embedded_receipt_sha256": comparison_receipt["receipt_sha256"],
            "exact_action_sha256": action_sha256,
            "simulator_replays_used": 2,
            "adaptive_retries": 0,
            "traces": trace_bindings,
        },
        "required_claims": {
            "procedure_count_matches": False,
            "observed_excursion_count": 6,
            "owner_intended_excursion_count": 5,
            "action_tensor_byte_identical": True,
            "simulator_parameter_promoted": False,
            "task_score_changed": False,
            "strict_task_consequence_available": False,
            "verdict": "diagnostic_joint_range_tie_or_loss_no_promotion",
        },
        "authority": AUTHORITY,
    }
    publication_path = (
        root / "configs/evaluations/overnight_calibration_publication_v1.json"
    )
    _write_json(publication_path, publication)
    return publication_path


def test_publication_verifies_hashes_receipts_action_identity_and_authority(
    tmp_path: Path,
) -> None:
    _publication_fixture(tmp_path)
    bundle = verify_overnight_calibration_publication(repo_root=tmp_path)
    assert bundle["publication"]["source_recording_id"] == "fixture-recording"
    assert bundle["raw_comparison"]["simulator_replays_used"] == 2
    assert bundle["evaluation"]["simulator_parameter_promoted"] is False
    assert len(bundle["raw_comparison"]["variants"]) == 2


def test_publication_fails_closed_when_evaluation_bytes_change(tmp_path: Path) -> None:
    _publication_fixture(tmp_path)
    evaluation_path = tmp_path / "outputs/comparison/evaluation.json"
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation["simulator_parameter_promoted"] = True
    _write_json(evaluation_path, evaluation)
    with pytest.raises(
        OvernightCalibrationPublicationError,
        match="Comparison evaluation hash changed",
    ):
        verify_overnight_calibration_publication(repo_root=tmp_path)


def test_publication_fails_closed_on_action_substitution(tmp_path: Path) -> None:
    _publication_fixture(tmp_path)
    raw_path = tmp_path / "outputs/comparison/raw.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["variants"][1]["input_action_sha256"] = "b" * 64
    _write_json(raw_path, raw)
    comparison_receipt_path = tmp_path / "outputs/comparison/receipt.json"
    comparison_receipt = json.loads(
        comparison_receipt_path.read_text(encoding="utf-8")
    )
    comparison_receipt["raw_comparison_sha256"] = sha256_file(raw_path)
    comparison_receipt = _receipt(
        {
            key: value
            for key, value in comparison_receipt.items()
            if key != "receipt_sha256"
        }
    )
    _write_json(comparison_receipt_path, comparison_receipt)
    publication_path = (
        tmp_path
        / "configs/evaluations/overnight_calibration_publication_v1.json"
    )
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    publication["comparison"]["raw_comparison_sha256"] = sha256_file(raw_path)
    publication["comparison"]["receipt_sha256"] = sha256_file(
        comparison_receipt_path
    )
    publication["comparison"]["embedded_receipt_sha256"] = comparison_receipt[
        "receipt_sha256"
    ]
    _write_json(publication_path, publication)
    with pytest.raises(
        OvernightCalibrationPublicationError,
        match="Comparison action identity changed",
    ):
        verify_overnight_calibration_publication(repo_root=tmp_path)
