from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = REPO_ROOT / "scripts" / "analyze_groot_n17_temporal_overlap.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GrootTemporalOverlapAnalysisTest(unittest.TestCase):
    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        parent_experiment_sha = "parent-experiment"
        parent_summary = {
            "experiment_sha256": parent_experiment_sha,
            "held_out_may_open": False,
        }
        parent_path = root / "parent-summary.json"
        parent_path.write_text(json.dumps(parent_summary), encoding="utf-8")
        arms = [
            {
                "id": "h8-mean",
                "execution_horizon": 8,
                "temporal_action_aggregation": "mean",
                "temporal_decay": 0.5,
                "maximum_overlapping_predictions": 2,
            },
            {
                "id": "h4-median",
                "execution_horizon": 4,
                "temporal_action_aggregation": "median",
                "temporal_decay": 0.5,
                "maximum_overlapping_predictions": 4,
            },
        ]
        selection_order = [
            "full_task_consequence_pass_count",
            "board_safety_pass_count",
            "final_xy_pass_count",
            "upright_pass_count",
            "lift_pass_count",
        ]
        experiment = {
            "parent_waypoint_summary_sha256": sha256_file(parent_path),
            "parent_waypoint_experiment_sha256": parent_experiment_sha,
            "frozen_identities": {
                "nominal_checkpoint_id": "checkpoint-4000",
                "nominal_checkpoint_aggregate_manifest_sha256": "manifest",
                "nvidia_source_commit": "source",
                "base_task_contract_canonical_sha256": "task",
            },
            "fixed_model_inference": {
                "proposal_count": 5,
                "action_aggregation": "median",
                "noise_scale": 0.5,
                "num_inference_timesteps": 4,
                "model_action_horizon": 16,
            },
            "action_execution_adapter": {"method": "linear_same_phase"},
            "renderer": {
                "mujoco_gl": "osmesa",
                "pyopengl_platform": "osmesa",
                "development_cadence": "policy_queries",
                "sealed_promotion_cadence": "all_samples",
            },
            "development": {
                "episode_indices": [0],
                "inference_seeds": [0, 1],
                "candidate_arms": arms,
                "maximum_candidate_arms": 2,
                "selection_order": selection_order,
            },
        }
        experiment_path = root / "experiment.json"
        experiment_path.write_text(json.dumps(experiment), encoding="utf-8")
        rollout_root = root / "rollouts"
        for arm in arms:
            for seed in (0, 1):
                receipt_root = (
                    rollout_root
                    / arm["id"]
                    / f"training-episode-0-seed-{seed}"
                )
                receipt_root.mkdir(parents=True)
                success = arm["id"] == "h8-mean"
                gates = {
                    name: {"passed": success}
                    for name in (
                        "maximum_other_piece_displacement",
                        "final_xy_error",
                        "final_upright_cosine",
                        "minimum_piece_rise",
                    )
                }
                gates["assistance_frames"] = {"passed": True}
                gates["model_owned_actions"] = {"passed": True}
                receipt = {
                    "split": "training",
                    "episode_index": 0,
                    "inference_seed": seed,
                    "checkpoint_id": "checkpoint-4000",
                    "checkpoint_manifest_sha256": "manifest",
                    "groot_source_commit": "source",
                    "task_contract_sha256": "task",
                    "action_consensus": {
                        key: experiment["fixed_model_inference"][key]
                        for key in (
                            "proposal_count",
                            "action_aggregation",
                            "noise_scale",
                            "num_inference_timesteps",
                        )
                    },
                    "execution_horizon": arm["execution_horizon"],
                    "temporal_action_aggregation": {
                        "method": arm["temporal_action_aggregation"],
                        "exponential_decay": arm["temporal_decay"],
                        "maximum_overlapping_predictions": arm[
                            "maximum_overlapping_predictions"
                        ],
                        "model_chunks_only": True,
                        "causal": True,
                        "assistance_frames": 0,
                    },
                    "action_execution_adapter": {
                        "method": "linear_same_phase",
                        "model_waypoints_only": True,
                    },
                    "render_cadence": {
                        "method": "policy_queries",
                        "policy_observation_frames_omitted": False,
                    },
                    "render_backend": {
                        "mujoco_gl": "osmesa",
                        "pyopengl_platform": "osmesa",
                    },
                    "all_actions_model_owned": True,
                    "assistance_frames": 0,
                    "verdict": {"success": success, "gates": gates},
                }
                (receipt_root / "receipt.json").write_text(
                    json.dumps(receipt), encoding="utf-8"
                )
        return experiment_path, parent_path, rollout_root

    def _run(
        self,
        experiment: Path,
        parent: Path,
        rollouts: Path,
        output: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ANALYZER),
                "--experiment",
                str(experiment),
                "--parent-summary",
                str(parent),
                "--rollout-root",
                str(rollouts),
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_freezes_only_arm_with_two_full_training_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, parent, rollouts = self._write_fixture(root)
            output = root / "summary.json"
            result = self._run(experiment, parent, rollouts, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(summary["held_out_may_open"])
            self.assertFalse(summary["promotion_authority"])
            self.assertEqual(summary["winning_configuration"]["id"], "h8-mean")
            self.assertEqual(len(summary["winning_configuration_sha256"]), 64)

    def test_rejects_noncausal_temporal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, parent, rollouts = self._write_fixture(root)
            path = (
                rollouts / "h8-mean" / "training-episode-0-seed-0" / "receipt.json"
            )
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["temporal_action_aggregation"]["causal"] = False
            path.write_text(json.dumps(receipt), encoding="utf-8")
            result = self._run(
                experiment, parent, rollouts, root / "summary.json"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("wrong temporal causal", result.stderr)


if __name__ == "__main__":
    unittest.main()
