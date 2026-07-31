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

    return {
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
