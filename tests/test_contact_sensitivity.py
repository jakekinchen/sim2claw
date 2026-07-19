from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from sim2claw.act_model import (
    load_act_checkpoint_snapshot,
    read_act_checkpoint_snapshot,
)
from sim2claw.contact_prior import ContactPriorSnapshot, load_contact_prior_contract
from sim2claw.contact_sensitivity import (
    run_contact_sensitivity,
    summarize_contact_sensitivity,
)


def _receipt(variant: str, *, success: bool, rise: float, action_hash: str) -> dict:
    return {
        "policy": {"checkpoint_snapshot_sha256": "accepted"},
        "simulator_variant": {
            "variant_id": variant,
            "variant_sha256": variant * 8,
            "compiled_identity": {
                "compiled_dynamics_sha256": variant,
                "compiled_inertial_control_sha256": "same-inertial-control",
                "compiled_total_body_mass_kg": 1.0,
                "modeled_added_mass_kg": 0.0,
                "bindings": [],
            },
        },
        "success": success,
        "terminal_outcome": "held_rook_above_board" if success else "act_episode_failed",
        "failed_gates": [] if success else ["final_piece_rise"],
        "episode": {
            "maximum_piece_rise_m": rise,
            "final_piece_rise_m": rise,
            "longest_contact_control_steps": 100,
            "final_contact_fraction": 1.0,
            "contact_timing": {"first_contact_control_step": 900},
        },
        "artifacts": {
            "action_trace_sha256": action_hash,
            "state_trace_sha256": variant,
        },
        "stability": {"finite_state": True},
    }


class CheckpointSnapshotTest(unittest.TestCase):
    def test_missing_checkpoint_fails_before_deserialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.pt"
            with mock.patch("sim2claw.act_model.torch.load") as torch_load:
                with self.assertRaises(FileNotFoundError):
                    read_act_checkpoint_snapshot(path, expected_sha256="0" * 64)
                torch_load.assert_not_called()

    def test_rejected_hash_fails_before_torch_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.pt"
            path.write_bytes(b"rejected")
            with mock.patch("sim2claw.act_model.torch.load") as torch_load:
                with self.assertRaisesRegex(ValueError, "accepted digest"):
                    read_act_checkpoint_snapshot(path, expected_sha256="0" * 64)
                torch_load.assert_not_called()

    def test_path_replacement_after_snapshot_cannot_change_deserialized_bytes(self) -> None:
        accepted = b"accepted immutable snapshot"
        replacement = b"replacement bytes"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.pt"
            path.write_bytes(accepted)
            snapshot = read_act_checkpoint_snapshot(
                path, expected_sha256=hashlib.sha256(accepted).hexdigest()
            )
            path.write_bytes(replacement)
            with mock.patch(
                "sim2claw.act_model.torch.load", return_value={}
            ) as torch_load:
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    load_act_checkpoint_snapshot(snapshot, device=torch.device("cpu"))
                stream = torch_load.call_args.args[0]
                self.assertIsInstance(stream, io.BytesIO)
                self.assertEqual(stream.getvalue(), accepted)
                self.assertNotEqual(stream.getvalue(), path.read_bytes())

    def test_post_preflight_path_replacement_does_not_change_any_variant_snapshot(self) -> None:
        accepted = b"accepted benchmark snapshot"
        replacement = b"replacement benchmark bytes"
        contract = load_contact_prior_contract()
        contract["policy"]["accepted_checkpoint_sha256"] = hashlib.sha256(
            accepted
        ).hexdigest()
        canonical = json.dumps(
            contract, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        contract_snapshot = ContactPriorSnapshot(
            Path("contract.json"), hashlib.sha256(canonical).hexdigest(), canonical
        )
        seen_snapshot_ids: list[int] = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "checkpoint.pt"
            path.write_bytes(accepted)

            def fake_preflight(snapshot, **kwargs):
                self.assertEqual(snapshot.data, accepted)
                path.write_bytes(replacement)
                return {
                    "checkpoint_snapshot_sha256": snapshot.sha256,
                    "status": "compatible",
                }

            def fake_evaluate(snapshot, *, simulator_variant, **kwargs):
                seen_snapshot_ids.append(id(snapshot))
                self.assertEqual(snapshot.data, accepted)
                self.assertEqual(path.read_bytes(), replacement)
                receipt = _receipt(
                    simulator_variant.variant_id,
                    success=simulator_variant.variant_id != "rubber_tip_high",
                    rise=0.09 if simulator_variant.variant_id != "rubber_tip_high" else 0.01,
                    action_hash=simulator_variant.variant_id,
                )
                receipt["policy"]["checkpoint_snapshot_sha256"] = snapshot.sha256
                receipt["simulator_variant"]["variant_sha256"] = (
                    simulator_variant.variant_sha256
                )
                return receipt

            with (
                mock.patch(
                    "sim2claw.contact_sensitivity.read_contact_prior_snapshot",
                    return_value=contract_snapshot,
                ),
                mock.patch(
                    "sim2claw.contact_sensitivity.preflight_contact_sensitivity",
                    side_effect=fake_preflight,
                ),
                mock.patch(
                    "sim2claw.contact_sensitivity.evaluate_act",
                    side_effect=fake_evaluate,
                ),
            ):
                report = run_contact_sensitivity(
                    path, output_directory=root / "output", render_video=False
                )
        self.assertEqual(len(seen_snapshot_ids), 4)
        self.assertEqual(len(set(seen_snapshot_ids)), 1)
        self.assertEqual(
            report["checkpoint_snapshot_sha256"], hashlib.sha256(accepted).hexdigest()
        )


class ContactSensitivitySummaryTest(unittest.TestCase):
    def test_contract_pins_the_only_accepted_rook_lift_checkpoint(self) -> None:
        contract = load_contact_prior_contract()
        self.assertEqual(
            contract["policy"]["accepted_checkpoint_sha256"],
            "f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc",
        )
        self.assertFalse(contract["policy"]["weights_mutable"])

    def test_summary_separates_sensitivity_and_preserves_snapshot_identity(self) -> None:
        report = summarize_contact_sensitivity(
            [
                _receipt("nominal", success=True, rise=0.09, action_hash="a"),
                _receipt("low", success=True, rise=0.08, action_hash="a"),
                _receipt("high", success=False, rise=0.01, action_hash="b"),
            ]
        )
        self.assertTrue(report["sensitivity"]["categorical_success_changed"])
        self.assertTrue(report["sensitivity"]["policy_actions_changed_with_contact_state"])
        self.assertAlmostEqual(report["sensitivity"]["maximum_piece_rise_range_m"], 0.08)
        self.assertTrue(report["identity_checks"]["same_checkpoint_snapshot_all_variants"])
        self.assertTrue(
            report["identity_checks"]["inertial_control_bitwise_identical_all_variants"]
        )
        self.assertTrue(
            report["identity_checks"]["total_body_mass_bitwise_identical_all_variants"]
        )
        self.assertTrue(report["rows"][0]["action_trace_matches_nominal"])
        self.assertFalse(report["rows"][2]["action_trace_matches_nominal"])


if __name__ == "__main__":
    unittest.main()
