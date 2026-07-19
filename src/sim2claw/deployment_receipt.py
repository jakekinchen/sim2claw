"""Validated, atomic NemoClaw deployment receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from .project_bundle import (
    PROJECT_AUTHORITY_CONTRACT,
    ProjectBundleError,
    require_exact_authority,
)


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_OBJECT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
VERIFIABLE_PIPELINE_STATUSES = {"passed", "partial", "blocked"}
PIPELINE_STAGES = {
    "inspect",
    "calibrate-sim",
    "evaluate-skills",
    "train-candidates",
    "compare-candidates",
}
HEALTH_CONTRACT = {
    "service": "sim2claw-studio",
    "read_only": True,
    "mode": "read_only_evidence",
    "recorder_control": "disabled",
    "physical_authority": False,
}


class DeploymentReceiptError(RuntimeError):
    """Raised before any receipt write when deployment proof is inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentReceiptError(f"cannot read deployment JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise DeploymentReceiptError(f"deployment JSON must contain an object: {path}")
    return value


def _require_equal(label: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise DeploymentReceiptError(
            f"{label} mismatch: expected {expected!r}, observed {observed!r}"
        )


def _require_authority(value: object, label: str) -> dict[str, bool | int]:
    try:
        return require_exact_authority(value, label=label)
    except ProjectBundleError as error:
        raise DeploymentReceiptError(str(error)) from error


def _result_digest(result: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in result.items() if key != "result_digest"}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def build_receipt(
    *,
    project_path: Path,
    project: dict[str, Any],
    pipeline: dict[str, Any],
    health: dict[str, Any],
    skill_sha256: str,
    source_revision: str,
    source_archive_sha256: str,
    project_bundle_sha256: str,
) -> dict[str, Any]:
    if GIT_OBJECT_PATTERN.fullmatch(source_revision) is None:
        raise DeploymentReceiptError("invalid source revision")
    for label, value in (
        ("skill", skill_sha256),
        ("source archive", source_archive_sha256),
        ("project bundle", project_bundle_sha256),
    ):
        if SHA256_PATTERN.fullmatch(value) is None:
            raise DeploymentReceiptError(f"invalid {label} SHA-256")

    manifest = _load_json(project_path)
    source = manifest.get("source_of_truth")
    if not isinstance(source, dict):
        raise DeploymentReceiptError("project manifest source_of_truth must be an object")
    manifest_authority = _require_authority(
        manifest.get("authority"), "project manifest authority contract"
    )
    project_id = manifest.get("project_id")
    manifest_sha256 = hashlib.sha256(project_path.read_bytes()).hexdigest()
    project_expected = {
        "schema_version": "sim2claw.project_inspection.v1",
        "project_id": project_id,
        "project_manifest_sha256": manifest_sha256,
        "project_state": source.get("project_state"),
        "project_state_sha256": source.get("project_state_sha256"),
        "evaluation_contract_sha256": source.get("evaluation_contract_sha256"),
        "physical_source_catalog": source.get("physical_source_catalog"),
        "physical_source_catalog_sha256": source.get("physical_source_catalog_sha256"),
        "directed_skill_ids": [
            f"pawn_{column}{source_rank}_to_{column}{destination_rank}"
            for column in "bcdefg"
            for source_rank, destination_rank in ((1, 2), (2, 1))
        ],
        "directed_skill_count": 12,
        "ready": True,
    }
    for key, expected in project_expected.items():
        _require_equal(f"project inspection {key}", project.get(key), expected)
    project_authority = _require_authority(
        project.get("authority"), "project inspection authority contract"
    )
    _require_equal("project authority contract", project_authority, manifest_authority)

    pipeline_expected = {
        "schema_version": "sim2claw.nemoclaw_pipeline_status.v1",
        "project_id": project_id,
        "project_path": project.get("project_path"),
        "project_manifest_sha256": manifest_sha256,
        "evaluation_set_id": project.get("evaluation_set_id"),
        "evaluation_contract_sha256": source.get("evaluation_contract_sha256"),
        "physical_authority": False,
    }
    for key, expected in pipeline_expected.items():
        _require_equal(f"pipeline status {key}", pipeline.get(key), expected)
    pipeline_authority = _require_authority(
        pipeline.get("authority"), "pipeline status authority contract"
    )
    _require_equal("pipeline authority contract", pipeline_authority, project_authority)
    if pipeline.get("status") not in VERIFIABLE_PIPELINE_STATUSES:
        raise DeploymentReceiptError(
            f"pipeline status is not deployment-verifiable: {pipeline.get('status')!r}"
        )
    result = pipeline.get("latest_stage_result")
    if not isinstance(result, dict):
        raise DeploymentReceiptError("pipeline has no validated latest stage result")
    if pipeline.get("latest_stage") not in PIPELINE_STAGES:
        raise DeploymentReceiptError(
            f"pipeline latest stage is invalid: {pipeline.get('latest_stage')!r}"
        )
    _require_equal(
        "latest stage result schema",
        result.get("schema_version"),
        "sim2claw.nemoclaw_stage_result.v1",
    )
    if result.get("stage") not in PIPELINE_STAGES:
        raise DeploymentReceiptError(
            f"latest stage result stage is invalid: {result.get('stage')!r}"
        )
    if result.get("status") not in VERIFIABLE_PIPELINE_STATUSES:
        raise DeploymentReceiptError(
            f"latest stage result status is invalid: {result.get('status')!r}"
        )
    for key in (
        "project_id",
        "project_path",
        "project_manifest_sha256",
        "evaluation_set_id",
        "evaluation_contract_sha256",
        "physical_authority",
    ):
        _require_equal(f"latest stage result {key}", result.get(key), pipeline.get(key))
    result_authority = _require_authority(
        result.get("authority"), "latest stage result authority contract"
    )
    _require_equal("latest stage result authority contract", result_authority, pipeline_authority)
    _require_equal("latest stage result status", result.get("status"), pipeline.get("status"))
    _require_equal("latest stage result stage", result.get("stage"), pipeline.get("latest_stage"))
    _require_equal("latest stage result digest", result.get("result_digest"), _result_digest(result))

    for key, expected in HEALTH_CONTRACT.items():
        _require_equal(f"Studio health {key}", health.get(key), expected)

    return {
        "schema_version": "sim2claw.nemoclaw_deployment_receipt.v2",
        "captured_at": datetime.now(UTC).isoformat(),
        "source_revision": source_revision,
        "source_archive_sha256": source_archive_sha256,
        "project_bundle_sha256": project_bundle_sha256,
        "skill_sha256": skill_sha256,
        "project": project,
        "pipeline": pipeline,
        "studio_health": health,
        "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        "physical_authority": False,
    }


def write_receipt(output: Path, **kwargs: Any) -> dict[str, Any]:
    receipt = build_receipt(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-path", type=Path, required=True)
    parser.add_argument("--project-json", type=Path, required=True)
    parser.add_argument("--pipeline-json", type=Path, required=True)
    parser.add_argument("--health-json", type=Path, required=True)
    parser.add_argument("--skill-sha256", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-archive-sha256", required=True)
    parser.add_argument("--project-bundle-sha256", required=True)
    args = parser.parse_args(argv)
    receipt = write_receipt(
        args.output,
        project_path=args.project_path,
        project=_load_json(args.project_json),
        pipeline=_load_json(args.pipeline_json),
        health=_load_json(args.health_json),
        skill_sha256=args.skill_sha256,
        source_revision=args.source_revision,
        source_archive_sha256=args.source_archive_sha256,
        project_bundle_sha256=args.project_bundle_sha256,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
