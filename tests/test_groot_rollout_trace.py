from __future__ import annotations

import unittest

import numpy as np

from sim2claw.groot_rollout_trace import (
    array_sha256,
    contact_transition_events,
    validate_integration_state_digests,
    validate_rollout_trace_lengths,
)


class GrootRolloutTraceTests(unittest.TestCase):
    def test_array_hash_binds_dtype_shape_and_payload(self) -> None:
        value = np.asarray([[1.0, 2.0]], dtype=np.float32)
        self.assertNotEqual(array_sha256(value), array_sha256(value.astype(np.float64)))
        self.assertNotEqual(array_sha256(value), array_sha256(value.reshape(2, 1)))
        changed = value.copy()
        changed[0, 1] = 3.0
        self.assertNotEqual(array_sha256(value), array_sha256(changed))

    def test_contact_events_preserve_grasp_and_release_timing(self) -> None:
        events = contact_transition_events(
            np.asarray([False, True, True, False], dtype=np.bool_),
            physics_steps=np.asarray([1, 2, 3, 4]),
            times_seconds=np.asarray([0.005, 0.010, 0.015, 0.020]),
            contact_name="target_jaw_contact",
        )
        self.assertEqual(
            [event["event"] for event in events],
            ["target_jaw_contact_started", "target_jaw_contact_ended"],
        )
        self.assertEqual(events[0]["physics_step"], 2)
        self.assertEqual(events[1]["time_seconds"], 0.020)

    def test_trace_validation_rejects_requested_applied_misalignment(self) -> None:
        with self.assertRaisesRegex(ValueError, "different shapes"):
            validate_rollout_trace_lengths(
                sample_count=2,
                requested_actions=np.zeros((2, 6), dtype=np.float32),
                applied_actions=np.zeros((2, 5), dtype=np.float64),
                integration_states=np.zeros((2, 8), dtype=np.float64),
                integration_state_digests=np.asarray(["a", "b"], dtype="U64"),
                pawn_positions=np.zeros((2, 16, 3), dtype=np.float64),
                pawn_rotations=np.zeros((2, 16, 3, 3), dtype=np.float64),
                end_effector_positions=np.zeros((2, 3), dtype=np.float64),
            )

    def test_integration_state_digest_validation_rejects_tamper(self) -> None:
        states = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
        digests = np.asarray(
            [array_sha256(row) for row in states],
            dtype="U64",
        )
        validate_integration_state_digests(states, digests)
        digests[1] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest drifted at row 1"):
            validate_integration_state_digests(states, digests)


if __name__ == "__main__":
    unittest.main()
