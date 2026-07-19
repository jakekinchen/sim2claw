from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER = REPO_ROOT / "scripts" / "analyze_groot_n17_consensus_sweep.py"


class GrootConsensusAnalysisTest(unittest.TestCase):
    def _write_fixture(self, root: Path, *, split: str = "training") -> tuple[Path, Path]:
        experiment = {
            "row_zero_development_probe": {
                "episode_indices": [0],
                "inference_seeds": [7],
                "candidate_arms": [
                    {
                        "id": "baseline-k1",
                        "proposal_count": 1,
                        "action_aggregation": "medoid",
                        "noise_scale": 1.0,
                        "num_inference_timesteps": 4,
                    },
                    {
                        "id": "candidate-k5",
                        "proposal_count": 5,
                        "action_aggregation": "median",
                        "noise_scale": 0.5,
                        "num_inference_timesteps": 4,
                    },
                ],
                "shortlist_rule": {"maximum_nonbaseline_arms": 1},
            }
        }
        experiment_path = root / "experiment.json"
        experiment_path.write_text(json.dumps(experiment), encoding="utf-8")
        probe_root = root / "probes"
        for index, arm in enumerate(experiment["row_zero_development_probe"]["candidate_arms"]):
            arm_root = probe_root / str(arm["id"])
            arm_root.mkdir(parents=True)
            error = 2.0 - index
            payload = {
                "split": split,
                "repeatable": True,
                "episode_index": 0,
                "inference_seed": 7,
                "action_consensus": {
                    key: arm[key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                },
                "probes": [
                    {
                        "training_expert_diagnostic": {
                            "promotion_authority": False,
                            "chunk_mae": error,
                            "first_action_mae": error,
                        },
                        "action_info": {
                            "consensus": {"maximum_pairwise_l2": float(index)}
                        },
                    },
                    {
                        "training_expert_diagnostic": {
                            "promotion_authority": False,
                            "chunk_mae": error,
                            "first_action_mae": error,
                        },
                        "action_info": {
                            "consensus": {"maximum_pairwise_l2": float(index)}
                        },
                    },
                ],
            }
            (arm_root / "training-episode-0-seed-7.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
        return experiment_path, probe_root

    def _run(self, experiment: Path, probe_root: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(ANALYZER),
                "--experiment",
                str(experiment),
                "--probe-root",
                str(probe_root),
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_ranks_complete_training_only_matrix_without_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, probe_root = self._write_fixture(root)
            output = root / "summary.json"
            result = self._run(experiment, probe_root, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(summary["promotion_authority"])
            self.assertEqual(summary["nonbaseline_shortlist"], ["candidate-k5"])
            self.assertEqual(
                [row["id"] for row in summary["ranked_arms"]],
                ["candidate-k5", "baseline-k1"],
            )

    def test_rejects_held_out_probe_before_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            experiment, probe_root = self._write_fixture(root, split="held_out")
            result = self._run(experiment, probe_root, root / "summary.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("probe is not training-only", result.stderr)


if __name__ == "__main__":
    unittest.main()
