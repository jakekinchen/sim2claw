"""V2 canonical seeded static compiler with calibrated model ranges."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _v1
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class CanonicalSeededActionStaticV2Error(RuntimeError):
    """The calibrated-range successor failed closed."""


def _calibrated_registered_model(
    original: Any,
    candidate_config: dict[str, Any],
):
    body_ranges = candidate_config["model"]["calibrated_body_ranges"]
    physical_minimum = np.asarray(
        [body_ranges["minimum"] + [0.0]], dtype=np.float64
    )
    physical_maximum = np.asarray(
        [body_ranges["maximum"] + [100.0]], dtype=np.float64
    )
    model_minimum = _physical_to_model_position(
        physical_minimum, candidate_config
    )[0]
    model_maximum = _physical_to_model_position(
        physical_maximum, candidate_config
    )[0]

    def build(rigid: dict[str, Any], timestep_s: float):
        model, addresses, robot_bodies, jaw_bodies = original(
            rigid, timestep_s
        )
        for index, name in enumerate(_v1.ALL_JOINTS):
            joint_id = _v1._named_id(
                model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            lower = min(model_minimum[index], model_maximum[index])
            upper = max(model_minimum[index], model_maximum[index])
            model.jnt_range[joint_id] = [lower, upper]
            actuator_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_ACTUATOR, name
            )
            if actuator_id >= 0:
                model.actuator_ctrlrange[actuator_id] = [lower, upper]
        mujoco.mj_setConst(model, mujoco.MjData(model))
        return model, addresses, robot_bodies, jaw_bodies

    return build


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run V1 enumeration with prospectively bound calibrated model ranges."""

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.canonical_seeded_action_static.v2"
    ):
        raise CanonicalSeededActionStaticV2Error(
            "unexpected canonical seeded static V2 contract"
        )
    manifest_path = _v1._bound(contract["inputs"]["candidate_manifest"])
    _v1._bound(contract["inputs"]["base_compiler_implementation"])
    _v1._bound(contract["inputs"]["compiler_implementation"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    decision = _v1._json(contract["inputs"]["v1_defect_closeout"])
    if (
        decision["status"]
        != "v1_static_pass_invalidated_by_stock_model_range_defect"
        or decision["authority"]["dynamic_simulation"] is not False
        or decision["authority"]["physical_motion"] is not False
    ):
        raise CanonicalSeededActionStaticV2Error(
            "V1 defect closeout authority changed"
        )

    original = _v1._registered_current_model
    _v1._registered_current_model = _calibrated_registered_model(
        original, manifest["candidate_config"]
    )
    translated = dict(contract)
    translated["schema_version"] = (
        "sim2claw.canonical_seeded_action_static.v1"
    )
    translated_id = hashlib.sha256(
        str(output_directory).encode("utf-8")
    ).hexdigest()
    translated_path = (
        REPO_ROOT
        / "runs/.canonical-seeded-action-static-v2-translated"
        / f"{translated_id}.json"
    )
    if translated_path.exists():
        raise CanonicalSeededActionStaticV2Error(
            "translated V2 contract path already exists"
        )
    translated_path.parent.mkdir(parents=True, exist_ok=True)
    translated_path.write_text(
        json.dumps(translated, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        receipt = _v1.enumerate_and_freeze(
            translated_path, output_directory
        )
    finally:
        _v1._registered_current_model = original
        translated_path.unlink(missing_ok=True)

    selected_margins = [
        float(row["compile"]["minimum_model_joint_margin_rad"])
        for row in receipt["selected"]
    ]
    model_margin_passed = bool(
        selected_margins
        and min(selected_margins)
        >= float(contract["gates"]["minimum_model_joint_margin_rad"])
    )
    passed = bool(receipt["passed"] and model_margin_passed)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.canonical_seeded_action_static_receipt.v2"
            ),
            "status": (
                "canonical_seeded_action_static_v2_pass"
                if passed
                else "canonical_seeded_action_static_v2_reject"
            ),
            "proof_class": (
                "cpu_fp64_canonical_current_anchor_seeded_calibrated_"
                "range_static_action_freeze"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _v1._sha(contract_path),
            "calibrated_model_ranges_applied": True,
            "calibrated_range_source_sha256": body_ranges_sha256(
                manifest["candidate_config"]["model"][
                    "calibrated_body_ranges"
                ]
            ),
            "minimum_selected_model_joint_margin_rad": min(
                selected_margins, default=float("-inf")
            ),
            "model_joint_margin_gate_passed": model_margin_passed,
            "v1_defect_reused_as_success_evidence": False,
            "passed": passed,
            "authority": contract["authority"],
            "claim_boundary": contract["claim_boundary"],
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def body_ranges_sha256(value: dict[str, Any]) -> str:
    import hashlib

    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CanonicalSeededActionStaticV2Error",
    "enumerate_and_freeze",
]
