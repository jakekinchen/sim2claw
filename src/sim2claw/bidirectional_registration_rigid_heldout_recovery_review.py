"""Motion-free, content-free review of the V4 heldout recovery protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .paths import REPO_ROOT


class HeldoutRecoveryReviewError(RuntimeError):
    """The recovery contract cannot be independently admitted."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path(entry: Mapping[str, Any]) -> Path:
    raw = Path(str(entry["path"]))
    return raw if raw.is_absolute() else REPO_ROOT / raw


def _bound(entry: Mapping[str, Any]) -> dict[str, Any]:
    path = _path(entry)
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise HeldoutRecoveryReviewError(f"review input changed: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def review(contract_path: Path, output_path: Path) -> dict[str, Any]:
    recovery = json.loads(contract_path.read_text(encoding="utf-8"))
    prior = _bound(recovery["prior_contract"])
    failure = _bound(recovery["prior_failed_open"])
    parser_path = _path(recovery["recovery_parser"])
    parser_bound = (
        parser_path.is_file()
        and _sha(parser_path) == recovery["recovery_parser"]["sha256"]
    )
    output_root = REPO_ROOT / recovery["outputs"]["root"]
    checks = {
        "prior_failure_manifest_only": failure["status"]
        == "failed_closed_before_raw_image_access"
        and failure["cumulative_manifest_read_count"] == 1
        and failure["raw_image_read_count_total"] == 0
        and failure["heldout_pixel_content_read"] is False,
        "candidate_unchanged": recovery["candidate"] == prior["candidate"],
        "fit_receipt_unchanged": recovery["fit_receipt"]
        == prior["fit_receipt"],
        "fit_review_unchanged": recovery["independent_fit_review"]
        == prior["independent_fit_review"],
        "sealed_manifest_unchanged": recovery["sealed_manifest"]
        == prior["sealed_manifest"],
        "member_set_unchanged": recovery["expected_members"]
        == prior["expected_members"],
        "annotation_protocol_unchanged": recovery["annotation_protocol"]
        == prior["annotation_protocol"],
        "thresholds_unchanged": recovery["frozen_gates"]
        == prior["frozen_gates"],
        "zero_refit_policy_unchanged": recovery["frozen_candidate_policy"]
        == prior["frozen_candidate_policy"]
        and not any(recovery["frozen_candidate_policy"].values()),
        "recovery_read_budget_exact": recovery["single_open_protocol"][
            "prior_manifest_only_read_count"
        ]
        == 1
        and recovery["single_open_protocol"][
            "additional_manifest_reads_authorized"
        ]
        == 1
        and recovery["single_open_protocol"][
            "required_cumulative_manifest_read_count"
        ]
        == 2
        and recovery["single_open_protocol"]["raw_image_reads_per_member"]
        == 1
        and recovery["single_open_protocol"][
            "required_heldout_pixel_open_count"
        ]
        == 1,
        "sealed_schema_matches_capture_source": recovery["recovery_schema"][
            "sealed_member_keys"
        ]
        == [
            "opaque_id",
            "image_sha256",
            "image_bytes",
            "capture_receipt_sha256",
        ]
        and recovery["recovery_schema"]["sealed_directory"]
        == "heldout-sealed"
        and recovery["recovery_schema"]["image_filename"] == "selected.png"
        and recovery["recovery_schema"]["capture_receipt_filename"]
        == "capture_receipt.json",
        "parser_hash_frozen": parser_bound,
        "no_prior_recovery_output": not output_root.exists(),
        "authority_closed": not any(recovery["authority"].values()),
    }
    checks = {name: bool(value) for name, value in checks.items()}
    admitted = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_heldout_recovery_review_receipt.v1",
        "status": "CONTINUE_TO_VERSIONED_SINGLE_PIXEL_OPEN"
        if admitted
        else "REDIRECT",
        "proof_class": "independent_motion_free_heldout_recovery_protocol_review",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "prior_failure_sha256": recovery["prior_failed_open"]["sha256"],
        "candidate_sha256": recovery["candidate"]["sha256"],
        "frozen_gates": recovery["frozen_gates"],
        "cumulative_manifest_read_count_before_recovery": 1,
        "heldout_pixel_open_count_before_recovery": 0,
        "checks": checks,
        "recovery_open_authorized": admitted,
        "authority": recovery["authority"],
        "claim_boundary": "Independent protocol review only; heldout pixels remain unread and no evaluation, task, motion, promotion, or transfer authority is granted.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
