from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = REPO_ROOT / "scripts" / "analyze_groot_n17_rate_limited_temporal.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GrootRateLimitedTemporalAnalysisTest(unittest.TestCase):
    def _write_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        parent_experiment = "parent-temporal"
        parent_arm = {
            "id": "h8-overlap-mean",
            "execution_horizon": 8,
            "temporal_action_aggregation": "mean",
            "temporal_decay": 0.5,
            "maximum_overlapping_predictions": 2,
        }
        parent = {
            "experiment_sha256": parent_experiment,
            "held_out_may_open": False,
            "ranked_arms": [parent_arm],
        }
        parent_path = root / "parent.json"
        parent_path.write_text(json.dumps(parent), encoding="utf-8")
        fixed = {
            "proposal_count": 5,
            "action_aggregation": "median",
            "noise_scale": 0.5,
            "num_inference_timesteps": 4,
            "model_action_horizon": 16,
        }
        limits = [0.01, 0.02, 0.03, 0.04, 0.005, 0.05]
        experiment = {
            "parent_temporal_summary_sha256": sha256_file(parent_path),
            "parent_temporal_experiment_sha256": parent_experiment,
            "parent_result": {"best_arm": parent_arm},
            "frozen_identities": {
                "nominal_checkpoint_id": "checkpoint-4000",
                "nominal_checkpoint_aggregate_manifest_sha256": "manifest",
                "nvidia_source_commit": "source",
                "base_task_contract_canonical_sha256": "task",
            },
            "fixed_model_inference": fixed,
            "fixed_temporal_executor": {
                key: parent_arm[key]
                for key in (
                    "execution_horizon",
                    "temporal_action_aggregation",
                    "temporal_decay",
                    "maximum_overlapping_predictions",
                )
            },
            "rate_limiter": {
                "source": "training-p95",
                "maximum_abs_delta_per_sample": limits,
                "initial_reference": "env.controls_before_first_policy_action",
            },
            "action_execution_adapter": {"method": "linear_same_phase"},
            "renderer": {
                "mujoco_gl": "osmesa",
                "pyopengl_platform": "osmesa",
                "development_cadence": "policy_queries",
                "sealed_promotion_cadence": "all_samples",
            },
            "development": {
                "arm_id": "rate95",
                "episode_indices": [0],
                "inference_seeds": [0, 1],
            },
        }
        experiment_path = root / "experiment.json"
        experiment_path.write_text(json.dumps(experiment), encoding="utf-8")
        rollouts = root / "rollouts"
        for seed in (0, 1):
            receipt_root = rollouts / "rate95" / f"training-episode-0-seed-{seed}"
            receipt_root.mkdir(parents=True)
            gates = {
                name: {"passed": True, "measured": 0.0}
                for name in (
                    "assistance_frames",
                    "model_owned_actions",
                    "maximum_other_piece_displacement",
                    "final_xy_error",
                    "final_upright_cosine",
                    "minimum_piece_rise",
                )
            }
            receipt = {
                "split": "training",
                "episode_index": 0,
                "inference_seed": seed,
                "checkpoint_id": "checkpoint-4000",
                "checkpoint_manifest_sha256": "manifest",
                "groot_source_commit": "source",
                "task_contract_sha256": "task",
                "action_consensus": {
                    key: fixed[key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                },
                "execution_horizon": 8,
                "temporal_action_aggregation": {
                    "method": "mean",
                    "exponential_decay": 0.5,
                    "maximum_overlapping_predictions": 2,
                    "model_chunks_only": True,
                    "causal": True,
                },
                "action_rate_limiter": {
                    "enabled": True,
                    "source": "training-p95",
                    "maximum_abs_delta_per_sample": limits,
                    "initial_reference": "env.controls_before_first_policy_action",
                    "model_targets_only": True,
                    "task_geometry_used": False,
                    "reward_used": False,
                    "assistance_frames": 0,
                    "rate_limited_sample_count": 1,
                    "maximum_applied_abs_delta": limits,
                },
                "action_execution_adapter": {"method": "linear_same_phase"},
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
                "maximum_piece_rise_m": 0.05,
                "verdict": {"success": True, "gates": gates},
            }
            (receipt_root / "receipt.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
        return experiment_path, parent_path, rollouts

    def _run(
        self, experiment: Path, parent: Path, rollouts: Path, output: Path
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

    def test_freezes_rate_limited_configuration_after_two_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, parent, rollouts = self._write_fixture(root)
            output = root / "summary.json"
            result = self._run(experiment, parent, rollouts, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(summary["held_out_may_open"])
            self.assertFalse(summary["promotion_authority"])
            self.assertEqual(len(summary["winning_configuration_sha256"]), 64)

    def test_rejects_wrong_rate_limit_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, parent, rollouts = self._write_fixture(root)
            path = rollouts / "rate95" / "training-episode-0-seed-0" / "receipt.json"
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["action_rate_limiter"]["source"] = "wrong"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            result = self._run(
                experiment, parent, rollouts, root / "summary.json"
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("wrong rate-limit source", result.stderr)


if __name__ == "__main__":
    unittest.main()
