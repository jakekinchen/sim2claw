"""Read-only Studio projection of the learning-factory controller state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .learning_factory import STAGE_IDS, LearningFactory
from .learning_factory_artifacts import canonical_digest, load_json_object
from .paths import REPO_ROOT


DEFAULT_FACTORY_PROJECT = Path(
    "configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json"
)


def _campaign_history(factory: LearningFactory) -> list[dict[str, Any]]:
    campaign_root = factory.root.parent
    if not campaign_root.is_dir():
        return []
    history: list[dict[str, Any]] = []
    for generation_root in sorted(campaign_root.iterdir()):
        if not generation_root.is_dir() or not generation_root.name.isdigit():
            continue
        generation = int(generation_root.name)
        stage_rows: list[dict[str, Any]] = []
        attempt_count = 0
        for stage_id in STAGE_IDS:
            latest_path = generation_root / "stages" / stage_id / "latest.json"
            attempts = generation_root / "stages" / stage_id / "attempts"
            if attempts.is_dir():
                attempt_count += sum(path.is_dir() for path in attempts.iterdir())
            if not latest_path.is_file():
                continue
            result = load_json_object(latest_path, label="factory history stage result")
            unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
            if (
                result.get("project_id") != factory.context.project["project_id"]
                or result.get("campaign_id") != factory.context.campaign_id
                or int(result.get("generation", -1)) != generation
                or result.get("stage_id") != stage_id
                or result.get("result_sha256") != canonical_digest(unsigned)
            ):
                raise ValueError(f"invalid factory history receipt: {latest_path}")
            stage_rows.append(
                {
                    "stage": stage_id,
                    "status": result["status"],
                    "result_sha256": result["result_sha256"],
                    "finished_at": result["finished_at"],
                }
            )
        recursion_path = generation_root / "recursion.json"
        recursion = (
            load_json_object(recursion_path, label="factory recursion")
            if recursion_path.is_file()
            else None
        )
        complete = len(stage_rows) == len(STAGE_IDS) and all(
            row["status"] == "passed" for row in stage_rows
        )
        overall = (
            "passed"
            if complete
            else (stage_rows[-1]["status"] if stage_rows else "not_started")
        )
        history.append(
            {
                "generation": generation,
                "parent_generation": (
                    recursion.get("parent_generation") if recursion else None
                ),
                "route_targets": recursion.get("route_targets", []) if recursion else [],
                "overall_status": overall,
                "completed_stage_count": len(stage_rows),
                "attempt_count": attempt_count,
                "latest_stage": stage_rows[-1]["stage"] if stage_rows else None,
                "latest_finished_at": stage_rows[-1]["finished_at"] if stage_rows else None,
                "stages": stage_rows,
            }
        )
    return history


def build_factory_navigation(
    *,
    repo_root: Path = REPO_ROOT,
    project_path: Path = DEFAULT_FACTORY_PROJECT,
) -> dict[str, Any]:
    """Return stage cards and commands without exposing a mutation endpoint."""

    factory = LearningFactory(project_path, repo_root=repo_root)
    status = factory.status()
    enriched_stages: list[dict[str, Any]] = []
    for card in status["stages"]:
        latest = factory._load_latest(card["stage"])
        evidence = None
        if latest is not None:
            output = latest.get("output") or {}
            evidence = {
                "status": latest["status"],
                "proof_class": latest["proof_class"],
                "summary": latest["summary"],
                "started_at": latest["started_at"],
                "finished_at": latest["finished_at"],
                "result_path": latest["result_path"],
                "result_sha256": latest["result_sha256"],
                "output_sha256": latest.get("output_sha256"),
                "output_ref": latest.get("output_ref"),
                "output_schema": output.get("schema_version"),
                "output_keys": sorted(output),
                "implementation_sha256": latest["implementation"]["sha256"],
                "diagnostics": latest.get("diagnostics", {}),
            }
        enriched_stages.append({**card, "evidence": evidence})
    status = {**status, "stages": enriched_stages}
    return {
        "schema_version": "sim2claw.studio_learning_factory.v1",
        "read_only": True,
        "execution_endpoint": None,
        "training_authority": False,
        "evaluation_authority": False,
        "promotion_authority": False,
        "physical_authority": False,
        "factory": status,
        "campaign_history": _campaign_history(factory),
    }
