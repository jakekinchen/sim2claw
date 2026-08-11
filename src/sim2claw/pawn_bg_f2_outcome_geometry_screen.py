"""OR144 quarantined same-episode rigid-pad footprint screen."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_deformable_cap_compatibility import legacy_shoulder_spec_mutator
from .pawn_bg_f2_normal_compliant_cap import load_contract as load_or140_contract
from .pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = REPO_ROOT / "configs" / "evaluations" / "pawn_bg_f2_outcome_footprint_screen_v1.json"
OUTPUT_PATH = REPO_ROOT / "outputs" / "pawn_bg_f2_outcome_footprint_screen_v1" / "receipt.json"
SCHEMA = "sim2claw.pawn_bg_f2_outcome_footprint_screen.v1"


class GeometryScreenError(RuntimeError):
    """The frozen outcome-informed screen cannot continue after drift."""


def _validate_binding(binding: Mapping[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise GeometryScreenError(f"source binding drifted: {binding['path']}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise GeometryScreenError("unexpected OR143 schema")
    _validate_binding(contract["authorization"])
    for binding in contract["source_bindings"].values():
        _validate_binding(binding)
    for binding in contract["implementation_bindings"].values():
        _validate_binding(binding)
    if any(contract.get("authority", {}).values()):
        raise GeometryScreenError("OR143 authority widened")
    grid = contract["grid"]
    expected = len(grid["coverage_lengths_m"]) * len(grid["half_widths_m"])
    if (
        expected != 16
        or grid["fixed_thickness_multiplier"] != 0.91
        or grid["fixed_coverage_offset_m"] != -0.03
        or grid["moving_coverage_offset_m"] != 0.025
    ):
        raise GeometryScreenError("OR144 grid identity drifted")
    return contract


class ScreenObserver:
    def __init__(self) -> None:
        self.maximum_tilt_degrees = 0.0
        self.maximum_rise_m = 0.0
        self.minimum_upright_cosine = 1.0
        self.warning_count_sum = 0
        self.step_count = 0

    def start(self, *, model: mujoco.MjModel, data: mujoco.MjData, selected_body: int, **kwargs: Any) -> None:
        self.selected_body = int(selected_body)
        self.initial_height = float(data.xpos[self.selected_body, 2])

    def capture(self, *, model: mujoco.MjModel, data: mujoco.MjData, **kwargs: Any) -> None:
        quaternion = np.asarray(data.xquat[self.selected_body], dtype=float)
        upright_cosine = float(1.0 - 2.0 * (quaternion[1] ** 2 + quaternion[2] ** 2))
        upright_cosine = max(-1.0, min(1.0, upright_cosine))
        tilt = math.degrees(math.acos(upright_cosine))
        self.maximum_tilt_degrees = max(self.maximum_tilt_degrees, tilt)
        self.minimum_upright_cosine = min(self.minimum_upright_cosine, upright_cosine)
        self.maximum_rise_m = max(
            self.maximum_rise_m,
            float(data.xpos[self.selected_body, 2]) - self.initial_height,
        )
        self.warning_count_sum += sum(
            int(data.warning[index].number)
            for index in range(int(mujoco.mjtWarning.mjNWARNING))
        )
        self.step_count += 1

    def finish(self, *, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        return None


def _rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        not bool(row["screen_gates"]["continuous_upright"]),
        not bool(row["episode"]["piece_lifted"]),
        not bool(row["episode"]["transported_after_lift"]),
        not bool(row["episode"]["whole_base_inside_destination"]),
        bool(row["episode"]["wrong_piece_robot_contacts"]),
        float(row["episode"]["maximum_other_piece_displacement_m"]),
        float(row["episode"]["final_target_distance_m"]),
        -float(row["screen_metrics"]["maximum_rise_m_full_step"]),
        float(row["screen_metrics"]["maximum_tilt_degrees_full_step"]),
        float(row["coverage_length_m"]),
        float(row["half_width_m"]),
    )


def run_screen(*, contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = load_contract(contract_path)
    source_path = REPO_ROOT / contract["source_bindings"]["rigid_0p91_receipt"]["path"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    runtime_contract = load_or140_contract(
        REPO_ROOT / contract["source_bindings"]["runtime_contract"]["path"]
    )
    base_parameters = copy.deepcopy(source["parameters"])
    rows = []
    for coverage_length in contract["grid"]["coverage_lengths_m"]:
        for half_width in contract["grid"]["half_widths_m"]:
            parameters = copy.deepcopy(base_parameters)
            parameters["tip_fixed_thickness_multiplier"] = 0.91
            parameters["tip_coverage_offset_m"] = -0.03
            parameters["tip_moving_coverage_offset_m"] = 0.025
            parameters["tip_coverage_m"] = float(coverage_length)
            parameters["tip_half_width_m"] = float(half_width)
            observer = ScreenObserver()
            result = run_grasp_episode_probe(
                source_repository_root=REPO_ROOT,
                recording_id=str(contract["recording_id"]),
                parameters=parameters,
                retention_trace_enabled=False,
                spec_mutator=legacy_shoulder_spec_mutator(runtime_contract),
                integration_step_observer=observer,
            )
            episode = result["episode"]
            if (
                episode["action_array_sha256"] != contract["action_sha256"]
                or episode["clipped_action_rows"] != 0
                or episode["diagnostic_measured_joint_state_replay"]["enabled"]
            ):
                raise GeometryScreenError("exact action identity drifted")
            row = {
                "candidate_id": f"coverage_{coverage_length:.3f}_width_{half_width:.4f}",
                "coverage_length_m": float(coverage_length),
                "half_width_m": float(half_width),
                "fixed_coverage_offset_m": -0.03,
                "moving_coverage_offset_m": 0.025,
                "fixed_thickness_multiplier": 0.91,
                "parameter_digest": canonical_digest(parameters),
                "screen_metrics": {
                    "maximum_tilt_degrees_full_step": observer.maximum_tilt_degrees,
                    "maximum_rise_m_full_step": observer.maximum_rise_m,
                    "minimum_upright_cosine_full_step": observer.minimum_upright_cosine,
                    "warning_count_sum": observer.warning_count_sum,
                    "step_count": observer.step_count,
                },
                "screen_gates": {
                    "continuous_upright": observer.maximum_tilt_degrees <= 10.0,
                    "rise": observer.maximum_rise_m >= 0.04,
                    "warning_free": observer.warning_count_sum == 0,
                },
                "episode": {
                    key: episode[key]
                    for key in (
                        "action_array_sha256",
                        "clipped_action_rows",
                        "piece_lifted",
                        "transported_after_lift",
                        "whole_base_inside_destination",
                        "qualified_bilateral_contact_observed",
                        "maximum_bilateral_lift_retention_seconds",
                        "maximum_transport_progress_after_lift",
                        "maximum_other_piece_displacement_m",
                        "wrong_piece_robot_contacts",
                        "final_target_distance_m",
                        "final_piece_upright_cosine",
                    )
                },
            }
            rows.append(row)
    ranked = sorted(rows, key=_rank)
    receipt = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "candidate_count": len(rows),
        "rows": rows,
        "ranked_candidate_ids": [row["candidate_id"] for row in ranked],
        "selected_for_full_strict_evaluation": [
            {
                "candidate_id": row["candidate_id"],
                "coverage_length_m": row["coverage_length_m"],
                "half_width_m": row["half_width_m"],
                "parameter_digest": row["parameter_digest"],
            }
            for row in ranked[:3]
        ],
        "selection_is_outcome_informed": True,
        "screen_is_not_strict_task_evaluation": True,
        "strict_success_claimed": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    receipt = run_screen(contract_path=args.contract.resolve())
    atomic_write_json(args.output.resolve(), receipt)
    print(json.dumps({
        "candidate_count": receipt["candidate_count"],
        "selected": receipt["selected_for_full_strict_evaluation"],
        "receipt_digest": receipt["receipt_digest"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_contract", "run_screen"]
