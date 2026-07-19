from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = REPO_ROOT / "scripts" / "analyze_groot_n17_consensus_closed_loop.py"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GrootConsensusClosedLoopAnalysisTest(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        assistance_frames: int = 0,
    ) -> tuple[Path, Path, Path]:
        arm = {
            "id": "candidate-k5",
            "proposal_count": 5,
            "action_aggregation": "medoid",
            "noise_scale": 0.5,
            "num_inference_timesteps": 4,
        }
        baseline_arm = {
            "id": "baseline-k1",
            "proposal_count": 1,
            "action_aggregation": "medoid",
            "noise_scale": 1.0,
            "num_inference_timesteps": 4,
        }
        experiment = {
            "frozen_identities": {
                "nominal_checkpoint_id": "checkpoint-4000",
                "nominal_checkpoint_aggregate_manifest_sha256": "manifest",
                "nvidia_source_commit": "source",
                "base_task_contract_canonical_sha256": "task",
            },
            "renderer": {
                "mujoco_gl": "osmesa",
                "pyopengl_platform": "osmesa",
            },
            "invariants": {"execution_horizon": 8},
            "row_zero_development_probe": {
                "candidate_arms": [baseline_arm, arm],
                "shortlist_rule": {"maximum_nonbaseline_arms": 1},
            },
            "closed_loop_development": {
                "episode_indices": [0],
                "inference_seeds": [0, 1],
                "selection_order": [
                    "full_task_consequence_pass_count",
                    "board_safety_pass_count",
                    "final_xy_pass_count",
                    "upright_pass_count",
                    "lift_pass_count",
                ],
            },
        }
        experiment_path = root / "experiment.json"
        experiment_path.write_text(json.dumps(experiment), encoding="utf-8")
        probe_summary = {
            "promotion_authority": False,
            "experiment_sha256": sha256_file(experiment_path),
            "nonbaseline_shortlist": [arm["id"]],
        }
        probe_path = root / "probe-summary.json"
        probe_path.write_text(json.dumps(probe_summary), encoding="utf-8")
        rollout_root = root / "rollouts"
        for inference_seed in (0, 1):
            receipt_root = (
                rollout_root
                / arm["id"]
                / f"training-episode-0-seed-{inference_seed}"
            )
            receipt_root.mkdir(parents=True)
            gates = {
                name: {"passed": True}
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
                "inference_seed": inference_seed,
                "checkpoint_id": "checkpoint-4000",
                "checkpoint_manifest_sha256": "manifest",
                "groot_source_commit": "source",
                "task_contract_sha256": "task",
                "action_consensus": {
                    key: arm[key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                },
                "execution_horizon": 8,
                "all_actions_model_owned": True,
                "assistance_frames": assistance_frames,
                "action_execution_adapter": {
                    "method": "sample_hold",
                    "model_waypoints_only": True,
                    "assistance_frames": 0,
                },
                "render_cadence": {
                    "method": "all_samples",
                    "policy_observation_frames_omitted": False,
                },
                "render_backend": {
                    "mujoco_gl": "osmesa",
                    "pyopengl_platform": "osmesa",
                },
                "verdict": {"success": True, "gates": gates},
            }
            (receipt_root / "receipt.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
        return experiment_path, probe_path, rollout_root

    def _run(
        self,
        experiment: Path,
        probe_summary: Path,
        rollout_root: Path,
        output: Path,
        waypoint_experiment: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
                sys.executable,
                str(ANALYZER),
                "--experiment",
                str(experiment),
                "--probe-summary",
                str(probe_summary),
                "--rollout-root",
                str(rollout_root),
                "--output",
                str(output),
            ]
        if waypoint_experiment is not None:
            command.extend(["--waypoint-experiment", str(waypoint_experiment)])
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_freezes_configuration_only_after_two_training_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, probe_summary, rollouts = self._write_fixture(root)
            output = root / "summary.json"
            result = self._run(experiment, probe_summary, rollouts, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(summary["promotion_authority"])
            self.assertTrue(summary["held_out_may_open"])
            self.assertEqual(
                summary["winning_configuration"]["id"],
                "candidate-k5",
            )
            self.assertEqual(len(summary["winning_configuration_sha256"]), 64)

    def test_rejects_assisted_development_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, probe_summary, rollouts = self._write_fixture(
                root, assistance_frames=1
            )
            result = self._run(
                experiment,
                probe_summary,
                rollouts,
                root / "summary.json",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("includes assistance", result.stderr)

    def test_waypoint_experiment_requires_adapter_and_baseline_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, probe_summary, rollouts = self._write_fixture(root)
            parent = json.loads(experiment.read_text(encoding="utf-8"))
            baseline = parent["row_zero_development_probe"]["candidate_arms"][0]
            for inference_seed in (0, 1):
                candidate_path = (
                    rollouts
                    / "candidate-k5"
                    / f"training-episode-0-seed-{inference_seed}"
                    / "receipt.json"
                )
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                candidate["action_execution_adapter"]["method"] = "linear_same_phase"
                candidate["render_cadence"]["method"] = "policy_queries"
                candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
                baseline_receipt = dict(candidate)
                baseline_receipt["action_consensus"] = {
                    key: baseline[key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                }
                baseline_root = (
                    rollouts
                    / "baseline-k1"
                    / f"training-episode-0-seed-{inference_seed}"
                )
                baseline_root.mkdir(parents=True)
                (baseline_root / "receipt.json").write_text(
                    json.dumps(baseline_receipt), encoding="utf-8"
                )
            waypoint = {
                "parent_consensus_experiment_sha256": sha256_file(experiment),
                "frozen_identities": parent["frozen_identities"],
                "action_execution_adapter": {"method": "linear_same_phase"},
                "renderer": {
                    "mujoco_gl": "osmesa",
                    "pyopengl_platform": "osmesa",
                    "development_cadence": "policy_queries",
                },
                "development": {
                    "episode_indices": [0],
                    "inference_seeds": [0, 1],
                    "execution_horizon": 8,
                    "maximum_candidate_arms": 2,
                    "selection_order": parent["closed_loop_development"][
                        "selection_order"
                    ],
                },
            }
            waypoint_path = root / "waypoint.json"
            waypoint_path.write_text(json.dumps(waypoint), encoding="utf-8")
            output = root / "waypoint-summary.json"
            result = self._run(
                experiment,
                probe_summary,
                rollouts,
                output,
                waypoint_experiment=waypoint_path,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(summary["held_out_may_open"])
            self.assertEqual(len(summary["ranked_arms"]), 2)
            configuration = summary["winning_configuration"]
            self.assertEqual(
                configuration["physics_action_adapter"], "linear_same_phase"
            )
            self.assertEqual(
                configuration["development_render_cadence"], "policy_queries"
            )


if __name__ == "__main__":
    unittest.main()
