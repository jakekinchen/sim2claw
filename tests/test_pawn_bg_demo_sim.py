from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from sim2claw.pawn_bg_demo_sim import (
    JointAdapter,
    _catalog_episodes,
    _load_source,
    physical_values_to_sim_with_adapter,
)


def _episodes() -> list[dict[str, object]]:
    rows = []
    index = 0
    for file_ in "bcdefg":
        for source, destination in (("1", "2"), ("2", "1")):
            rows.append({
                "recording_id": f"recording-{index}",
                "folder_label": f"{file_}{source}-to-{file_}{destination}",
            })
            index += 1
    rows.append({"recording_id": "recording-12", "folder_label": "c2-to-c1"})
    return rows


class PawnBGDemoSimTests(unittest.TestCase):
    def test_joint_adapter_applies_exact_body_signs_and_offsets(self) -> None:
        adapter = JointAdapter(
            adapter_id="test",
            body_joint_signs=(-1, 1, -1, 1, -1),
            body_joint_zero_offsets_rad=(0.1, 0.2, 0.3, 0.4, 0.5),
            evidence_class="test_only",
        )
        converted = physical_values_to_sim_with_adapter(
            [10.0, 20.0, 30.0, 40.0, 50.0, 25.0],
            np.asarray([-0.2, 1.8]),
            adapter,
        )
        expected = np.deg2rad([10.0, 20.0, 30.0, 40.0, 50.0])
        np.testing.assert_array_equal(
            converted[:5],
            expected * np.asarray([-1, 1, -1, 1, -1])
            + np.asarray([0.1, 0.2, 0.3, 0.4, 0.5]),
        )
        self.assertEqual(converted[5], 0.3)

    def test_joint_adapter_types_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact -1/\\+1 integers"):
            JointAdapter(
                adapter_id="bad",
                body_joint_signs=(True, 1, 1, 1, 1),
                body_joint_zero_offsets_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
                evidence_class="test_only",
            )
        with self.assertRaisesRegex(ValueError, "finite floats"):
            JointAdapter(
                adapter_id="bad",
                body_joint_signs=(1, 1, 1, 1, 1),
                body_joint_zero_offsets_rad=(0, 0.0, 0.0, 0.0, 0.0),
                evidence_class="test_only",
            )

    def test_owner_scope_resolves_13_recordings_and_12_skills(self) -> None:
        selected = _catalog_episodes({"episodes": _episodes()})
        self.assertEqual(len(selected), 13)
        self.assertEqual(len({(source, destination) for _, source, destination in selected}), 12)

    def test_missing_or_out_of_scope_recording_fails_closed(self) -> None:
        episodes = _episodes()
        episodes.pop()
        with self.assertRaisesRegex(ValueError, "13 recordings"):
            _catalog_episodes({"episodes": episodes})
        episodes = _episodes()
        episodes[-1]["folder_label"] = "a1-to-a2"
        with self.assertRaisesRegex(ValueError, "13 recordings"):
            _catalog_episodes({"episodes": episodes})

    def test_source_bytes_and_receipt_are_hash_bound(self) -> None:
        sample = {
            "timestamp_monotonic_seconds": 1.0,
            "follower_command_degrees": [0, 0, 0, 0, 0, 50],
            "follower_actual_position_degrees": [0, 0, 0, 0, 0, 50],
        }
        samples_bytes = (json.dumps(sample) + "\n").encode()
        samples_hash = hashlib.sha256(samples_bytes).hexdigest()
        receipt = {"mode": "physical_follower", "samples_sha256": samples_hash}
        receipt_bytes = json.dumps(receipt).encode()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            recording = root / "recording"
            recording.mkdir()
            (recording / "samples.jsonl").write_bytes(samples_bytes)
            (recording / "recording_receipt.json").write_bytes(receipt_bytes)
            episode = {
                "recording_id": "recording-0",
                "sample_count": 1,
                "samples_sha256": samples_hash,
                "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "assets": {
                    "samples": "recording/samples.jsonl",
                    "receipt": "recording/recording_receipt.json",
                },
            }
            self.assertEqual(_load_source(episode, root), [sample])
            (recording / "samples.jsonl").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fail catalog hashes"):
                _load_source(episode, root)


if __name__ == "__main__":
    unittest.main()
