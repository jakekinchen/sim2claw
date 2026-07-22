"""Fail-closed Phase 2 identity and authority oracles used by Phase 1 CI."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import SailContractError, assert_split_integrity


REQUIRED_WORKCELL_IDENTITIES = (
    "robot_serials",
    "servo_ids",
    "firmware",
    "calibration_sha256",
    "fingertip_profile",
    "board_identity",
    "board_dimensions",
    "board_to_base_transform",
    "camera_identities",
    "camera_intrinsics",
    "camera_extrinsics",
    "table_fixture_geometry",
    "joint_mapping",
)


def classify_workcell_identity(
    identities: Mapping[str, Any], *, claimed_same_as_retired: bool
) -> str:
    complete = all(
        identities.get(name) is not None
        and identities.get(name) != ""
        and identities.get(name) != "unknown"
        for name in REQUIRED_WORKCELL_IDENTITIES
    )
    unchanged = all(
        not isinstance(identities.get(name), Mapping)
        or identities[name].get("matches_retired") is True
        for name in REQUIRED_WORKCELL_IDENTITIES
    )
    if claimed_same_as_retired and complete and unchanged:
        return "same_workcell"
    return "new_related_workcell"


def compile_hardware_preflight(
    *,
    authority: Mapping[str, bool],
    identities: Mapping[str, Any],
    policy_camera_ids: Sequence[str],
    evaluator_only_camera_ids: Sequence[str],
    training_ids: Sequence[str] = (),
    hardware_evaluation_ids: Sequence[str] = (),
) -> dict[str, Any]:
    assert_split_integrity(
        training_ids=training_ids,
        hardware_evaluation_ids=hardware_evaluation_ids,
    )
    policy_set = set(policy_camera_ids)
    evaluator_set = set(evaluator_only_camera_ids)
    if policy_set & evaluator_set:
        raise SailContractError("evaluator-only camera entered policy observations")
    workcell_class = classify_workcell_identity(
        identities, claimed_same_as_retired=bool(authority.get("claim_same_workcell"))
    )
    capture = bool(authority.get("capture")) and bool(authority.get("owner"))
    motion = (
        bool(authority.get("motion"))
        and bool(authority.get("owner"))
        and bool(authority.get("gateway"))
    )
    return {
        "workcell_class": workcell_class,
        "capture_allowed": capture,
        "motion_allowed": motion,
        "policy_camera_ids": sorted(policy_set),
        "evaluator_only_camera_ids": sorted(evaluator_set),
        "physical_authority": capture or motion,
    }
