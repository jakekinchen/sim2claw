#!/usr/bin/env python3
"""Audit whether legacy physical replay values fit the current MuJoCo ranges.

This is a read-only input-capability audit. It never replays, clips, fits, or
changes an episode and grants no calibration or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from sim2claw.physical_sim_replay import physical_values_to_sim
from sim2claw.scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS, build_scene_spec


AUDIT_SCHEMA = "sim2claw.physical_replay_joint_limit_audit.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compiled_control_contract() -> tuple[dict[str, Any], str, np.ndarray]:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    actuator_ids = [
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_ACTUATOR,
            f"left_{joint}",
        )
        for joint in ROBOT_JOINTS
    ]
    if any(identifier < 0 for identifier in actuator_ids):
        raise RuntimeError("current scene is missing a left-arm actuator")
    bounds = model.actuator_ctrlrange[actuator_ids].astype(np.float64)
    payload = {
        "joint_order": list(ROBOT_JOINTS),
        "actuator_names": [f"left_{joint}" for joint in ROBOT_JOINTS],
        "actuator_ctrlrange": bounds.astype(float).tolist(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return payload, hashlib.sha256(encoded).hexdigest(), bounds


def _empty_metric() -> dict[str, int | float]:
    return {
        "row_count": 0,
        "violating_row_count": 0,
        "joint_value_count": 0,
        "violating_joint_value_count": 0,
        "maximum_exceedance_sim_units": 0.0,
    }


def _accumulate(
    metric: dict[str, int | float],
    values: np.ndarray,
    bounds: np.ndarray,
) -> int:
    exceedance = np.maximum(
        np.maximum(bounds[:, 0] - values, 0.0),
        np.maximum(values - bounds[:, 1], 0.0),
    )
    violating = exceedance > 0.0
    metric["row_count"] = int(metric["row_count"]) + 1
    metric["joint_value_count"] = int(metric["joint_value_count"]) + len(values)
    metric["violating_row_count"] = int(metric["violating_row_count"]) + int(
        violating.any()
    )
    metric["violating_joint_value_count"] = int(
        metric["violating_joint_value_count"]
    ) + int(violating.sum())
    metric["maximum_exceedance_sim_units"] = max(
        float(metric["maximum_exceedance_sim_units"]),
        float(exceedance.max()),
    )
    return int(violating.sum())


def audit_catalog(repo_root: Path, catalog_path: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    catalog_path = catalog_path.resolve()
    try:
        catalog_relative = catalog_path.relative_to(repo_root).as_posix()
    except ValueError as error:
        raise ValueError("catalog must resolve below repo root") from error
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    recordings = catalog.get("episodes")
    if not isinstance(recordings, list) or not recordings:
        raise ValueError("catalog needs non-empty recordings")

    control, control_sha256, bounds = compiled_control_contract()
    actual = _empty_metric()
    commands = _empty_metric()
    initial_violating_episodes = 0
    initial_violating_counts: list[int] = []
    verified_assets = 0

    for recording in recordings:
        assets = recording["assets"]
        expected_assets = (
            ("receipt", "receipt_sha256"),
            ("samples", "samples_sha256"),
            ("overhead_video", "overhead_video_sha256"),
        )
        for asset_key, hash_key in expected_assets:
            asset_path = (repo_root / assets[asset_key]).resolve()
            try:
                asset_path.relative_to(repo_root)
            except ValueError as error:
                raise ValueError("catalog asset escapes repo root") from error
            if sha256_file(asset_path) != recording[hash_key]:
                raise ValueError(
                    f"catalog asset hash mismatch: {recording['recording_id']} {asset_key}"
                )
            verified_assets += 1

        samples_path = (repo_root / assets["samples"]).resolve()
        samples = [
            json.loads(line)
            for line in samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not samples:
            raise ValueError(f"empty samples: {recording['recording_id']}")
        initial = physical_values_to_sim(
            samples[0]["follower_actual_position_degrees"], bounds[-1]
        )
        initial_count = int(((initial < bounds[:, 0]) | (initial > bounds[:, 1])).sum())
        initial_violating_counts.append(initial_count)
        initial_violating_episodes += int(initial_count > 0)
        for sample in samples:
            actual_values = physical_values_to_sim(
                sample["follower_actual_position_degrees"], bounds[-1]
            )
            command_values = physical_values_to_sim(
                sample["follower_command_degrees"], bounds[-1]
            )
            _accumulate(actual, actual_values, bounds)
            _accumulate(commands, command_values, bounds)

    for metric in (actual, commands):
        metric["violating_row_fraction"] = (
            int(metric["violating_row_count"]) / int(metric["row_count"])
        )

    return {
        "schema_version": AUDIT_SCHEMA,
        "proof_class": "physical_read_only_input_capability",
        "claim": "legacy_canonical_replay_is_not_exact_and_joint_timing_fit_is_not_ready",
        "inputs": {
            "catalog_path": catalog_relative,
            "catalog_sha256": sha256_file(catalog_path),
            "catalog_episode_count": len(recordings),
            "catalog_bound_assets_verified": verified_assets,
            "sample_rows": int(actual["row_count"]),
            "physical_to_sim_transform": (
                "legacy_physical_values_to_sim_degrees_to_radians_for_first_five_"
                "joints_and_0_to_100_linear_gripper_mapping"
            ),
            "mujoco_version": mujoco.__version__,
        },
        "compiled_control_contract": {
            **control,
            "sha256": control_sha256,
        },
        "violation_predicate": {
            "expression": "value < lower_bound or value > upper_bound",
            "tolerance_sim_units": 0.0,
        },
        "results": {
            "episodes_audited": len(recordings),
            "episodes_with_out_of_range_initial_state": initial_violating_episodes,
            "out_of_range_initial_joint_values_per_episode": initial_violating_counts,
            "measured_trajectory": actual,
            "recorded_commands": commands,
        },
        "interpretation": {
            "legacy_replay_clips_initial_state": True,
            "legacy_replay_clips_commands": True,
            "legacy_trace_preserves_requested_command_before_clipping": False,
            "exact_recorded_action_replay_supported": False,
            "reviewed_hash_bound_joint_transform_available": False,
            "joint_timing_fit_ready": False,
            "full_calibration_ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("configs/data/physical_pawn_move_catalog_20260719.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    catalog = args.catalog
    if not catalog.is_absolute():
        catalog = repo_root / catalog
    result = audit_catalog(repo_root, catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
