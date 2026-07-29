"""Static-only elbow-locked directional pawn-displacement successor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import canonical_elbow_locked_low_path_static as _low
from . import canonical_elbow_locked_wrist_path_static as _elbow
from . import canonical_wrist_path_static as _wrist


def enumerate_and_freeze(
    contract_path: Path, output_directory: Path
) -> dict[str, Any]:
    """Run the frozen head-height contact search exactly once."""

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    bridge = json.loads(
        (
            contract_path.parents[2]
            / str(contract["base_contract"]["path"])
        ).read_text(encoding="utf-8")
    )
    base = json.loads(
        (
            contract_path.parents[2]
            / str(bridge["base_contract"]["path"])
        ).read_text(encoding="utf-8")
    )
    minimum_contact_height = float(
        base["gates"]["minimum_first_contact_height_m"]
    )
    original = _wrist._compile
    original_witness = _wrist._first_contact_witness

    def witness_with_minimum(**kwargs: Any) -> dict[str, Any]:
        witness = original_witness(**kwargs)
        observed_height = witness.get(
            "contact_height_relative_initial_pawn_root_m"
        )
        witness["minimum_required_contact_height_m"] = minimum_contact_height
        witness["above_minimum_contact_height"] = bool(
            witness.get("observed")
            and observed_height is not None
            and float(observed_height) >= minimum_contact_height
        )
        if witness.get("observed") and not witness[
            "above_minimum_contact_height"
        ]:
            witness["observed"] = False
        return witness

    _wrist._compile = _low._compile_low_direct
    _wrist._first_contact_witness = witness_with_minimum
    try:
        receipt = _elbow.enumerate_and_freeze(
            contract_path.resolve(), output_directory.resolve()
        )
    finally:
        _wrist._compile = original
        _wrist._first_contact_witness = original_witness
    passed = bool(receipt["passed"])
    receipt.update(
        {
            "schema_version": (
                "sim2claw.directional_displacement_static_receipt.v1"
            ),
            "status": (
                "directional_displacement_static_pass"
                if passed
                else "directional_displacement_static_reject"
            ),
            "proof_class": (
                "cpu_fp64_elbow_locked_head_height_directional_displacement_static"
            ),
            "primitive_name": "directional pawn displacement",
            "straight_sliding_push_claim": False,
            "chess_play_claim": False,
            "dynamic_replay_executed": False,
            "physical_motion": False,
            "physical_task_attempts": 0,
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["enumerate_and_freeze"]
