"""Prospective proxy-only jaw collision challenger for canonical CC02 actions."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco

from . import canonical_seeded_action_temporal as _temporal
from .paths import REPO_ROOT


class CanonicalProxyContactTemporalError(RuntimeError):
    """The frozen proxy-contact challenger or one of its inputs changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalProxyContactTemporalError(
            "proxy-contact input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalProxyContactTemporalError(
            f"bound proxy-contact input changed: {path}"
        )
    return path


def _load_json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


class _ResolvedJson:
    """Resolve only the compact challenger contract for the frozen runner."""

    def __init__(
        self,
        *,
        compact: Mapping[str, Any],
        base: Mapping[str, Any],
    ) -> None:
        self._compact = compact
        self._base = base

    def loads(self, text: str, *args: Any, **kwargs: Any) -> Any:
        parsed = json.loads(text, *args, **kwargs)
        if (
            isinstance(parsed, dict)
            and parsed.get("schema_version")
            == "sim2claw.canonical_proxy_contact_temporal.v1"
        ):
            if parsed != self._compact:
                raise CanonicalProxyContactTemporalError(
                    "compact proxy-contact contract changed during replay"
                )
            resolved = copy.deepcopy(self._base)
            resolved["contract_id"] = parsed["contract_id"]
            resolved["status"] = parsed["status"]
            resolved["proof_class"] = parsed["proof_class"]
            resolved["output_directory"] = parsed["output_directory"]
            resolved["claim_boundary"] = parsed["claim_boundary"]
            return resolved
        return parsed


def replay(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Execute the frozen one-mechanism collision challenger exactly once."""

    if output_directory.exists():
        raise CanonicalProxyContactTemporalError(
            "immutable proxy-contact output already exists"
        )
    compact = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_temporal_contract",
        "temporal_receipt",
        "temporal_closeout",
        "contact_witness_receipt",
        "model_source",
        "temporal_implementation",
        "challenger_implementation",
        "mechanism_change",
        "unchanged_from_baseline",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        compact.get("schema_version")
        != "sim2claw.canonical_proxy_contact_temporal.v1"
        or set(compact) != expected_keys
        or not all(compact["unchanged_from_baseline"].values())
        or any(
            value
            for name, value in compact["authority"].items()
            if name != "dynamic_simulation"
        )
        or compact["authority"]["dynamic_simulation"] is not True
    ):
        raise CanonicalProxyContactTemporalError(
            "proxy-contact contract widened its authority or change surface"
        )
    for key in (
        "base_temporal_contract",
        "temporal_receipt",
        "temporal_closeout",
        "contact_witness_receipt",
        "model_source",
        "temporal_implementation",
        "challenger_implementation",
    ):
        _bound(compact[key])
    if output_directory != (REPO_ROOT / compact["output_directory"]).resolve():
        raise CanonicalProxyContactTemporalError(
            "proxy-contact output path changed"
        )
    temporal_receipt = _load_json(compact["temporal_receipt"])
    witness = _load_json(compact["contact_witness_receipt"])
    mechanism = compact["mechanism_change"]
    expected_meshes = {
        "left_wrist_roll_follower_so101_gripper_part0_v1",
        "left_moving_jaw_so101_gripper_part0_v1",
        "left_moving_jaw_so101_gripper_part1_v1",
    }
    if (
        temporal_receipt["status"]
        != "canonical_seeded_action_temporal_reject"
        or temporal_receipt["direction_counts"]
        != {"REAL_TO_SIM": 0, "SIM_TO_REAL": 0}
        or witness["status"] != "canonical_contact_witness_completed"
        or witness["all_rise_events_follow_jaw_contact"] is not True
        or mechanism
        != {
            "mechanism_id": "jaw_collision_mesh_to_named_proxy_only_v1",
            "disable_collision_meshes_on_bodies": [
                "left_gripper",
                "left_moving_jaw_so101_v1",
            ],
            "preserve_named_collision_primitives": True,
            "expected_disabled_mesh_assets": sorted(expected_meshes),
            "other_geometry_unchanged": True,
            "mass_friction_damping_timing_and_actions_unchanged": True,
            "calibrated_physical_geometry": False,
            "diagnostic_challenger": True,
        }
    ):
        raise CanonicalProxyContactTemporalError(
            "proxy-contact mechanism admission changed"
        )

    base = _load_json(compact["base_temporal_contract"])
    original_builder = _temporal._static._registered_current_model
    original_json = _temporal.json
    disabled: list[dict[str, Any]] = []

    def proxy_only_builder(
        rigid: Mapping[str, Any],
        timestep_s: float,
    ) -> tuple[mujoco.MjModel, list[int], set[int], set[int]]:
        model, addresses, robot_bodies, jaw_bodies = original_builder(
            rigid, timestep_s
        )
        seen: set[str] = set()
        for geom_id in range(model.ngeom):
            body_id = int(model.geom_bodyid[geom_id])
            if (
                body_id not in jaw_bodies
                or int(model.geom_type[geom_id])
                != int(mujoco.mjtGeom.mjGEOM_MESH)
                or not (
                    int(model.geom_contype[geom_id])
                    or int(model.geom_conaffinity[geom_id])
                )
            ):
                continue
            mesh_id = int(model.geom_dataid[geom_id])
            mesh_name = mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_MESH, mesh_id
            )
            body_name = mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id
            )
            if mesh_name is None or body_name is None:
                raise CanonicalProxyContactTemporalError(
                    "proxy-contact mesh identity is missing"
                )
            seen.add(mesh_name)
            disabled.append(
                {
                    "geom_id": geom_id,
                    "body_name": body_name,
                    "mesh_name": mesh_name,
                    "previous_contype": int(model.geom_contype[geom_id]),
                    "previous_conaffinity": int(
                        model.geom_conaffinity[geom_id]
                    ),
                }
            )
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        if seen != expected_meshes:
            raise CanonicalProxyContactTemporalError(
                "proxy-contact mesh set changed"
            )
        return model, addresses, robot_bodies, jaw_bodies

    try:
        _temporal._static._registered_current_model = proxy_only_builder
        _temporal.json = _ResolvedJson(compact=compact, base=base)
        receipt = _temporal.replay(contract_path, output_directory)
    finally:
        _temporal._static._registered_current_model = original_builder
        _temporal.json = original_json

    receipt["schema_version"] = (
        "sim2claw.canonical_proxy_contact_temporal_receipt.v1"
    )
    receipt["proof_class"] = (
        "cpu_fp64_exact_action_proxy_only_jaw_collision_"
        "direct_target_and_diagnostic_zoh_challenger"
    )
    receipt["baseline_temporal_receipt_sha256"] = compact[
        "temporal_receipt"
    ]["sha256"]
    receipt["contact_witness_receipt_sha256"] = compact[
        "contact_witness_receipt"
    ]["sha256"]
    receipt["mechanism_change"] = mechanism
    receipt["disabled_collision_meshes"] = disabled
    receipt["candidate_refit"] = False
    receipt["physical_motion"] = False
    receipt["physical_task_attempts"] = 0
    receipt["authority"] = compact["authority"]
    receipt["claim_boundary"] = compact["claim_boundary"]
    receipt_path = output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["CanonicalProxyContactTemporalError", "replay"]
