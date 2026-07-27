#!/usr/bin/env python3
"""Replay the exact geometric micro-lattice traces through frozen actuator variants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import _replay
from sim2claw.pawn_bg_timing_ablation import (
    _episode_metrics,
    _mapped_episode,
    _pool,
    _strip_arrays,
)
from sim2claw.wrist_view_reposition import (
    _decode_capture_hold,
    _decode_stage,
)


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_micro_actuator_response_v1.json"
)
SCHEMA = "sim2claw.geometric_micro_actuator_response.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_micro_actuator_response_receipt.v1"


class GeometricActuatorEvaluationError(RuntimeError):
    """A source, action, or authority boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricActuatorEvaluationError(message)


def _path(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source path escaped the repository",
    )
    path = REPO_ROOT / relative
    _require(
        path.is_file() and sha256_file(path) == binding.get("sha256"),
        f"hash-bound source changed: {relative}",
    )
    return path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricActuatorEvaluationError(
            f"cannot read JSON {path}: {error}"
        ) from error
    _require(isinstance(value, dict), f"JSON source is not an object: {path}")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _load_json(path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == "retrospective_external_check_of_previously_frozen_variants",
        "contract proof status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "evaluation authority widened",
    )
    _require(
        all((contract.get("action_invariance") or {}).values()),
        "action invariance is not fail closed",
    )
    expected = {
        "rigid_zero_deadband": {
            "shoulder_lift_deadband_degrees": 0.0,
            "elbow_flex_deadband_degrees": 0.0,
            "elbow_load_bias_coefficient": 0.0,
        },
        "prior_deadband_baseline": {
            "shoulder_lift_deadband_degrees": 2.0,
            "elbow_flex_deadband_degrees": 2.0,
            "elbow_load_bias_coefficient": 0.0,
        },
        "frozen_selected_load_response": {
            "shoulder_lift_deadband_degrees": 1.5,
            "elbow_flex_deadband_degrees": 2.0,
            "elbow_load_bias_coefficient": -1.5,
        },
    }
    _require(contract.get("variants") == expected, "frozen variants changed")
    stage_count = len((contract.get("sources") or {}).get("stages") or [])
    _require(1 <= stage_count <= 4, "stage inventory must contain 1 to 4 stages")
    return contract


def _stage_payload(
    source: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_index = int(source["stage_index"])
    stage = packet["stages"][stage_index - 1]
    motion, _, _ = _decode_stage(stage)
    hold, _, _ = _decode_capture_hold(stage)
    exact = np.concatenate((motion, hold), axis=0)

    samples_binding = {
        "path": source["samples_path"],
        "sha256": source["samples_sha256"],
    }
    receipt_binding = {
        "path": source["execution_receipt_path"],
        "sha256": source["execution_receipt_sha256"],
    }
    samples_path = _path(samples_binding)
    execution = _load_json(_path(receipt_binding))
    _require(
        execution.get("status") == "completed_wrist_view_reposition_stage"
        and execution.get("stage_index") == stage_index
        and execution.get("action_sha256") == stage["action_sha256"]
        and execution.get("capture_hold_action_sha256")
        == stage["capture_hold_action_sha256"]
        and execution.get("physical_follower_torque_enabled") is False
        and execution.get("completed_samples") == exact.shape[0],
        f"stage {stage_index} execution receipt changed",
    )
    try:
        rows = [
            json.loads(line)
            for line in samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricActuatorEvaluationError(
            f"cannot read stage {stage_index} samples: {error}"
        ) from error
    _require(len(rows) == exact.shape[0], f"stage {stage_index} sample count changed")
    mapped_samples = []
    for row_index, (row, action) in enumerate(zip(rows, exact, strict=True)):
        requested = np.asarray(row["requested_physical_units"], dtype="<f8")
        _require(
            requested.shape == (6,)
            and requested.tobytes() == action.astype("<f8").tobytes()
            and row.get("sample_index") == row_index
            and row.get("rate_limited") is False
            and row.get("safety_clamped") is False
            and row.get("stalled") is False
            and not bool(row.get("assistance"))
            and not bool(row.get("intervention")),
            f"stage {stage_index} row {row_index} is not exact and unassisted",
        )
        copy = dict(row)
        copy["timestamp_monotonic_seconds"] = float(row["timestamp_seconds"])
        mapped_samples.append(copy)
    episode = {
        "recording_id": f"geometric-micro-stage-{stage_index}",
        "sample_hz": 40,
    }
    return episode, {
        "payload": (episode, "none", "none", mapped_samples),
        "source": {
            "samples_path": str(samples_path.relative_to(REPO_ROOT)),
            "samples_sha256": sha256_file(samples_path),
            "execution_receipt_path": str(
                _path(receipt_binding).relative_to(REPO_ROOT)
            ),
            "execution_receipt_sha256": sha256_file(_path(receipt_binding)),
            "physical_motion_action_sha256": stage["action_sha256"],
            "physical_hold_action_sha256": stage["capture_hold_action_sha256"],
        },
    }


def _relative_improvement(candidate: float, baseline: float) -> float:
    _require(baseline > 0.0, "baseline metric must be positive")
    return float((baseline - candidate) / baseline)


def _replace_nonfinite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _replace_nonfinite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_nonfinite(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def evaluate(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    sources = contract["sources"]
    packet = _load_json(_path(sources["packet"]))
    selection_path = _path(sources["selection_receipt"])
    selection = _load_json(selection_path)
    digest_payload = dict(selection)
    observed_digest = digest_payload.pop("receipt_digest", None)
    _require(
        observed_digest == sources["selection_receipt"]["receipt_digest"]
        == canonical_digest(digest_payload),
        "selection receipt digest changed",
    )
    mechanism_path = _path(sources["mechanism_contract"])
    mechanism = _load_json(mechanism_path)
    _require(
        selection.get("selected_candidate")
        == contract["variants"]["frozen_selected_load_response"],
        "selected candidate differs from the frozen external variant",
    )
    workcell = _workcell_candidate(selection)

    per_stage: list[dict[str, Any]] = []
    metrics_by_variant: dict[str, list[dict[str, Any]]] = {
        name: [] for name in contract["variants"]
    }
    mapped_action_hashes: list[str] = []
    for source in sources["stages"]:
        episode, loaded = _stage_payload(source, packet)
        mapped = _mapped_episode(loaded["payload"], workcell)
        mapped_action_hashes.append(mapped["action_receipt"]["sha256"])
        variants: dict[str, Any] = {}
        for name, parameters in contract["variants"].items():
            states, schedule, torque = _replay(
                mapped, workcell, mechanism, dict(parameters)
            )
            metrics = _episode_metrics(mapped, states, workcell, mechanism)
            metrics_by_variant[name].append(metrics)
            variants[name] = {
                "parameters": parameters,
                "schedule_sha256": schedule["sha256"],
                "load_response": torque,
                "metrics": _strip_arrays(metrics),
            }
        per_stage.append(
            {
                "stage_index": int(source["stage_index"]),
                "recording_id": episode["recording_id"],
                "source": loaded["source"],
                "mapped_action_receipt": mapped["action_receipt"],
                "variants": variants,
            }
        )

    pooled = {
        name: _pool(metrics_by_variant[name]) for name in contract["variants"]
    }
    rigid = pooled["rigid_zero_deadband"]
    deadband = pooled["prior_deadband_baseline"]
    selected = pooled["frozen_selected_load_response"]
    comparisons = {
        "prior_deadband_vs_rigid": {
            "joint_rms_relative_improvement": _relative_improvement(
                deadband["overall_joint_rms_degrees"],
                rigid["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement": _relative_improvement(
                deadband["ee_rms_m"], rigid["ee_rms_m"]
            ),
        },
        "selected_vs_rigid": {
            "joint_rms_relative_improvement": _relative_improvement(
                selected["overall_joint_rms_degrees"],
                rigid["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement": _relative_improvement(
                selected["ee_rms_m"], rigid["ee_rms_m"]
            ),
        },
        "selected_vs_prior_deadband": {
            "joint_rms_relative_improvement": _relative_improvement(
                selected["overall_joint_rms_degrees"],
                deadband["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement": _relative_improvement(
                selected["ee_rms_m"], deadband["ee_rms_m"]
            ),
        },
    }
    gates = {
        "exact_action_invariance": len(mapped_action_hashes) == len(per_stage),
        "prior_deadband_joint_rms_improves_over_rigid": (
            comparisons["prior_deadband_vs_rigid"][
                "joint_rms_relative_improvement"
            ]
            > 0.0
        ),
        "prior_deadband_ee_rms_improves_over_rigid": (
            comparisons["prior_deadband_vs_rigid"][
                "ee_rms_relative_improvement"
            ]
            > 0.0
        ),
        "selected_joint_rms_improves_over_prior_deadband": (
            comparisons["selected_vs_prior_deadband"][
                "joint_rms_relative_improvement"
            ]
            > 0.0
        ),
        "selected_ee_rms_improves_over_prior_deadband": (
            comparisons["selected_vs_prior_deadband"][
                "ee_rms_relative_improvement"
            ]
            > 0.0
        ),
    }
    retained = (
        gates["exact_action_invariance"]
        and gates["selected_joint_rms_improves_over_prior_deadband"]
        and gates["selected_ee_rms_improves_over_prior_deadband"]
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path.resolve()),
        "selection_receipt_path": str(selection_path),
        "selection_receipt_sha256": sha256_file(selection_path),
        "mechanism_contract_path": str(mechanism_path),
        "mechanism_contract_sha256": sha256_file(mechanism_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "stage_count": len(per_stage),
        "per_stage": per_stage,
        "pooled": pooled,
        "comparisons": comparisons,
        "gates": gates,
        "frozen_load_response_retained": retained,
        "verdict": (
            "frozen_load_response_retained_for_future_validation"
            if retained
            else "frozen_load_response_rejected_plain_deadband_direction_retained"
        ),
        "next_mechanism": (
            None
            if retained
            else "direction_and_load_conditioned_joint_play_with_wrist_flex"
        ),
        "parameter_fitting_performed": False,
        "action_correction_performed": False,
        "parameters_promoted": False,
        "pawn_contact_admitted": False,
        "authority": contract["authority"],
    }
    receipt = _replace_nonfinite(receipt)
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_path.resolve(), receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = evaluate(contract_path=args.contract, output_path=args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
