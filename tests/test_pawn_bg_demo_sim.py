from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.pawn_bg_demo_sim import _catalog_episodes, _load_source


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
