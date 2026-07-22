"""Versioned, non-calibrating rubber-tip contact sensitivity variants."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .paths import DEFAULT_RUBBER_TIP_CONTACT_PRIOR


SCHEMA_VERSION = "sim2claw.rubber_tip_contact_prior.v1"
EXPECTED_CONTRACT_SHA256 = (
    "e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499"
)
VARIANT_ORDER = (
    "nominal_uncalibrated",
    "rubber_tip_low",
    "rubber_tip_nominal_prior",
    "rubber_tip_high",
)
TOP_LEVEL_KEYS = {
    "schema_version",
    "analysis_id",
    "task_id",
    "task_contract_sha256",
    "frozen_before_evaluation",
    "proof_class",
    "purpose",
    "policy",
    "reported_modification",
    "collision_approximation",
    "evaluation_order",
    "variants",
    "fixed_evaluation",
    "limitations",
}
RUBBER_VARIANT_KEYS = {
    "label",
    "rubber_tip_enabled",
    "evidence_class",
    "effective_wrap_thickness_m",
    "effective_box_half_width_m",
    "distal_coverage_length_m",
    "contact_friction",
    "contact_softness",
    "parameter_provenance",
}
DYNAMICS_ARRAY_FIELDS = (
    "body_parentid",
    "body_weldid",
    "body_mocapid",
    "body_jntnum",
    "body_jntadr",
    "body_dofnum",
    "body_dofadr",
    "body_geomnum",
    "body_geomadr",
    "body_pos",
    "body_quat",
    "body_ipos",
    "body_iquat",
    "body_mass",
    "body_subtreemass",
    "body_inertia",
    "jnt_type",
    "jnt_qposadr",
    "jnt_dofadr",
    "jnt_bodyid",
    "jnt_group",
    "jnt_limited",
    "jnt_solref",
    "jnt_solimp",
    "jnt_pos",
    "jnt_axis",
    "jnt_stiffness",
    "jnt_range",
    "jnt_margin",
    "dof_bodyid",
    "dof_jntid",
    "dof_parentid",
    "dof_Madr",
    "dof_simplenum",
    "dof_solref",
    "dof_solimp",
    "dof_frictionloss",
    "dof_armature",
    "dof_damping",
    "dof_invweight0",
    "dof_M0",
    "geom_type",
    "geom_contype",
    "geom_conaffinity",
    "geom_condim",
    "geom_bodyid",
    "geom_priority",
    "geom_solmix",
    "geom_solref",
    "geom_solimp",
    "geom_size",
    "geom_pos",
    "geom_quat",
    "geom_friction",
    "geom_margin",
    "geom_gap",
    "actuator_trntype",
    "actuator_dyntype",
    "actuator_gaintype",
    "actuator_biastype",
    "actuator_trnid",
    "actuator_actadr",
    "actuator_actnum",
    "actuator_group",
    "actuator_ctrllimited",
    "actuator_forcelimited",
    "actuator_dynprm",
    "actuator_gainprm",
    "actuator_biasprm",
    "actuator_ctrlrange",
    "actuator_forcerange",
    "actuator_gear",
    "qpos0",
    "qpos_spring",
)
INERTIAL_CONTROL_ARRAY_FIELDS = (
    "body_parentid",
    "body_weldid",
    "body_mocapid",
    "body_jntnum",
    "body_jntadr",
    "body_dofnum",
    "body_dofadr",
    "body_pos",
    "body_quat",
    "body_ipos",
    "body_iquat",
    "body_mass",
    "body_subtreemass",
    "body_inertia",
    "jnt_type",
    "jnt_qposadr",
    "jnt_dofadr",
    "jnt_bodyid",
    "jnt_group",
    "jnt_limited",
    "jnt_solref",
    "jnt_solimp",
    "jnt_pos",
    "jnt_axis",
    "jnt_stiffness",
    "jnt_range",
    "jnt_margin",
    "dof_bodyid",
    "dof_jntid",
    "dof_parentid",
    "dof_Madr",
    "dof_simplenum",
    "dof_solref",
    "dof_solimp",
    "dof_frictionloss",
    "dof_armature",
    "dof_damping",
    "dof_invweight0",
    "dof_M0",
    "actuator_trntype",
    "actuator_dyntype",
    "actuator_gaintype",
    "actuator_biastype",
    "actuator_trnid",
    "actuator_actadr",
    "actuator_actnum",
    "actuator_group",
    "actuator_ctrllimited",
    "actuator_forcelimited",
    "actuator_dynprm",
    "actuator_gainprm",
    "actuator_biasprm",
    "actuator_ctrlrange",
    "actuator_forcerange",
    "actuator_gear",
    "qpos0",
    "qpos_spring",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_exact_keys(value: Any, keys: set[str], context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ValueError(f"{context} keys drifted; missing={missing}, extra={extra}")
    return value


def _require_string(value: Any, context: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _require_bool(value: Any, expected: bool, context: str) -> None:
    if type(value) is not bool or value is not expected:
        raise ValueError(f"{context} must be exactly {expected}")


def _require_number(value: Any, context: str, *, positive: bool = True) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{context} must be a finite number, not bool or string")
    number = float(value)
    if positive and number <= 0.0:
        raise ValueError(f"{context} must be positive")
    return number


def _require_equal(value: Any, expected: Any, context: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise ValueError(f"{context} drifted from the frozen value")


@dataclass(frozen=True)
class ContactPriorSnapshot:
    source_path: Path
    sha256: str
    canonical_json: bytes

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class SimulatorVariant:
    contract_path: Path
    contract_sha256: str
    task_id: str
    task_contract_sha256: str
    accepted_checkpoint_sha256: str
    variant_id: str
    variant_sha256: str
    payload: dict[str, Any]
    collision_approximation: dict[str, Any]

    @property
    def rubber_tip_enabled(self) -> bool:
        return bool(self.payload["rubber_tip_enabled"])


def _validate_contract(contract: Any) -> dict[str, Any]:
    contract = _require_exact_keys(contract, TOP_LEVEL_KEYS, "contact prior")
    _require_equal(contract["schema_version"], SCHEMA_VERSION, "schema_version")
    _require_equal(
        contract["analysis_id"],
        "rubber_tip_contact_sensitivity_v1",
        "analysis_id",
    )
    _require_equal(contract["task_id"], "chess_rook_lift_v1", "task_id")
    _require_equal(
        contract["task_contract_sha256"],
        "4c3c4f95a9a7d72acebaed993091c576baf125f9ed0454a960dfd2d5906c518f",
        "task_contract_sha256",
    )
    _require_bool(contract["frozen_before_evaluation"], True, "frozen_before_evaluation")
    _require_equal(
        contract["proof_class"],
        "simulation_contact_prior_sensitivity",
        "proof_class",
    )
    _require_string(contract["purpose"], "purpose")

    policy = _require_exact_keys(
        contract["policy"],
        {
            "type",
            "checkpoint_schema_version",
            "accepted_checkpoint_sha256",
            "checkpoint_location_authority",
            "weights_mutable",
        },
        "policy",
    )
    _require_equal(policy["type"], "ACT", "policy.type")
    _require_equal(
        policy["checkpoint_schema_version"],
        "sim2claw.act_checkpoint.v1",
        "policy.checkpoint_schema_version",
    )
    _require_equal(
        policy["accepted_checkpoint_sha256"],
        "f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc",
        "policy.accepted_checkpoint_sha256",
    )
    _require_equal(
        policy["checkpoint_location_authority"],
        "existing_same_repository_ignored_output_read_only",
        "policy.checkpoint_location_authority",
    )
    _require_bool(policy["weights_mutable"], False, "policy.weights_mutable")

    reported = _require_exact_keys(
        contract["reported_modification"],
        {
            "material_description",
            "wrap_count_per_fingertip",
            "applies_to",
            "physical_measurements_available",
        },
        "reported_modification",
    )
    material = _require_exact_keys(
        reported["material_description"], {"value", "provenance"}, "material_description"
    )
    _require_equal(material["value"], "rubber_band", "material_description.value")
    _require_equal(
        material["provenance"],
        "owner_reported_unmeasured",
        "material_description.provenance",
    )
    wraps = _require_exact_keys(
        reported["wrap_count_per_fingertip"],
        {"range", "unit", "provenance"},
        "wrap_count_per_fingertip",
    )
    _require_equal(wraps["range"], [4, 5], "wrap_count_per_fingertip.range")
    _require_equal(wraps["unit"], "wraps", "wrap_count_per_fingertip.unit")
    _require_equal(
        wraps["provenance"],
        "owner_reported_unmeasured",
        "wrap_count_per_fingertip.provenance",
    )
    applies = _require_exact_keys(
        reported["applies_to"], {"value", "provenance"}, "applies_to"
    )
    _require_equal(
        applies["value"],
        "each_fixed_and_moving_gripper_fingertip",
        "applies_to.value",
    )
    _require_equal(
        applies["provenance"],
        "owner_reported_unmeasured",
        "applies_to.provenance",
    )
    _require_bool(
        reported["physical_measurements_available"],
        False,
        "physical_measurements_available",
    )

    collision = _require_exact_keys(
        contract["collision_approximation"],
        {
            "type",
            "reason",
            "task_arm",
            "fingers",
            "geometry_provenance",
            "mass_effect_mode",
            "physical_mass_acknowledgement",
        },
        "collision_approximation",
    )
    _require_equal(collision["type"], "added_distal_box_sleeve", "collision.type")
    _require_string(collision["reason"], "collision.reason")
    _require_equal(collision["task_arm"], "left", "collision.task_arm")
    _require_equal(
        collision["geometry_provenance"],
        "estimated_collision_prior_not_measured_geometry",
        "collision.geometry_provenance",
    )
    _require_equal(
        collision["mass_effect_mode"],
        "excluded_as_negligible_unmeasured_owner_assessment",
        "collision.mass_effect_mode",
    )
    _require_equal(
        collision["physical_mass_acknowledgement"],
        "nonzero_unmeasured_intentionally_approximated_as_zero_for_dynamics",
        "collision.physical_mass_acknowledgement",
    )
    if type(collision["fingers"]) is not list or len(collision["fingers"]) != 2:
        raise ValueError("collision.fingers must contain exactly fixed then moving")
    expected_fingers = (
        ("fixed", "fixed_jaw_box5", 2, 1, 0),
        ("moving", "moving_jaw_box3", 1, 2, 0),
    )
    for index, expected in enumerate(expected_fingers):
        finger = _require_exact_keys(
            collision["fingers"][index],
            {
                "finger_id",
                "anchor_geom_suffix",
                "coverage_axis_index",
                "width_axis_index",
                "normal_axis_index",
            },
            f"collision.fingers[{index}]",
        )
        for key, expected_value in zip(
            (
                "finger_id",
                "anchor_geom_suffix",
                "coverage_axis_index",
                "width_axis_index",
                "normal_axis_index",
            ),
            expected,
            strict=True,
        ):
            _require_equal(finger[key], expected_value, f"collision.fingers[{index}].{key}")

    if type(contract["evaluation_order"]) is not list:
        raise ValueError("evaluation_order must be a list")
    _require_equal(contract["evaluation_order"], list(VARIANT_ORDER), "evaluation_order")
    if len(set(contract["evaluation_order"])) != len(VARIANT_ORDER):
        raise ValueError("evaluation_order must contain four unique variants")
    variants = _require_exact_keys(contract["variants"], set(VARIANT_ORDER), "variants")
    if tuple(variants) != VARIANT_ORDER:
        raise ValueError("variants must be declared in the frozen evaluation order")
    nominal = _require_exact_keys(
        variants["nominal_uncalibrated"],
        {"label", "rubber_tip_enabled", "evidence_class", "parameter_provenance"},
        "variants.nominal_uncalibrated",
    )
    _require_equal(
        nominal["label"],
        "Current nominal uncalibrated simulator",
        "nominal.label",
    )
    _require_bool(nominal["rubber_tip_enabled"], False, "nominal.rubber_tip_enabled")
    _require_equal(
        nominal["evidence_class"],
        "nominal_uncalibrated_simulation",
        "nominal.evidence_class",
    )
    _require_equal(
        nominal["parameter_provenance"],
        "existing_frozen_task_simulator_unchanged",
        "nominal.parameter_provenance",
    )
    expected_variant_metadata = {
        "rubber_tip_low": (
            "Rubber-tip low-effect prior",
            "estimated_low_effect_prior_not_measured",
        ),
        "rubber_tip_nominal_prior": (
            "Rubber-tip nominal prior",
            "estimated_midpoint_prior_not_measured",
        ),
        "rubber_tip_high": (
            "Rubber-tip high-effect prior",
            "estimated_high_effect_prior_not_measured",
        ),
    }
    for variant_id in VARIANT_ORDER[1:]:
        _validate_rubber_variant(
            variant_id,
            variants[variant_id],
            expected_variant_metadata[variant_id],
        )

    fixed = _require_exact_keys(
        contract["fixed_evaluation"],
        {
            "held_out_seeds",
            "repetitions_per_variant",
            "policy_weights_mutable",
            "observations_mutable",
            "actions_mutable",
            "evaluator_thresholds_mutable",
            "training_rows_from_evaluator",
        },
        "fixed_evaluation",
    )
    _require_equal(fixed["held_out_seeds"], [9101], "fixed_evaluation.held_out_seeds")
    _require_equal(
        fixed["repetitions_per_variant"], 1, "fixed_evaluation.repetitions_per_variant"
    )
    for field in (
        "policy_weights_mutable",
        "observations_mutable",
        "actions_mutable",
        "evaluator_thresholds_mutable",
    ):
        _require_bool(fixed[field], False, f"fixed_evaluation.{field}")
    _require_equal(
        fixed["training_rows_from_evaluator"],
        0,
        "fixed_evaluation.training_rows_from_evaluator",
    )
    limitations = contract["limitations"]
    if (
        type(limitations) is not list
        or len(limitations) != 3
        or any(type(value) is not str or not value for value in limitations)
    ):
        raise ValueError("limitations must contain exactly three non-empty strings")
    return contract


def _validate_rubber_variant(
    variant_id: str,
    value: Any,
    expected_metadata: tuple[str, str],
) -> None:
    variant = _require_exact_keys(value, RUBBER_VARIANT_KEYS, f"variants.{variant_id}")
    _require_equal(variant["label"], expected_metadata[0], f"{variant_id}.label")
    _require_bool(variant["rubber_tip_enabled"], True, f"{variant_id}.rubber_tip_enabled")
    _require_equal(
        variant["evidence_class"],
        "rubber_tip_prior_sensitivity_simulation",
        f"{variant_id}.evidence_class",
    )
    for field in (
        "effective_wrap_thickness_m",
        "effective_box_half_width_m",
        "distal_coverage_length_m",
    ):
        _require_number(variant[field], f"{variant_id}.{field}")
    friction = _require_exact_keys(
        variant["contact_friction"],
        {"sliding_dimensionless", "torsional_m", "rolling_m"},
        f"{variant_id}.contact_friction",
    )
    for field in ("sliding_dimensionless", "torsional_m", "rolling_m"):
        _require_number(friction[field], f"{variant_id}.contact_friction.{field}")
    softness = _require_exact_keys(
        variant["contact_softness"],
        {"solref_time_constant_s", "solref_damping_ratio", "solimp"},
        f"{variant_id}.contact_softness",
    )
    _require_number(
        softness["solref_time_constant_s"],
        f"{variant_id}.contact_softness.solref_time_constant_s",
    )
    _require_number(
        softness["solref_damping_ratio"],
        f"{variant_id}.contact_softness.solref_damping_ratio",
    )
    if type(softness["solimp"]) is not list or len(softness["solimp"]) != 5:
        raise ValueError(f"{variant_id}.contact_softness.solimp must have five values")
    for index, item in enumerate(softness["solimp"]):
        _require_number(item, f"{variant_id}.contact_softness.solimp[{index}]")
    _require_equal(
        variant["parameter_provenance"],
        expected_metadata[1],
        f"{variant_id}.parameter_provenance",
    )


def read_contact_prior_snapshot(
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> ContactPriorSnapshot:
    raw = path.read_bytes()
    try:
        contract = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("contact prior contract is not valid UTF-8 JSON") from error
    validated = _validate_contract(contract)
    canonical = _canonical_bytes(validated)
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != EXPECTED_CONTRACT_SHA256:
        raise ValueError("contact prior contract digest drifted from the reviewed contract")
    return ContactPriorSnapshot(path, digest, canonical)


def load_contact_prior_contract(
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> dict[str, Any]:
    return read_contact_prior_snapshot(path).payload()


def contact_prior_contract_sha256(
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> str:
    return read_contact_prior_snapshot(path).sha256


def load_simulator_variant(
    variant_id: str,
    *,
    path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
    contract_snapshot: ContactPriorSnapshot | None = None,
) -> SimulatorVariant:
    snapshot = contract_snapshot or read_contact_prior_snapshot(path)
    contract = snapshot.payload()
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
        contract_path=snapshot.source_path,
        contract_sha256=snapshot.sha256,
        task_id=str(contract["task_id"]),
        task_contract_sha256=str(contract["task_contract_sha256"]),
        accepted_checkpoint_sha256=str(
            contract["policy"]["accepted_checkpoint_sha256"]
        ),
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
            "bindings": [],
        }

    arm = str(variant.collision_approximation["task_arm"])
    thickness = float(variant.payload["effective_wrap_thickness_m"])
    half_width = float(variant.payload["effective_box_half_width_m"])
    coverage = float(variant.payload["distal_coverage_length_m"])
    segment_count = int(variant.payload.get("wrap_segment_count", 1))
    segment_fill_fraction = float(
        variant.payload.get("wrap_segment_fill_fraction", 1.0)
    )
    ridge_count = int(variant.payload.get("wrap_ridge_count", 0))
    ridge_height = float(variant.payload.get("wrap_ridge_height_m", 0.0))
    ridge_fill_fraction = float(
        variant.payload.get("wrap_ridge_fill_fraction", 0.5)
    )
    if not 1 <= segment_count <= 8:
        raise ValueError("rubber-tip wrap segment count must be within [1, 8]")
    if not 0.2 <= segment_fill_fraction <= 1.0:
        raise ValueError(
            "rubber-tip wrap segment fill fraction must be within [0.2, 1.0]"
        )
    if not 0 <= ridge_count <= 8:
        raise ValueError("rubber-tip wrap ridge count must be within [0, 8]")
    if not 0.0 <= ridge_height <= 0.005:
        raise ValueError("rubber-tip wrap ridge height must be within [0, 0.005] m")
    if ridge_count and ridge_height <= 0.0:
        raise ValueError("rubber-tip wrap ridges require a positive ridge height")
    if not 0.2 <= ridge_fill_fraction <= 1.0:
        raise ValueError(
            "rubber-tip wrap ridge fill fraction must be within [0.2, 1.0]"
        )
    if ridge_count and segment_count != 1:
        raise ValueError(
            "raised rubber-tip ridges require one continuous base sleeve"
        )
    friction = variant.payload["contact_friction"]
    softness = variant.payload["contact_softness"]
    normal_compliance = variant.payload.get("normal_compliance", {})
    compliant = bool(normal_compliance.get("enabled", False))
    compliance_travel = float(normal_compliance.get("travel_m", 0.0))
    compliance_stiffness = float(normal_compliance.get("stiffness_n_per_m", 0.0))
    compliance_damping = float(normal_compliance.get("damping_n_s_per_m", 0.0))
    compliance_mass_per_finger = float(
        normal_compliance.get("modeled_mass_per_finger_kg", 0.0)
    )
    if compliant:
        if not 0.00025 <= compliance_travel <= 0.005:
            raise ValueError(
                "rubber-tip normal-compliance travel must be within [0.00025, 0.005] m"
            )
        if not 50.0 <= compliance_stiffness <= 20_000.0:
            raise ValueError(
                "rubber-tip normal-compliance stiffness must be within [50, 20000] N/m"
            )
        if not 0.01 <= compliance_damping <= 20.0:
            raise ValueError(
                "rubber-tip normal-compliance damping must be within [0.01, 20] N s/m"
            )
        if not 0.0001 <= compliance_mass_per_finger <= 0.02:
            raise ValueError(
                "rubber-tip modeled mass per finger must be within [0.0001, 0.02] kg"
            )
    added_geoms: list[str] = []
    added_bodies: list[str] = []
    added_joints: list[str] = []
    bindings: list[dict[str, Any]] = []
    for finger in variant.collision_approximation["fingers"]:
        anchor_name = f"{arm}_{finger['anchor_geom_suffix']}"
        anchor = spec.geom(anchor_name)
        if anchor is None or anchor.type != mujoco.mjtGeom.mjGEOM_BOX:
            raise ValueError(f"rubber-tip anchor geom is missing or not a box: {anchor_name}")
        size = [float(value) for value in anchor.size]
        size[int(finger["normal_axis_index"])] += thickness
        size[int(finger["width_axis_index"])] = half_width
        coverage_axis = int(finger["coverage_axis_index"])
        segment_pitch = coverage / segment_count
        size[coverage_axis] = segment_pitch * segment_fill_fraction / 2.0
        for segment_index in range(segment_count):
            geom_name = (
                f"{arm}_rubber_tip_{finger['finger_id']}_{variant.variant_id}_geom"
                if segment_count == 1
                else (
                    f"{arm}_rubber_tip_{finger['finger_id']}_{variant.variant_id}"
                    f"_segment_{segment_index + 1:02d}_geom"
                )
            )
            position = [float(value) for value in anchor.pos]
            position[coverage_axis] += (
                -coverage / 2.0
                + (segment_index + 0.5) * segment_pitch
            )
            geom_parent = anchor.parent
            geom_position = position
            geom_quat = [float(value) for value in anchor.quat]
            modeled_mass = 0.0
            body_name: str | None = None
            joint_name: str | None = None
            if compliant:
                body_name = geom_name.removesuffix("_geom") + "_body"
                joint_name = geom_name.removesuffix("_geom") + "_normal_joint"
                geom_parent = anchor.parent.add_body(
                    name=body_name,
                    pos=position,
                    quat=[float(value) for value in anchor.quat],
                )
                axis = [0.0, 0.0, 0.0]
                axis[int(finger["normal_axis_index"])] = 1.0
                geom_parent.add_joint(
                    name=joint_name,
                    type=mujoco.mjtJoint.mjJNT_SLIDE,
                    axis=axis,
                    limited=True,
                    range=[-compliance_travel, compliance_travel],
                    stiffness=compliance_stiffness,
                    damping=compliance_damping,
                    springref=0.0,
                )
                geom_position = [0.0, 0.0, 0.0]
                geom_quat = [1.0, 0.0, 0.0, 0.0]
                modeled_mass = compliance_mass_per_finger / segment_count
                added_bodies.append(body_name)
                added_joints.append(joint_name)
            geom_parent.add_geom(
                name=geom_name,
                type=mujoco.mjtGeom.mjGEOM_BOX,
                pos=geom_position,
                quat=geom_quat,
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
                mass=modeled_mass,
                rgba=[0.08, 0.08, 0.08, 1.0],
                group=3,
            )
            added_geoms.append(geom_name)
            bindings.append(
                {
                    "finger_id": finger["finger_id"],
                    "anchor_geom": anchor_name,
                    "parent_body": geom_parent.name,
                    "anchor_parent_body": anchor.parent.name,
                    "added_geom": geom_name,
                    "added_body": body_name,
                    "added_joint": joint_name,
                    "segment_index": segment_index,
                    "segment_count": segment_count,
                    "segment_fill_fraction": segment_fill_fraction,
                    "contact_layer": "base_sleeve",
                    "modeled_added_mass_kg": modeled_mass,
                    "normal_compliance": (
                        {
                            "travel_m": compliance_travel,
                            "stiffness_n_per_m": compliance_stiffness,
                            "damping_n_s_per_m": compliance_damping,
                            "joint_axis_index": int(finger["normal_axis_index"]),
                        }
                        if compliant
                        else None
                    ),
                    "mass_effect_mode": variant.collision_approximation[
                        "mass_effect_mode"
                    ],
                }
            )
        if ridge_count:
            ridge_pitch = coverage / ridge_count
            ridge_size = [float(value) for value in anchor.size]
            ridge_size[int(finger["normal_axis_index"])] += (
                thickness + ridge_height
            )
            ridge_size[int(finger["width_axis_index"])] = half_width
            ridge_size[coverage_axis] = (
                ridge_pitch * ridge_fill_fraction / 2.0
            )
            for ridge_index in range(ridge_count):
                geom_name = (
                    f"{arm}_rubber_tip_{finger['finger_id']}_{variant.variant_id}"
                    f"_ridge_{ridge_index + 1:02d}_geom"
                )
                position = [float(value) for value in anchor.pos]
                position[coverage_axis] += (
                    -coverage / 2.0
                    + (ridge_index + 0.5) * ridge_pitch
                )
                anchor.parent.add_geom(
                    name=geom_name,
                    type=mujoco.mjtGeom.mjGEOM_BOX,
                    pos=position,
                    quat=[float(value) for value in anchor.quat],
                    size=ridge_size,
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
                    mass=0.0,
                    rgba=[0.45, 0.04, 0.04, 1.0],
                    group=3,
                )
                added_geoms.append(geom_name)
                bindings.append(
                    {
                        "finger_id": finger["finger_id"],
                        "anchor_geom": anchor_name,
                        "parent_body": anchor.parent.name,
                        "added_geom": geom_name,
                        "ridge_index": ridge_index,
                        "ridge_count": ridge_count,
                        "ridge_height_m": ridge_height,
                        "ridge_fill_fraction": ridge_fill_fraction,
                        "contact_layer": "raised_wrap_ridge",
                        "modeled_added_mass_kg": 0.0,
                        "mass_effect_mode": variant.collision_approximation[
                            "mass_effect_mode"
                        ],
                    }
                )
    return {
        "variant_id": variant.variant_id,
        "variant_sha256": variant.variant_sha256,
        "nominal_unchanged": False,
        "added_geoms": added_geoms,
        "added_bodies": added_bodies,
        "added_joints": added_joints,
        "bindings": bindings,
        "parameter_provenance": variant.payload["parameter_provenance"],
    }


def compiled_dynamics_sha256(model: mujoco.MjModel) -> str:
    digest = hashlib.sha256()
    option_values = (
        float(model.opt.timestep),
        int(model.opt.integrator),
        int(model.opt.cone),
        int(model.opt.iterations),
        int(model.opt.ls_iterations),
        float(model.opt.impratio),
    )
    digest.update(repr(option_values).encode("ascii"))
    for name in DYNAMICS_ARRAY_FIELDS:
        array = np.asarray(getattr(model, name))
        digest.update(name.encode("ascii"))
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(repr(array.shape).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def compiled_inertial_control_sha256(model: mujoco.MjModel) -> str:
    digest = hashlib.sha256()
    for name in INERTIAL_CONTROL_ARRAY_FIELDS:
        array = np.asarray(getattr(model, name))
        digest.update(name.encode("ascii"))
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(repr(array.shape).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def compiled_contact_identity(
    model: mujoco.MjModel,
    application: dict[str, Any] | None,
) -> dict[str, Any]:
    identity = {
        "compiled_dynamics_sha256": compiled_dynamics_sha256(model),
        "compiled_inertial_control_sha256": compiled_inertial_control_sha256(
            model
        ),
        "compiled_total_body_mass_kg": float(np.sum(model.body_mass)),
        "compiled_counts": {
            "nbody": int(model.nbody),
            "njnt": int(model.njnt),
            "nq": int(model.nq),
            "nv": int(model.nv),
            "nu": int(model.nu),
        },
        "modeled_added_mass_kg": 0.0,
        "mass_effect_mode": "excluded_as_negligible_unmeasured_owner_assessment",
        "bindings": [],
    }
    if application is None or application["nominal_unchanged"]:
        return identity
    compiled_bindings: list[dict[str, Any]] = []
    for binding in application["bindings"]:
        geom_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_GEOM, binding["added_geom"]
        )
        parent_body_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, binding["parent_body"]
        )
        if geom_id < 0 or parent_body_id < 0:
            raise ValueError("compiled rubber-tip geom or parent body identity is missing")
        compiled = {
            **binding,
            "added_geom_id": geom_id,
            "parent_body_id": parent_body_id,
            "compiled_geom_body_id": int(model.geom_bodyid[geom_id]),
            "parent_body_mass_kg": float(model.body_mass[parent_body_id]),
            "parent_body_subtree_mass_kg": float(model.body_subtreemass[parent_body_id]),
            "geom_size_half_extents_m": model.geom_size[geom_id].astype(float).tolist(),
            "geom_friction": model.geom_friction[geom_id].astype(float).tolist(),
            "geom_solref": model.geom_solref[geom_id].astype(float).tolist(),
            "geom_solimp": model.geom_solimp[geom_id].astype(float).tolist(),
            "geom_condim": int(model.geom_condim[geom_id]),
            "geom_priority": int(model.geom_priority[geom_id]),
        }
        compiled["identity_checks_passed"] = bool(
            compiled["compiled_geom_body_id"] == parent_body_id
            and binding["modeled_added_mass_kg"] == 0.0
        )
        compiled_bindings.append(compiled)
    identity["bindings"] = compiled_bindings
    identity["identity_checks_passed"] = all(
        binding["identity_checks_passed"] for binding in compiled_bindings
    )
    return identity
