"""Versioned, non-calibrating rubber-tip contact sensitivity variants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco

from .paths import DEFAULT_RUBBER_TIP_CONTACT_PRIOR


SCHEMA_VERSION = "sim2claw.rubber_tip_contact_prior.v1"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SimulatorVariant:
    contract_path: Path
    contract_sha256: str
    task_id: str
    task_contract_sha256: str
    variant_id: str
    variant_sha256: str
    payload: dict[str, Any]
    collision_approximation: dict[str, Any]

    @property
    def rubber_tip_enabled(self) -> bool:
        return bool(self.payload["rubber_tip_enabled"])


def load_contact_prior_contract(
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported rubber-tip contact prior contract")
    if not contract.get("frozen_before_evaluation"):
        raise ValueError("contact prior contract must be frozen before evaluation")
    order = contract.get("evaluation_order")
    variants = contract.get("variants")
    if not isinstance(order, list) or not order or not isinstance(variants, dict):
        raise ValueError("contact prior contract must declare ordered variants")
    if order[0] != "nominal_uncalibrated" or set(order) != set(variants):
        raise ValueError("contact prior evaluation order must cover every variant once")
    nominal = variants["nominal_uncalibrated"]
    if nominal.get("rubber_tip_enabled") is not False:
        raise ValueError("nominal simulator variant must remain unchanged")
    fixed = contract.get("fixed_evaluation", {})
    if fixed.get("held_out_seeds") != [9101] or fixed.get("repetitions_per_variant") != 1:
        raise ValueError("rubber-tip benchmark is frozen to one held-out seed per variant")
    immutable_fields = (
        "policy_weights_mutable",
        "observations_mutable",
        "actions_mutable",
        "evaluator_thresholds_mutable",
    )
    if any(fixed.get(field) is not False for field in immutable_fields):
        raise ValueError("policy, observation, action, and evaluator contracts are immutable")
    if fixed.get("training_rows_from_evaluator") != 0:
        raise ValueError("evaluator rows cannot enter training")
    for variant_id in order[1:]:
        variant = variants[variant_id]
        _validate_rubber_variant(variant_id, variant)
    return contract


def _validate_rubber_variant(variant_id: str, variant: dict[str, Any]) -> None:
    if variant.get("rubber_tip_enabled") is not True:
        raise ValueError(f"{variant_id} must enable the rubber-tip prior")
    for field in (
        "effective_wrap_thickness_m",
        "effective_outer_radius_m",
        "distal_coverage_length_m",
        "added_mass_per_finger_kg",
    ):
        value = variant.get(field)
        if not isinstance(value, (int, float)) or float(value) <= 0.0:
            raise ValueError(f"{variant_id}.{field} must be positive")
    friction = variant.get("contact_friction", {})
    if any(
        float(friction.get(field, 0.0)) <= 0.0
        for field in ("sliding_dimensionless", "torsional_m", "rolling_m")
    ):
        raise ValueError(f"{variant_id} must define three positive friction dimensions")
    softness = variant.get("contact_softness", {})
    solimp = softness.get("solimp")
    if (
        float(softness.get("solref_time_constant_s", 0.0)) <= 0.0
        or float(softness.get("solref_damping_ratio", 0.0)) <= 0.0
        or not isinstance(solimp, list)
        or len(solimp) != 5
    ):
        raise ValueError(f"{variant_id} must define MuJoCo contact softness")
    if "not_measured" not in str(variant.get("parameter_provenance", "")):
        raise ValueError(f"{variant_id} must remain explicitly unmeasured")


def contact_prior_contract_sha256(
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> str:
    return _canonical_sha256(load_contact_prior_contract(path))


def load_simulator_variant(
    variant_id: str,
    *,
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> SimulatorVariant:
    contract = load_contact_prior_contract(path)
    if variant_id not in contract["variants"]:
        raise ValueError(f"unknown contact prior variant: {variant_id}")
    identity_payload = {
        "schema_version": contract["schema_version"],
        "analysis_id": contract["analysis_id"],
        "task_id": contract["task_id"],
        "task_contract_sha256": contract["task_contract_sha256"],
        "collision_approximation": contract["collision_approximation"],
        "variant_id": variant_id,
        "variant": contract["variants"][variant_id],
    }
    return SimulatorVariant(
        contract_path=path,
        contract_sha256=_canonical_sha256(contract),
        task_id=str(contract["task_id"]),
        task_contract_sha256=str(contract["task_contract_sha256"]),
        variant_id=variant_id,
        variant_sha256=_canonical_sha256(identity_payload),
        payload=contract["variants"][variant_id],
        collision_approximation=contract["collision_approximation"],
    )


def apply_contact_variant(
    spec: mujoco.MjSpec,
    variant: SimulatorVariant,
) -> dict[str, Any]:
    """Apply one additive collision prior; nominal is a strict no-op."""

    if not variant.rubber_tip_enabled:
        return {
            "variant_id": variant.variant_id,
            "variant_sha256": variant.variant_sha256,
            "nominal_unchanged": True,
            "added_geoms": [],
        }

    arm = str(variant.collision_approximation["task_arm"])
    thickness = float(variant.payload["effective_wrap_thickness_m"])
    radius = float(variant.payload["effective_outer_radius_m"])
    coverage = float(variant.payload["distal_coverage_length_m"])
    friction = variant.payload["contact_friction"]
    softness = variant.payload["contact_softness"]
    added_names: list[str] = []
    for finger in variant.collision_approximation["fingers"]:
        anchor_name = f"{arm}_{finger['anchor_geom_suffix']}"
        anchor = spec.geom(anchor_name)
        if anchor is None or anchor.type != mujoco.mjtGeom.mjGEOM_BOX:
            raise ValueError(f"rubber-tip anchor geom is missing or not a box: {anchor_name}")
        size = [float(value) for value in anchor.size]
        size[int(finger["normal_axis_index"])] += thickness
        size[int(finger["width_axis_index"])] = radius
        size[int(finger["coverage_axis_index"])] = coverage / 2.0
        name = f"{arm}_rubber_tip_{finger['finger_id']}_{variant.variant_id}"
        anchor.parent.add_geom(
            name=name,
            type=mujoco.mjtGeom.mjGEOM_BOX,
            pos=[float(value) for value in anchor.pos],
            quat=[float(value) for value in anchor.quat],
            size=size,
            contype=1,
            conaffinity=1,
            condim=6,
            priority=2,
            friction=[
                float(friction["sliding_dimensionless"]),
                float(friction["torsional_m"]),
                float(friction["rolling_m"]),
            ],
            solref=[
                float(softness["solref_time_constant_s"]),
                float(softness["solref_damping_ratio"]),
            ],
            solimp=[float(value) for value in softness["solimp"]],
            mass=float(variant.payload["added_mass_per_finger_kg"]),
            rgba=[0.08, 0.08, 0.08, 1.0],
            group=3,
        )
        added_names.append(name)
    return {
        "variant_id": variant.variant_id,
        "variant_sha256": variant.variant_sha256,
        "nominal_unchanged": False,
        "added_geoms": added_names,
        "parameter_provenance": variant.payload["parameter_provenance"],
    }
