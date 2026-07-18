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
                "candidate_arms": [arm],
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
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
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
            ],
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


if __name__ == "__main__":
    unittest.main()
