from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from tools.evaluate_current_pi_cad_keyed_joint_mapping import (
    CadMappingEvaluationError,
    TAG_BODY,
    fixed_base_metric_evidence_bound,
    hold_statistics,
    load_contract,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/current_pi_cad_keyed_joint_mapping_v1.json"
)


def test_frozen_contract_has_correct_split_and_tag3_mapping() -> None:
    contract = load_contract(CONTRACT)

    assert contract["split"]["fit_poses"] == ["J", "S", "K", "L"]
    assert contract["split"]["fresh_validation_pose"] == "M"
    assert contract["split"]["pose_m_observation_accessed_at_freeze"] is False
    assert contract["fixed_hypotheses"]["tag_body_map"]["3"] == (
        "left_shoulder"
    )
    assert TAG_BODY[3] == "left_shoulder"
    assert contract["fit_method"]["identifiability_fail_closed"] is True
    assert contract["authority"]["tag_only_promotion"] is False


def test_contract_rejects_tag3_as_fixed_base() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    changed = copy.deepcopy(contract)
    changed["fixed_hypotheses"]["tag_body_map"]["3"] = "left_base"

    with pytest.raises(
        CadMappingEvaluationError,
        match="tag body map changed",
    ):
        validate_contract(changed)


def test_contract_rejects_opened_m_at_freeze() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    changed = copy.deepcopy(contract)
    changed["split"]["pose_m_observation_accessed_at_freeze"] = True

    with pytest.raises(
        CadMappingEvaluationError,
        match="split changed",
    ):
        validate_contract(changed)


def test_frozen_contract_has_no_metric_fixed_base_anchor() -> None:
    contract = load_contract(CONTRACT)

    assert fixed_base_metric_evidence_bound(contract["sources"]) is False


def test_hold_gate_uses_actual_capture_hold_drift(
    tmp_path: Path,
) -> None:
    samples = tmp_path / "joint_samples.jsonl"
    rows = []
    for index in range(80):
        actual = np.zeros(6, dtype=np.float64)
        actual[1] = 0.2 * index / 79.0
        rows.append(
            {
                "phase": "capture_hold",
                "follower_actual_position_degrees": actual.tolist(),
            }
        )
    samples.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = hold_statistics(samples, 0.3)

    assert result["sample_count"] == 80
    assert result["maximum_absolute_drift_degrees"] == pytest.approx(0.2)
    assert result["gate_passed"] is True


def test_hold_gate_fails_above_frozen_drift(
    tmp_path: Path,
) -> None:
    samples = tmp_path / "joint_samples.jsonl"
    rows = []
    for index in range(80):
        actual = np.zeros(6, dtype=np.float64)
        actual[2] = 0.4 * index / 79.0
        rows.append(
            {
                "phase": "capture_hold",
                "follower_actual_position_degrees": actual.tolist(),
            }
        )
    samples.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = hold_statistics(samples, 0.3)

    assert result["gate_passed"] is False
