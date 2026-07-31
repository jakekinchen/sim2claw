"""Fail-closed Studio projection for the OR26 synchronized visual comparison."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT
from .studio_catalog import media_url


CLOSEOUT_PATH = Path(
    "configs/decisions/observable_registration_visible_divergence_video_v1_closeout.json"
)
OUTPUT_ROOT = Path("outputs/observable_registration_visible_divergence_video_v1")
EXPECTED_CLOSEOUT_SCHEMA = (
    "sim2claw.observable_registration_visible_divergence_video_closeout.v1"
)
EXPECTED_RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_visible_divergence_video_receipt.v1"
)
MEASURED_CLOSEOUT_PATH = Path(
    "configs/decisions/"
    "observable_registration_measured_state_visual_twin_v1_closeout.json"
)
EXPECTED_MEASURED_CLOSEOUT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_closeout.v1"
)
EXPECTED_MEASURED_RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_receipt.v1"
)


class VisibleDivergenceStudioError(ValueError):
    """Raised when the retained comparison cannot be published safely."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VisibleDivergenceStudioError(f"{path} is not a JSON object")
    return payload


def _verified_file(
    *,
    repo_root: Path,
    output_root: Path,
    relative_name: str,
    expected_sha256: str,
) -> Path:
    path = (output_root / relative_name).resolve()
    if not path.is_relative_to(output_root.resolve()) or not path.is_file():
        raise VisibleDivergenceStudioError(
            f"visible-divergence artifact is unavailable: {relative_name}"
        )
    observed = _sha256(path)
    if observed != expected_sha256:
        raise VisibleDivergenceStudioError(
            f"visible-divergence artifact hash mismatch: {relative_name}"
        )
    if not path.is_relative_to(repo_root.resolve()):
        raise VisibleDivergenceStudioError(
            f"visible-divergence artifact is outside the repository: {relative_name}"
        )
    return path


def _with_measured_state_variant(
    *,
    repo_root: Path,
    baseline: dict[str, Any],
) -> dict[str, Any]:
    closeout_path = (repo_root / MEASURED_CLOSEOUT_PATH).resolve()
    closeout = _json(closeout_path)
    if (
        closeout.get("schema_version") != EXPECTED_MEASURED_CLOSEOUT_SCHEMA
        or closeout.get("status")
        != "PASS_MEASURED_STATE_VISUAL_TWIN_DIAGNOSTIC"
    ):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state closeout is not admitted"
        )
    binding = closeout.get("receipt")
    if not isinstance(binding, dict):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state receipt binding is missing"
        )
    receipt_path = (repo_root / str(binding.get("path") or "")).resolve()
    if (
        not receipt_path.is_relative_to(repo_root)
        or not receipt_path.is_file()
        or _sha256(receipt_path) != binding.get("sha256")
    ):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state receipt hash does not verify"
        )
    receipt = _json(receipt_path)
    if (
        receipt.get("schema_version") != EXPECTED_MEASURED_RECEIPT_SCHEMA
        or receipt.get("status")
        != "PASS_MEASURED_STATE_VISUAL_TWIN_DIAGNOSTIC"
        or receipt.get("artifact_sha256") != binding.get("artifact_sha256")
    ):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state receipt identity does not verify"
        )
    output_root = receipt_path.parent.resolve()
    outputs = receipt.get("outputs")
    if not isinstance(outputs, dict):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state output bindings are missing"
        )
    measured_media: dict[str, dict[str, str]] = {}
    for key, (path_key, sha_key) in {
        "physical": ("physical_video_path", "physical_video_sha256"),
        "simulator": ("simulator_video_path", "simulator_video_sha256"),
        "comparison": ("comparison_video_path", "comparison_video_sha256"),
        "poster": ("poster_path", "poster_sha256"),
    }.items():
        relative_name = str(outputs.get(path_key) or "")
        expected_sha256 = str(outputs.get(sha_key) or "")
        path = _verified_file(
            repo_root=repo_root,
            output_root=output_root,
            relative_name=relative_name,
            expected_sha256=expected_sha256,
        )
        measured_media[key] = {
            "url": media_url(path, repo_root),
            "sha256": expected_sha256,
        }
    dynamics = receipt.get("natural_dynamics")
    trajectory = receipt.get("trajectory_comparison")
    visible = receipt.get("visible_comparison")
    timeline = receipt.get("timeline")
    result = closeout.get("result")
    if not all(
        isinstance(value, dict)
        for value in (dynamics, trajectory, visible, timeline, result)
    ):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state diagnostic fields are missing"
        )
    if (
        int(timeline.get("frame_count") or 0) != 531
        or float(timeline.get("output_fps") or 0) != 20
        or receipt.get("observation_conditioned") is not True
        or receipt.get("action_only_transfer") is not False
    ):
        raise VisibleDivergenceStudioError(
            "OR34 measured-state proof boundary does not verify"
        )
    contact = int(dynamics["first_selected_jaw_contact_sample"])
    pawn_motion = int(dynamics["first_motion_over_1mm_sample"])
    physical_lift = int(result["physical_lift_interval_samples"][0])
    measured_endpoints = {
        "initial": {
            "pixel_error": visible["registered_initial_pawn_error_px"],
        },
        "terminal": {
            "pixel_error": visible["registered_terminal_pawn_error_px"],
        },
        "interpretation": result["interpretation"],
    }
    measured_markers = [
        {
            "sample": contact,
            "seconds": contact / 20.0,
            "label": "Raw-state jaw contact",
            "tone": "contact",
        },
        {
            "sample": pawn_motion,
            "seconds": pawn_motion / 20.0,
            "label": "Sim pawn motion > 1 mm",
            "tone": "divergence",
        },
        {
            "sample": physical_lift,
            "seconds": physical_lift / 20.0,
            "label": "Physical lift begins",
            "tone": "contact",
        },
    ]
    baseline_variant = {
        "id": "identified_plant",
        "label": "Identified plant",
        "subtitle": "Gateway commands → fitted effective plant",
        "artifact_sha256": baseline["artifact_sha256"],
        "simulator": baseline["media"]["simulator"],
        "markers": baseline["markers"],
        "divergence_boundary": baseline["divergence_boundary"],
        "registered_planar_endpoints": baseline[
            "registered_planar_endpoints"
        ],
    }
    measured_variant = {
        "id": "measured_state",
        "label": "Raw measured state",
        "subtitle": "531 follower readings → natural MuJoCo object",
        "artifact_sha256": receipt["artifact_sha256"],
        "simulator": measured_media["simulator"],
        "markers": measured_markers,
        "divergence_boundary": {
            "sample_interval": [pawn_motion, physical_lift],
            "seconds": [pawn_motion / 20.0, physical_lift / 20.0],
            "interpretation": result["interpretation"],
        },
        "registered_planar_endpoints": measured_endpoints,
    }
    return {
        **baseline,
        "schema_version": "sim2claw.visible_divergence_studio_projection.v2",
        "artifact_sha256": receipt["artifact_sha256"],
        "media": measured_media,
        "markers": measured_markers,
        "divergence_boundary": measured_variant["divergence_boundary"],
        "registered_planar_endpoints": measured_endpoints,
        "default_variant": "measured_state",
        "variants": {
            "measured_state": measured_variant,
            "identified_plant": baseline_variant,
        },
        "trajectory_comparison": trajectory,
        "observation_conditioned": True,
        "action_only_transfer": False,
    }


def load_visible_divergence_studio(
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Return a read-only, hash-verified browser projection of OR26."""

    repo_root = repo_root.resolve()
    closeout_path = (repo_root / CLOSEOUT_PATH).resolve()
    closeout = _json(closeout_path)
    if (
        closeout.get("schema_version") != EXPECTED_CLOSEOUT_SCHEMA
        or closeout.get("status") != "PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO"
    ):
        raise VisibleDivergenceStudioError("OR26 closeout is not admitted")

    receipt_binding = closeout.get("receipt")
    if not isinstance(receipt_binding, dict):
        raise VisibleDivergenceStudioError("OR26 receipt binding is missing")
    receipt_path = (repo_root / str(receipt_binding.get("path") or "")).resolve()
    if (
        not receipt_path.is_relative_to(repo_root)
        or not receipt_path.is_file()
        or _sha256(receipt_path) != receipt_binding.get("sha256")
    ):
        raise VisibleDivergenceStudioError("OR26 receipt hash does not verify")
    receipt = _json(receipt_path)
    if (
        receipt.get("schema_version") != EXPECTED_RECEIPT_SCHEMA
        or receipt.get("status") != "PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO"
        or receipt.get("artifact_sha256") != receipt_binding.get("artifact_sha256")
    ):
        raise VisibleDivergenceStudioError("OR26 receipt identity does not verify")

    output_root = receipt_path.parent.resolve()
    output_bindings = receipt.get("outputs")
    if not isinstance(output_bindings, dict):
        raise VisibleDivergenceStudioError("OR26 output bindings are missing")
    names = {
        "physical": (
            "physical_video_path",
            "physical_video_sha256",
        ),
        "simulator": (
            "simulator_video_path",
            "simulator_video_sha256",
        ),
        "comparison": (
            "comparison_video_path",
            "comparison_video_sha256",
        ),
        "poster": (
            "poster_path",
            "poster_sha256",
        ),
    }
    media: dict[str, dict[str, str]] = {}
    for key, (path_key, sha_key) in names.items():
        relative_name = str(output_bindings.get(path_key) or "")
        expected_sha256 = str(output_bindings.get(sha_key) or "")
        path = _verified_file(
            repo_root=repo_root,
            output_root=output_root,
            relative_name=relative_name,
            expected_sha256=expected_sha256,
        )
        media[key] = {
            "url": media_url(path, repo_root),
            "sha256": expected_sha256,
        }

    timeline = receipt.get("timeline")
    divergence = receipt.get("visible_divergence")
    registration = receipt.get("camera_and_display_registration")
    if not all(
        isinstance(value, dict)
        for value in (timeline, divergence, registration)
    ):
        raise VisibleDivergenceStudioError("OR26 timing or divergence fields are missing")
    boundary = divergence.get("earliest_contact_consequence_divergence_boundary")
    endpoints = divergence.get("registered_planar_endpoints")
    if not isinstance(boundary, dict) or not isinstance(endpoints, dict):
        raise VisibleDivergenceStudioError("OR26 visible boundary does not verify")

    frame_count = int(timeline.get("frame_count") or 0)
    fps = float(timeline.get("output_fps") or 0)
    if frame_count != 531 or fps != 20:
        raise VisibleDivergenceStudioError("OR26 canonical timeline does not verify")

    markers = [
        {
            "sample": int(divergence["simulator_first_unilateral_contact_sample"]),
            "label": "Unilateral contact",
            "tone": "contact",
        },
        {
            "sample": int(divergence["simulator_first_tilt_over_5_degrees_sample"]),
            "label": "Tilt > 5°",
            "tone": "divergence",
        },
        {
            "sample": int(divergence["simulator_first_bilateral_contact_sample"]),
            "label": "Bilateral contact",
            "tone": "contact",
        },
        {
            "sample": int(divergence["simulator_first_sustained_support_loss_sample"]),
            "label": "Support loss",
            "tone": "divergence",
        },
    ]
    for marker in markers:
        marker["seconds"] = marker["sample"] / fps

    baseline = {
        "schema_version": "sim2claw.visible_divergence_studio_projection.v1",
        "available": True,
        "read_only": True,
        "physical_authority": False,
        "global_mapping_approved": False,
        "physics_success_claim": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "artifact_sha256": receipt["artifact_sha256"],
        "timeline": {
            "frame_count": frame_count,
            "fps": fps,
            "duration_seconds": frame_count / fps,
            "missing_physical_frame_count": int(
                timeline.get("missing_physical_frame_count") or 0
            ),
        },
        "media": media,
        "markers": markers,
        "divergence_boundary": {
            "sample_interval": boundary["sample_interval"],
            "seconds": boundary["seconds"],
            "interpretation": boundary["interpretation"],
        },
        "registered_planar_endpoints": endpoints,
        "registration": {
            "post_warp_board_corner_rms_px": registration[
                "post_warp_board_corner_rms_px"
            ],
            "display_homography_is_metric_camera_calibration": registration[
                "display_homography_is_metric_camera_calibration"
            ],
            "global_mapping_approved": registration["global_mapping_approved"],
        },
    }
    return _with_measured_state_variant(
        repo_root=repo_root,
        baseline=baseline,
    )
