from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sim2claw.act_model import ACTCheckpointSnapshot
from sim2claw.manipulation_v2 import _accepted_checkpoint_snapshot


class ManipulationCheckpointSnapshotTest(unittest.TestCase):
    def test_path_requires_accepted_digest_before_read(self) -> None:
        with mock.patch("pathlib.Path.read_bytes") as read_bytes:
            with self.assertRaisesRegex(ValueError, "accepted digest"):
                _accepted_checkpoint_snapshot(
                    Path("checkpoint.pt"), expected_checkpoint_sha256=None
                )
        read_bytes.assert_not_called()

    def test_rejected_path_bytes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.pt"
            path.write_bytes(b"rejected")
            with self.assertRaisesRegex(ValueError, "accepted digest"):
                _accepted_checkpoint_snapshot(
                    path, expected_checkpoint_sha256="0" * 64
                )

    def test_rejected_existing_snapshot_fails_closed(self) -> None:
        snapshot = ACTCheckpointSnapshot(Path("checkpoint.pt"), "0" * 64, b"bad")
        with self.assertRaisesRegex(ValueError, "accepted digest"):
            _accepted_checkpoint_snapshot(
                snapshot, expected_checkpoint_sha256="1" * 64
            )

    def test_forged_existing_snapshot_with_accepted_declared_digest_fails(self) -> None:
        expected = "1" * 64
        snapshot = ACTCheckpointSnapshot(Path("checkpoint.pt"), expected, b"forged")
        with self.assertRaisesRegex(ValueError, "does not match its bytes"):
            _accepted_checkpoint_snapshot(
                snapshot, expected_checkpoint_sha256=expected
            )

    def test_path_replacement_cannot_change_accepted_snapshot(self) -> None:
        accepted = b"accepted immutable manipulation snapshot"
        replacement = b"replacement"
        digest = hashlib.sha256(accepted).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.pt"
            path.write_bytes(accepted)
            snapshot = _accepted_checkpoint_snapshot(
                path, expected_checkpoint_sha256=digest
            )
            path.write_bytes(replacement)

        self.assertEqual(snapshot.sha256, digest)
        self.assertEqual(snapshot.data, accepted)
        self.assertNotEqual(snapshot.data, replacement)


if __name__ == "__main__":
    unittest.main()
