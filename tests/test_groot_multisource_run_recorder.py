from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "brev"
    / "record_groot_n17_multisource_run.py"
)
SPEC = importlib.util.spec_from_file_location(
    "record_groot_n17_multisource_run",
    MODULE_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("failed to load multisource run recorder")
RECORDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECORDER)
checkpoint_manifest = RECORDER.checkpoint_manifest
rank12_contract_identities = RECORDER.rank12_contract_identities
sha256_file = RECORDER.sha256_file


class GrootMultisourceRunRecorderTests(unittest.TestCase):
    def test_checkpoint_manifest_retains_complete_payload_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)
            for name in (
                "config.json",
                "model.safetensors.index.json",
                "processor_config.json",
                "statistics.json",
                "trainer_state.json",
                "model-00001-of-00001.safetensors",
            ):
                (checkpoint / name).write_text(name, encoding="utf-8")

            manifest = checkpoint_manifest(checkpoint, 1000)

            self.assertEqual(manifest["checkpoint_step"], 1000)
            self.assertEqual(manifest["file_count"], 6)

    def test_preserves_historical_v1_beside_current_v2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluations = root / "configs" / "evaluations"
            evaluations.mkdir(parents=True)
            historical = evaluations / "pawn_rank12_bidirectional_v1.json"
            current = evaluations / "pawn_rank12_bidirectional_v2.json"
            historical.write_text(
                '{"evaluation_set_id":"pawn_rank12_bidirectional_v1"}\n',
                encoding="utf-8",
            )
            current.write_text(
                '{"evaluation_set_id":"pawn_rank12_bidirectional_b_to_g_v2"}\n',
                encoding="utf-8",
            )

            identities = rank12_contract_identities(root)

            self.assertEqual(
                identities["historical_completed_run_contract"]["sha256"],
                sha256_file(historical),
            )
            self.assertEqual(
                identities["current_product_contract"]["sha256"],
                sha256_file(current),
            )
            self.assertTrue(
                identities["completed_run_contract_was_not_rewritten"]
            )

    def test_rejects_a_mislabeled_current_v2_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evaluations = root / "configs" / "evaluations"
            evaluations.mkdir(parents=True)
            (evaluations / "pawn_rank12_bidirectional_v1.json").write_text(
                '{"evaluation_set_id":"pawn_rank12_bidirectional_v1"}\n',
                encoding="utf-8",
            )
            (evaluations / "pawn_rank12_bidirectional_v2.json").write_text(
                '{"evaluation_set_id":"wrong-scope"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "current rank-12 v2"):
                rank12_contract_identities(root)


if __name__ == "__main__":
    unittest.main()
