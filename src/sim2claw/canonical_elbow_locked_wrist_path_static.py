"""Prospective static pawn-push search with the nonresponsive elbow locked."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_wrist_path_static as _wrist
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class CanonicalElbowLockedStaticError(RuntimeError):
    """The elbow-locked successor changed scope or failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalElbowLockedStaticError(
            "elbow-locked input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalElbowLockedStaticError(
            f"bound elbow-locked input changed: {path}"
        )
    return path


def _locked_elbow_solver(
    model: mujoco.MjModel,
    seed: np.ndarray,
    target: np.ndarray,
    pinch_local: np.ndarray,
    *,
    iterations: int,
    damping: float,
    step_limit: float,
) -> tuple[np.ndarray, float]:
    """Solve XYZ with pan, lift, and wrist flex while holding elbow exact."""

    scratch = mujoco.MjData(model)
    addresses = [
        int(
            model.jnt_qposadr[
                _static._named_id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            ]
        )
        for name in _static.ALL_JOINTS
    ]
    scratch.qpos[addresses] = seed
    active_indices = (0, 1, 3)
    columns = [
        int(
            model.jnt_dofadr[
                _static._named_id(
                    model,
                    mujoco.mjtObj.mjOBJ_JOINT,
                    _static.ARM_JOINTS[index],
                )
            ]
        )
        for index in active_indices
    ]
    joint_ids = [
        _static._named_id(
            model,
            mujoco.mjtObj.mjOBJ_JOINT,
            _static.ARM_JOINTS[index],
        )
        for index in active_indices
    ]
    elbow_id = _static._named_id(
        model, mujoco.mjtObj.mjOBJ_JOINT, _static.ARM_JOINTS[2]
    )
    elbow_address = int(model.jnt_qposadr[elbow_id])
    elbow_value = float(seed[2])
    tip_geom = _static._named_id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_sph_tip2"
    )
    tip_body = int(model.geom_bodyid[tip_geom])
    jacobian_full = np.zeros((3, model.nv), dtype=np.float64)
    identity = np.eye(3, dtype=np.float64)
    residual = float("inf")
    for _ in range(iterations):
        scratch.qpos[elbow_address] = elbow_value
        mujoco.mj_forward(model, scratch)
        tip = _static._pinch_point(model, scratch, "left", pinch_local)
        error = target - tip
        residual = float(np.linalg.norm(error))
        if residual < 0.0015:
            break
        mujoco.mj_jac(
            model, scratch, jacobian_full, None, tip, tip_body
        )
        jacobian = jacobian_full[:, columns]
        gain = jacobian @ jacobian.T + (damping**2) * identity
        update = jacobian.T @ np.linalg.solve(gain, error)
        update = np.clip(update, -step_limit, step_limit)
        for joint_id, delta in zip(joint_ids, update, strict=True):
            address = int(model.jnt_qposadr[joint_id])
            low, high = model.jnt_range[joint_id]
            scratch.qpos[address] = float(
                np.clip(scratch.qpos[address] + delta, low, high)
            )
    scratch.qpos[elbow_address] = elbow_value
    return np.asarray(scratch.qpos[addresses], dtype=np.float64), residual


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run the frozen static-only elbow-locked successor exactly once."""

    if output_directory.exists():
        raise CanonicalElbowLockedStaticError(
            "immutable elbow-locked output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "implementation",
        "live_seed",
        "unchanged_from_base",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.canonical_elbow_locked_wrist_path_static.v1"
        or contract.get("status")
        != "frozen_before_static_only_elbow_locked_enumeration"
        or not all(contract["unchanged_from_base"].values())
        or contract["authority"]
        != {
            "model_loading": True,
            "static_simulation": True,
            "dynamic_simulation": False,
            "mapping_approval": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        }
    ):
        raise CanonicalElbowLockedStaticError(
            "elbow-locked successor widened its contract"
        )
    for key in (
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "implementation",
    ):
        _bound(contract[key])
    base_path = _bound(contract["base_contract"])
    base = json.loads(base_path.read_text(encoding="utf-8"))
    predecessor_path = _bound(base["base_contract"])
    resolved = json.loads(predecessor_path.read_text(encoding="utf-8"))
    manifest_path = _bound(resolved["inputs"]["candidate_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    follower = np.asarray(
        [contract["live_seed"]["follower_position_degrees"]],
        dtype=np.float64,
    )
    model_seed = _physical_to_model_position(
        follower, manifest["candidate_config"]
    )[0]
    locked_index = int(contract["live_seed"]["locked_joint_index"])
    if (
        locked_index != 2
        or contract["live_seed"]["locked_joint_name"] != "elbow_flex"
        or float(contract["live_seed"]["locked_value_degrees"])
        != float(follower[0, locked_index])
    ):
        raise CanonicalElbowLockedStaticError(
            "elbow-locked seed contract changed"
        )
    resolved["live_seed"]["follower_position_degrees"] = follower[0].tolist()
    resolved["live_seed"]["model_radians"] = model_seed.tolist()
    resolved["output_directory"] = contract["output_directory"]
    resolved["claim_boundary"] = contract["claim_boundary"]
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    original_solver = _static._solve_fixed_roll
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="elbow-locked-resolved-",
            dir=output_directory.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(resolved, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_path = Path(handle.name)
        _static._solve_fixed_roll = _locked_elbow_solver
        receipt = _wrist.enumerate_and_freeze(
            temporary_path.resolve(), output_directory.resolve()
        )
    finally:
        _static._solve_fixed_roll = original_solver
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    elbow_values = []
    for row in receipt["selected"]:
        action_path = REPO_ROOT / row["action_path"]
        action = np.fromfile(action_path, dtype="<f8").reshape(
            row["action_shape"]
        )
        elbow_values.append(action[:, locked_index])
    elbow_exact = bool(
        elbow_values
        and all(
            np.array_equal(values, np.full_like(values, model_seed[2]))
            for values in elbow_values
        )
    )
    passed = bool(receipt["passed"] and elbow_exact)
    receipt.update(
        {
            "schema_version": (
                "sim2claw.canonical_elbow_locked_wrist_path_static_receipt.v1"
            ),
            "status": (
                "canonical_elbow_locked_wrist_path_static_pass"
                if passed
                else "canonical_elbow_locked_wrist_path_static_reject"
            ),
            "proof_class": (
                "cpu_fp64_current_workcell_elbow_locked_static_action_freeze"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "passed": passed,
            "elbow_lock": {
                "joint_name": "elbow_flex",
                "joint_index": locked_index,
                "model_value_radians": float(model_seed[locked_index]),
                "physical_value_degrees": float(follower[0, locked_index]),
                "selected_actions_exactly_constant": elbow_exact,
            },
            "dynamic_replay_executed": False,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "authority": contract["authority"],
            "claim_boundary": contract["claim_boundary"],
        }
    )
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalElbowLockedStaticError",
    "enumerate_and_freeze",
]
