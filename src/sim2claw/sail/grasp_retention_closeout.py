"""Compile the receipt chain for the grasp-retention resolution campaign."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from ..paths import REPO_ROOT
from .grasp_retention_resolution import _load_json


CAMPAIGNS = (
    ("geometry_force", "grasp_retention_resolution_v1.json", "grasp-retention-resolution-v1"),
    ("force_contact", "grasp_retention_force_contact_v1.json", "grasp-retention-force-contact-v1"),
    ("contact_compliance", "grasp_retention_contact_compliance_v1.json", "grasp-retention-contact-compliance-v1"),
    ("current_torque", "grasp_retention_current_torque_v1.json", "grasp-retention-current-torque-v1"),
    ("load_hold", "grasp_retention_load_hold_v1.json", "grasp-retention-load-hold-v1"),
    ("calibrated_hold", "grasp_retention_calibrated_hold_v1.json", "grasp-retention-calibrated-hold-v1"),
    ("composite", "grasp_retention_composite_v1.json", "grasp-retention-composite-v1"),
    ("capsule_pad", "grasp_retention_capsule_pad_v1.json", "grasp-retention-capsule-pad-v1"),
)
SCHEMA = "sim2claw.sail_grasp_retention_closeout.v1"


class GraspRetentionCloseoutError(RuntimeError):
    """The grasp-retention closeout failed closed."""


def _candidate(receipt: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for row in receipt["candidates"]:
        if row["candidate_id"] == candidate_id:
            return row
    raise GraspRetentionCloseoutError(f"missing candidate: {candidate_id}")


def compile_grasp_retention_closeout(
    *, repository_root: Path = REPO_ROOT, output_path: Path | None = None
) -> dict[str, Any]:
    root = repository_root.resolve()
    rows: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {}
    expected_action = "402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6"
    for label, config_name, output_name in CAMPAIGNS:
        config_path = root / "configs" / "sail" / config_name
        receipt_path = (
            root / "outputs" / "sail" / output_name / "anchor-screen-receipt.json"
        )
        config = _load_json(config_path)
        receipt = _load_json(receipt_path)
        if receipt["contract_sha256"] != sha256_file(config_path):
            raise GraspRetentionCloseoutError(f"contract drift: {label}")
        if receipt["action_array_sha256"] != expected_action:
            raise GraspRetentionCloseoutError(f"action drift: {label}")
        if not receipt["all_actions_byte_identical"]:
            raise GraspRetentionCloseoutError(f"action mutation: {label}")
        if any(
            "action_identity_drift" in candidate["result"]["reasons"]
            for candidate in receipt["candidates"]
        ):
            raise GraspRetentionCloseoutError(
                f"episode-level action invariance failed: {label}"
            )
        if receipt["candidate_count"] != len(config["frozen_candidate_family"]):
            raise GraspRetentionCloseoutError(f"candidate inventory drift: {label}")
        loaded[label] = receipt
        rows.append(
            {
                "campaign": label,
                "config_path": str(config_path),
                "config_sha256": sha256_file(config_path),
                "receipt_path": str(receipt_path),
                "receipt_sha256": sha256_file(receipt_path),
                "candidate_count": receipt["candidate_count"],
                "anchor_pass_count": receipt["anchor_pass_count"],
                "leader": receipt["ranking"][0],
            }
        )

    if any(row["anchor_pass_count"] for row in rows):
        raise GraspRetentionCloseoutError(
            "an anchor pass exists and requires sentinel evaluation before closeout"
        )

    geometry = loaded["geometry_force"]
    force = loaded["force_contact"]
    calibrated = loaded["calibrated_hold"]
    composite = loaded["composite"]
    capsule = loaded["capsule_pad"]
    baseline = _candidate(geometry, "baseline")["result"]
    aligned = _candidate(geometry, "fixed_cover_040")["result"]
    force_frontier = _candidate(force, "condim4_force_125")["result"]
    calibrated_frontier = _candidate(calibrated, "condim6_dwell_000")["result"]
    transport_frontier = _candidate(composite, "condim4_cover_050")["result"]
    capsule_frontier = _candidate(capsule, "condim6_cover050_r004")["result"]

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": "terminal_negative_direct_pad_force_and_deformation_measurement_required",
        "proof_class": "retrospective_action_frozen_simulator_mechanism_resolution",
        "physical_authority": False,
        "simulator_promotion": False,
        "policy_training_opened": False,
        "action_array_sha256": expected_action,
        "all_actions_byte_identical": True,
        "campaigns": rows,
        "candidate_runs": sum(row["candidate_count"] for row in rows),
        "anchor_passes": 0,
        "causal_gains": {
            "fixed_rubber_alignment": {
                "baseline_contact_loss_source_index": baseline[
                    "contact_loss_source_index"
                ],
                "aligned_contact_loss_source_index": aligned[
                    "contact_loss_source_index"
                ],
                "delay_frames": (
                    aligned["contact_loss_source_index"]
                    - baseline["contact_loss_source_index"]
                ),
                "interpretation": "the fixed-side rubber was not on the C2 load-bearing surface",
            },
            "finite_force_contact_frontier": {
                "contact_loss_source_index": force_frontier[
                    "contact_loss_source_index"
                ],
                "loaded_aperture_bias_degrees": force_frontier[
                    "loaded_aperture_bias_degrees"
                ],
                "interpretation": "finite actuator force can match aperture but not task consequence",
            },
            "calibrated_hold_frontier": {
                "contact_loss_source_index": calibrated_frontier[
                    "contact_loss_source_index"
                ],
                "loaded_aperture_bias_degrees": calibrated_frontier[
                    "loaded_aperture_bias_degrees"
                ],
                "interpretation": "loaded hysteresis reaches two frames before release but changes transport",
            },
            "transport_frontier": {
                "lift_and_transport": transport_frontier["lift_and_transport"],
                "loaded_aperture_bias_degrees": transport_frontier[
                    "loaded_aperture_bias_degrees"
                ],
                "contact_loss_source_index": transport_frontier[
                    "contact_loss_source_index"
                ],
                "interpretation": "transport and aperture can coexist but rigid pad contact still slips",
            },
            "rounded_pad_frontier": {
                "piece_lifted": capsule_frontier["piece_lifted"],
                "loaded_aperture_bias_degrees": capsule_frontier[
                    "loaded_aperture_bias_degrees"
                ],
                "contact_loss_source_index": capsule_frontier[
                    "contact_loss_source_index"
                ],
                "interpretation": "rounded rigid contact does not reproduce the compliant physical cap",
            },
        },
        "resolved_diagnosis": {
            "primary": "real rubber cap deformation and distributed contact patch are absent from the rigid simulator contact model",
            "contributing": [
                "fixed-side rubber was displaced from the actual load-bearing jaw surface",
                "plain MuJoCo position actuator overcloses after contact instead of holding the measured loaded aperture",
                "constant low torque cannot represent high-effort closure followed by low-current geared holding",
            ],
            "ruled_out_as_standalone_repairs": [
                "higher scalar friction",
                "actuator zero shift",
                "finite global force limit",
                "binary contact force limit",
                "4D versus 6D contact dimensionality",
                "softened rigid contact",
                "box versus capsule rigid pad shape",
            ],
        },
        "required_measurement_packet": {
            "purpose": "identify a deformable pad and geared load-hold model without retrospective overfit",
            "measurements": [
                "jaw aperture and motor current at 100 Hz or faster during unloaded close, first contact, loaded hold, and release",
                "direct fingertip normal force versus commanded and measured gripper angle",
                "rubber cap profile, thickness, durometer or compression curve, and loaded contact-patch dimensions",
                "synchronized side view sufficient to recover pawn pose and both fingertip contact heights",
            ],
            "minimum_trials": "three unloaded cycles and three blocked closures at two known gaps before any pawn task",
            "robot_motion_authority": False,
            "operator_owned": True,
        },
        "experimental_implementation": {
            "parameter": "gripper_load_hold_enabled",
            "default_enabled": False,
            "promotion_status": "not_promoted",
            "reason": "no frozen candidate passed all C2 anchor gates",
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    destination = output_path or (
        root / "outputs" / "sail" / "grasp-retention-closeout-v1" / "receipt.json"
    )
    atomic_write_json(destination, receipt)
    return receipt
