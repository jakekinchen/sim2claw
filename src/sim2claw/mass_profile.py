from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import mujoco

from .paths import DEFAULT_SO101_MASS_PROFILE


MASS_PROFILE_SCHEMA = "sim2claw.so101_mass_profile.v1"
RIGID_BODY_NAMES = (
    "base",
    "shoulder",
    "upper_arm",
    "lower_arm",
    "wrist",
    "gripper",
    "moving_jaw_so101_v1",
)


def _positive_number(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return result


def load_so101_mass_profile(
    path: Path = DEFAULT_SO101_MASS_PROFILE,
) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    if profile.get("schema_version") != MASS_PROFILE_SCHEMA:
        raise ValueError(f"unsupported SO-101 mass profile schema: {path}")

    rigid_body_masses = profile.get("derived", {}).get("rigid_body_masses_g")
    if not isinstance(rigid_body_masses, dict):
        raise ValueError("derived.rigid_body_masses_g must be an object")
    if set(rigid_body_masses) != set(RIGID_BODY_NAMES):
        raise ValueError("derived.rigid_body_masses_g has the wrong body set")
    bare_total = sum(
        _positive_number(rigid_body_masses[name], field=f"rigid body {name}")
        for name in RIGID_BODY_NAMES
    )
    expected_bare_total = _positive_number(
        profile["derived"]["bare_arm_total_g"], field="bare arm total"
    )
    if not math.isclose(bare_total, expected_bare_total, abs_tol=1e-9):
        raise ValueError("bare arm total does not match rigid-body masses")
    printed_total = sum(float(row["mass_g"]) for row in profile["printed_groups"])
    if not math.isclose(
        printed_total,
        float(profile["derived"]["printed_parts_total_g"]),
        abs_tol=1e-9,
    ):
        raise ValueError("printed-parts total does not match measurement rows")
    servo = profile["specified_components"]["servo"]
    servos_total = float(servo["count"]) * float(servo["unit_mass_g"])
    if not math.isclose(
        servos_total, float(profile["derived"]["servos_total_g"]), abs_tol=1e-9
    ):
        raise ValueError("servo total does not match specified count and unit mass")
    hardware = profile["estimated_components"][
        "arm_fasteners_horns_and_passive_hardware"
    ]
    bare_component_total = printed_total + servos_total + float(hardware["mass_g"])
    if not math.isclose(bare_component_total, expected_bare_total, abs_tol=1e-9):
        raise ValueError("bare arm total does not match its component classes")

    payloads = profile.get("payloads")
    if not isinstance(payloads, dict) or not payloads:
        raise ValueError("payloads must be a non-empty object")
    for payload_id, payload in payloads.items():
        additions = payload.get("rigid_body_additions_g")
        if not isinstance(additions, dict):
            raise ValueError(f"payload {payload_id} additions must be an object")
        for body_name, mass_g in additions.items():
            if body_name not in {*RIGID_BODY_NAMES, "camera_mount"}:
                raise ValueError(f"payload {payload_id} has unknown body {body_name}")
            _positive_number(mass_g, field=f"payload {payload_id} body {body_name}")
        payload_total = sum(float(value) for value in additions.values())
        expected_payload_total = _positive_number(
            payload["total_g"], field=f"payload {payload_id} total"
        )
        if not math.isclose(payload_total, expected_payload_total, abs_tol=1e-9):
            raise ValueError(f"payload {payload_id} total does not match additions")
        camera_breakdown = payload.get("camera_mount_breakdown_g")
        if not isinstance(camera_breakdown, dict):
            raise ValueError(f"payload {payload_id} camera breakdown must be an object")
        if not math.isclose(
            sum(float(value) for value in camera_breakdown.values()),
            float(additions["camera_mount"]),
            abs_tol=1e-9,
        ):
            raise ValueError(f"payload {payload_id} camera breakdown does not match")

    left_payload_id = profile["scene_defaults"]["robot_payloads"]["left"]
    left_payload_total = float(payloads[left_payload_id]["total_g"])
    left_total = expected_bare_total + left_payload_total
    if not math.isclose(
        left_total,
        float(profile["derived"]["left_arm_with_payload_total_g"]),
        abs_tol=1e-9,
    ):
        raise ValueError("left-arm total does not match arm and payload totals")

    estimates = profile["estimated_components"]
    servo_tolerance = float(servo["unit_tolerance_g"])
    component_low = (
        printed_total
        + float(servo["count"]) * (float(servo["unit_mass_g"]) - servo_tolerance)
        + float(hardware["range_g"][0])
        + float(profile["specified_components"]["d405"]["unit_mass_g"])
        + float(estimates["custom_library_mount"]["range_g"][0])
        + float(estimates["d405_mount_fasteners"]["range_g"][0])
        + float(estimates["d405_usb_cable"]["range_g"][0])
    )
    component_high = (
        printed_total
        + float(servo["count"]) * (float(servo["unit_mass_g"]) + servo_tolerance)
        + float(hardware["range_g"][1])
        + float(profile["specified_components"]["d405"]["unit_mass_g"])
        + float(estimates["custom_library_mount"]["range_g"][1])
        + float(estimates["d405_mount_fasteners"]["range_g"][1])
        + float(estimates["d405_usb_cable"]["range_g"][1])
    )
    uncertainty = profile["uncertainty"]
    bounded_range = [component_low, component_high]
    if bounded_range != [
        float(value)
        for value in uncertainty["component_bounded_left_total_range_g"]
    ]:
        raise ValueError("component-bounded total range does not match source ranges")
    margin = _positive_number(
        uncertainty["additional_conservative_margin_g"],
        field="additional conservative margin",
    )
    reported_range = [component_low - margin, component_high + margin]
    if reported_range != [
        float(value) for value in uncertainty["reported_left_total_range_g"]
    ] or reported_range != [
        float(value) for value in profile["derived"]["left_arm_total_range_g"]
    ]:
        raise ValueError("reported total range does not match bounds and margin")
    return profile


def _scale_body_inertial(body: Any, mass_kg: float) -> None:
    if not body.explicitinertial or body.mass <= 0:
        raise ValueError(f"SO-101 body {body.name} has no scalable explicit inertial")
    scale = mass_kg / float(body.mass)
    body.mass = mass_kg
    body.fullinertia = [float(value) * scale for value in body.fullinertia]


def _configure_d405_payload(
    spec: mujoco.MjSpec,
    *,
    camera_mount_mass_kg: float,
    printed_mount_mass_kg: float,
    camera_dimensions_m: tuple[float, float, float],
) -> None:
    camera_mount = spec.body("camera_mount")
    if camera_mount is None:
        raise ValueError("SO-101 camera_mount body is missing")
    mount_geom = None
    for geom in camera_mount.geoms:
        if geom.meshname == "wrist_roll_follower_so101_camera_mount":
            mount_geom = geom
            break
    if mount_geom is None:
        raise ValueError("SO-101 camera mount mesh geom is missing")

    # The profile separates the printed support from the D405, its fasteners,
    # and the distal cable segment. The vendored mount mesh remains a shape
    # prior; the owner's custom STL is not copied here.
    mount_geom.mass = printed_mount_mass_kg
    camera_mass_kg = camera_mount_mass_kg - float(mount_geom.mass)
    if camera_mass_kg <= 0:
        raise ValueError("D405 payload must be heavier than its printed mount")
    camera_box = spec.geom("camera_box2")
    if camera_box is None:
        raise ValueError("SO-101 camera_box2 geom is missing")
    camera_box.mass = camera_mass_kg
    camera_box.size = [value / 2.0 for value in camera_dimensions_m]


def _remove_camera_payload_mass(spec: mujoco.MjSpec) -> None:
    camera_mount = spec.body("camera_mount")
    if camera_mount is None:
        raise ValueError("SO-101 camera_mount body is missing")
    for geom in camera_mount.geoms:
        geom.mass = 0.0


def apply_so101_mass_profile(
    spec: mujoco.MjSpec,
    profile: dict[str, Any],
    *,
    payload_id: str | None,
) -> None:
    """Apply measured masses while retaining CAD COM/inertia as explicit priors."""

    masses_g = profile["derived"]["rigid_body_masses_g"]
    additions_g: dict[str, float] = {}
    if payload_id is not None:
        try:
            additions_g = profile["payloads"][payload_id]["rigid_body_additions_g"]
        except KeyError as error:
            raise ValueError(f"unknown SO-101 payload: {payload_id}") from error

    for body_name in RIGID_BODY_NAMES:
        body = spec.body(body_name)
        if body is None:
            raise ValueError(f"SO-101 body is missing: {body_name}")
        mass_g = float(masses_g[body_name]) + float(additions_g.get(body_name, 0.0))
        _scale_body_inertial(body, mass_g / 1000.0)

    camera_mount_mass_g = additions_g.get("camera_mount")
    if camera_mount_mass_g is None:
        _remove_camera_payload_mass(spec)
    else:
        payload = profile["payloads"][payload_id]
        mount_mass_g = float(
            payload["camera_mount_breakdown_g"]["custom_library_mount"]
        )
        camera_dimensions_m = tuple(
            float(value) / 1000.0
            for value in profile["specified_components"]["d405"]["dimensions_mm"]
        )
        _configure_d405_payload(
            spec,
            camera_mount_mass_kg=float(camera_mount_mass_g) / 1000.0,
            printed_mount_mass_kg=mount_mass_g / 1000.0,
            camera_dimensions_m=camera_dimensions_m,
        )


def mass_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    payload_id = profile["scene_defaults"]["robot_payloads"]["left"]
    payload_total_g = float(profile["payloads"][payload_id]["total_g"])
    return {
        "profile_id": profile["profile_id"],
        "proof_class": profile["proof_class"],
        "bare_arm_total_g": float(profile["derived"]["bare_arm_total_g"]),
        "left_arm_with_payload_total_g": float(
            profile["derived"]["left_arm_with_payload_total_g"]
        ),
        "left_payload_id": payload_id,
        "left_payload_total_g": payload_total_g,
        "total_range_g": profile["derived"]["left_arm_total_range_g"],
        "com_and_inertia_status": profile["derived"]["com_and_inertia_status"],
    }
