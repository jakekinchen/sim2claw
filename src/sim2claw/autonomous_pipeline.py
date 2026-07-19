"""Project-scoped, truth-preserving stages for NemoClaw/OpenClaw."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT
from .project_bundle import (
    PROJECT_AUTHORITY_CONTRACT,
    ProjectBundleError,
    inspect_project,
    require_exact_authority,
)
from .studio_events import StudioActivity


STAGE_RESULT_SCHEMA = "sim2claw.nemoclaw_stage_result.v1"
PIPELINE_STATUS_SCHEMA = "sim2claw.nemoclaw_pipeline_status.v1"
STAGES = (
    "inspect",
    "calibrate-sim",
    "evaluate-skills",
    "train-candidates",
    "compare-candidates",
)
STAGE_STATUSES = ("passed", "partial", "blocked")


class PipelineStateError(RuntimeError):
    """Raised when a saved stage result is not bound to the selected project."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineStateError(f"cannot read pipeline JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise PipelineStateError(f"pipeline JSON must contain an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _result_root(repo_root: Path, project_id: str) -> Path:
    return repo_root / "runs" / "nemoclaw" / "projects" / project_id


def _project_context(project_path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        inspection = inspect_project(project_path, repo_root=repo_root)
    except ProjectBundleError as error:
        raise PipelineStateError(str(error)) from error
    return {
        "inspection": inspection,
        "project_id": inspection["project_id"],
        "project_path": inspection["project_path"],
        "project_state": inspection["project_state"],
        "project_manifest_sha256": inspection["project_manifest_sha256"],
        "evaluation_set_id": inspection["evaluation_set_id"],
        "evaluation_contract_sha256": inspection["evaluation_contract_sha256"],
        "authority": inspection["authority"],
    }


def _stage_payload(
    stage: str,
    project: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    state = _load_json(repo_root / project["project_state"])
    common = {
        "project_id": project["project_id"],
        "project_path": project["project_path"],
        "project_manifest_sha256": project["project_manifest_sha256"],
        "evaluation_set_id": project["evaluation_set_id"],
        "evaluation_contract_sha256": project["evaluation_contract_sha256"],
        "training_lock": state["training_lock"],
        "promotion_owner": state["promotion_owner"],
        "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        "physical_authority": False,
        "policy_promoted": False,
    }
    if stage == "inspect":
        return {
            **common,
            "status": "passed",
            "summary": "Project, state, evaluator, exact 12-skill scope, catalog, and bundle inputs agree.",
            "evidence": project["inspection"],
        }
    if stage == "calibrate-sim":
        registration = state["workspace_registration"]
        return {
            **common,
            "status": "blocked",
            "summary": "Current 100 mm workspace is not requalified against the frozen evaluation pose.",
            "blockers": [
                "deterministic object-contact replay is not accepted",
                "current workspace requires separate evaluator requalification",
                registration["status"],
            ],
            "evidence": registration,
        }
    if stage == "evaluate-skills":
        summary_path = (
            repo_root
            / "outputs/pawn_composability/recovered_corpus_v2/evaluation/summary.json"
        )
        summary = _load_json(summary_path) if summary_path.is_file() else None
        return {
            **common,
            "status": "partial" if summary else "blocked",
            "summary": (
                "Retrospective B-G scorecard exists but contains no reviewed base-center annotations or covered skills."
                if summary
                else "No recovered-corpus B-G scorecard is present."
            ),
            "evidence": summary,
            "evidence_path": summary_path.relative_to(repo_root).as_posix(),
        }
    if stage == "train-candidates":
        return {
            **common,
            "status": "blocked",
            "summary": "Training is fail-closed until M7 candidates replay and pass the separate evaluator.",
            "blockers": [state["training_lock"]],
            "training_started": False,
        }
    if stage == "compare-candidates":
        return {
            **common,
            "status": "blocked",
            "summary": "No compatible B-G checkpoint is admitted for comparison or promotion.",
            "blockers": [
                "no B-G checkpoint bound to the frozen product evaluation",
                "retrospective sources are not held out and cannot promote a checkpoint",
            ],
        }
    raise ValueError(f"unsupported pipeline stage: {stage}")


def run_stage(
    stage: str,
    project_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"unsupported pipeline stage: {stage}")
    repo_root = repo_root.resolve()
    project = _project_context(project_path, repo_root)
    started_at = datetime.now(UTC)
    activity = StudioActivity(
        kind="nemoclaw_pipeline",
        title=f"NemoClaw pipeline: {stage}",
        task_id=f"{project['project_id']}:{stage}",
        run_root=repo_root / "runs/studio/processes",
    )
    activity.update(phase="Inspecting project-bound live truth", current=0, total=1)
    try:
        payload = _stage_payload(stage, project, repo_root)
        finished_at = datetime.now(UTC)
        result_without_digest = {
            "schema_version": STAGE_RESULT_SCHEMA,
            "stage": stage,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": (finished_at - started_at).total_seconds(),
            **payload,
        }
        result = {
            **result_without_digest,
            "result_digest": _digest(result_without_digest),
        }
        run_id = started_at.strftime("%Y%m%dT%H%M%SZ") + f"-{stage}"
        root = _result_root(repo_root, project["project_id"])
        result_path = root / "runs" / run_id / "stage_result.json"
        _write_json(result_path, result)
        _write_json(root / "latest-stage-result.json", result)
        activity.update(
            phase=f"Finished with proof state: {result['status']}",
            current=1,
            total=1,
            detail=str(result_path.relative_to(repo_root)),
            metrics={"status": result["status"], "physical_authority": False},
        )
        activity.complete(
            detail=f"stage_result={result_path.relative_to(repo_root)}",
            metrics={"proof_state": result["status"]},
        )
        return result
    except Exception as error:
        activity.fail(error)
        raise


def _validate_saved_result(result: dict[str, Any], project: dict[str, Any]) -> None:
    expected = {
        "schema_version": STAGE_RESULT_SCHEMA,
        "project_id": project["project_id"],
        "project_path": project["project_path"],
        "project_manifest_sha256": project["project_manifest_sha256"],
        "evaluation_set_id": project["evaluation_set_id"],
        "evaluation_contract_sha256": project["evaluation_contract_sha256"],
        "physical_authority": False,
    }
    for key, expected_value in expected.items():
        if result.get(key) != expected_value:
            raise PipelineStateError(
                f"saved pipeline result {key} mismatch: expected {expected_value!r}, "
                f"observed {result.get(key)!r}"
            )
    try:
        authority = require_exact_authority(
            result.get("authority"), label="saved pipeline authority contract"
        )
    except ProjectBundleError as error:
        raise PipelineStateError(str(error)) from error
    if authority != project["authority"]:
        raise PipelineStateError("saved pipeline authority contract mismatches project")
    if result.get("stage") not in STAGES:
        raise PipelineStateError(f"saved pipeline result has invalid stage: {result.get('stage')!r}")
    if result.get("status") not in STAGE_STATUSES:
        raise PipelineStateError(
            f"saved pipeline result has invalid status: {result.get('status')!r}"
        )
    observed_digest = result.get("result_digest")
    unsigned = {key: value for key, value in result.items() if key != "result_digest"}
    expected_digest = _digest(unsigned)
    if observed_digest != expected_digest:
        raise PipelineStateError(
            f"saved pipeline result digest mismatch: expected {expected_digest}, "
            f"observed {observed_digest}"
        )


def pipeline_status(
    project_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    project = _project_context(project_path, repo_root)
    path = _result_root(repo_root, project["project_id"]) / "latest-stage-result.json"
    common = {
        "schema_version": PIPELINE_STATUS_SCHEMA,
        "project_id": project["project_id"],
        "project_path": project["project_path"],
        "project_manifest_sha256": project["project_manifest_sha256"],
        "evaluation_set_id": project["evaluation_set_id"],
        "evaluation_contract_sha256": project["evaluation_contract_sha256"],
        "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        "physical_authority": False,
    }
    if not path.is_file():
        return {
            **common,
            "status": "not_started",
            "latest_stage": None,
            "latest_stage_result": None,
        }
    result = _load_json(path)
    _validate_saved_result(result, project)
    return {
        **common,
        "status": result["status"],
        "latest_stage": result["stage"],
        "latest_stage_result": result,
    }
