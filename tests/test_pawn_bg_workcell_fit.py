from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from sim2claw.pawn_bg_actuator_sysid import _apply_parameters, load_candidate
from sim2claw.pawn_bg_workcell_fit import (
    WorkcellCandidate,
    WorkcellFitError,
    _product_episodes,
    load_workcell_contract,
)
from sim2claw.scene import board_square_center, load_capture_config


class PawnBGWorkcellFitTests(unittest.TestCase):
    def test_contract_keeps_candidate_non_authorizing(self) -> None:
        contract = load_workcell_contract()
        self.assertEqual(contract["schema_version"], "sim2claw.pawn_bg_workcell_fit.v1")
        self.assertTrue(contract["admission"]["declared_before_held_out_opened"])
        self.assertEqual(contract["admission"]["maximum_held_out_event_rms_m"], 0.06)
        self.assertTrue(all(value is False for value in contract["authority"].values()))

    def test_contract_schema_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"schema_version": "unexpected"}), encoding="utf-8")
            with self.assertRaisesRegex(WorkcellFitError, "unexpected workcell fit"):
                load_workcell_contract(path)

    def test_candidate_adapter_keeps_identity_signs_and_rejected_authority(self) -> None:
        candidate = WorkcellCandidate(
            board_yaw_relative_to_table_degrees=181.0,
            board_center_in_table_frame_xy_m=(0.01, -0.02),
            joint_zero_offsets_rad=(0.1, 0.2, 0.3, 0.4, 0.0),
            joint_range_envelope_rad=tuple((-1.0, 1.0) for _ in range(5)),
        )
        adapter = candidate.adapter()
        self.assertEqual(adapter.body_joint_signs, (1, 1, 1, 1, 1))
        self.assertEqual(adapter.body_joint_zero_offsets_rad, candidate.joint_zero_offsets_rad)
        self.assertEqual(
            adapter.evidence_class,
            "bounded_zero_offset_candidate_not_physically_validated",
        )

    def test_product_scope_requires_all_thirteen_reviewed_recordings(self) -> None:
        labels = [
            "b1-to-b2", "b2-to-b1", "c1-to-c2", "c2-to-c1", "c2-to-c1-redo",
            "d1-to-d2", "d2-to-d1", "e1-to-e2", "e2-to-e1", "f1-to-f2",
            "f2-to-f1", "g1-to-g2-redo", "g2-to-g1",
        ]
        catalog = {
            "episodes": [
                {"recording_id": f"episode-{index}", "folder_label": label}
                for index, label in enumerate(labels)
            ]
        }
        self.assertEqual(len(_product_episodes(catalog)), 13)
        with self.assertRaisesRegex(WorkcellFitError, "must contain 13"):
            _product_episodes({"episodes": catalog["episodes"][:-1]})

    def test_board_yaw_override_is_opt_in(self) -> None:
        config = load_capture_config()
        frozen_yaw = float(
            config["simulation_estimates"]["board"]["yaw_relative_to_table_degrees"]
        )
        default = np.asarray(board_square_center("b1"))
        explicit_default = np.asarray(
            board_square_center("b1", board_yaw_relative_to_table_degrees=frozen_yaw)
        )
        rotated = np.asarray(
            board_square_center("b1", board_yaw_relative_to_table_degrees=frozen_yaw + 180.0)
        )
        np.testing.assert_allclose(default, explicit_default, atol=1e-12)
        self.assertGreater(float(np.linalg.norm(default[:2] - rotated[:2])), 0.05)
        self.assertAlmostEqual(float(default[2]), float(rotated[2]), places=12)

    def test_actuator_parameter_scaling_is_bounded_to_requested_arrays(self) -> None:
        model = SimpleNamespace(
            actuator_gainprm=np.asarray([[2.0], [3.0]]),
            actuator_biasprm=np.asarray([[0.0, -2.0], [0.0, -3.0]]),
            actuator_forcerange=np.asarray([[-4.0, 4.0], [-5.0, 5.0]]),
            jnt_dofadr=np.asarray([0, 1]),
            dof_damping=np.asarray([0.5, 0.75]),
        )
        _apply_parameters(
            model,
            actuator_ids=[0, 1],
            joint_ids=[0, 1],
            parameters={
                "actuator_gain_scale": 1.1,
                "joint_damping_scale": 1.2,
                "actuator_forcerange_scale": 0.9,
            },
        )
        np.testing.assert_allclose(model.actuator_gainprm[:, 0], [2.2, 3.3])
        np.testing.assert_allclose(model.actuator_biasprm[:, 1], [-2.2, -3.3])
        np.testing.assert_allclose(model.actuator_forcerange, [[-3.6, 3.6], [-4.5, 4.5]])
        np.testing.assert_allclose(model.dof_damping, [0.6, 0.9])

    def test_actuator_receipt_loader_preserves_frozen_candidate(self) -> None:
        payload = {
            "selected_parameters": {
                "board_yaw_relative_to_table_degrees": 184.9,
                "board_center_in_table_frame_xy_m": [-0.01, -0.066],
                "joint_zero_offsets_rad": [0.0, 0.32, 0.0, 0.0, 0.0],
                "joint_range_envelope_rad": [[-1.0, 1.0]] * 5,
                "base_z_offset_m": 0.0,
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            candidate = load_candidate(path)
        self.assertAlmostEqual(candidate.board_yaw_relative_to_table_degrees, 184.9)
        self.assertEqual(candidate.joint_zero_offsets_rad[1], 0.32)
        self.assertEqual(candidate.adapter().body_joint_signs, (1, 1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
