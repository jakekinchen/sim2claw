"""Deterministic Studio projection of the human and agent project surfaces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT
from .sail.studio import StudioObservatoryError, load_studio_observatory
from .studio_catalog import build_catalog


CONFIG_SCHEMA = "sim2claw.studio_project_map_config.v1"
API_SCHEMA = "sim2claw.studio_project_map.v1"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "studio" / "project_map_v1.json"
DEFAULT_FACTORY_PROJECT = (
    REPO_ROOT / "configs" / "projects" / "pawn_rank12_reachable_bg_hackathon_v1.json"
)
ALLOWED_ROUTES = {
    "replay",
    "sail",
    "library",
    "calibration",
    "robots",
    "orchestrator",
    "record",
}
EXPECTED_STAGE_IDS = (
    "capture",
    "scene",
    "simulate",
    "replay",
    "evaluate",
    "diagnose",
    "improve",
    "learn_transfer",
)
EXPECTED_AUTHORITY_KEYS = {
    "agent_is_evaluator",
    "agent_can_promote",
    "training_authority",
    "physical_authority",
    "robot_motion",
}


class StudioProjectMapError(ValueError):
    """Raised when the project map cannot be projected without guessing."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StudioProjectMapError(f"{label} is unavailable: {error}") from error
    if not isinstance(payload, dict):
        raise StudioProjectMapError(f"{label} must be a JSON object")
    return payload


def _validated_config(path: Path) -> tuple[dict[str, Any], str]:
    payload = _load_object(path, "Studio project map config")
    if payload.get("schema_version") != CONFIG_SCHEMA:
        raise StudioProjectMapError("unexpected Studio project map config schema")
    for field in ("project_id", "title", "objective"):
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            raise StudioProjectMapError(f"Studio project map {field} is invalid")
    stages = payload.get("stages")
    if not isinstance(stages, list) or len(stages) != len(EXPECTED_STAGE_IDS):
        raise StudioProjectMapError("Studio project map must declare eight stages")
    if not all(isinstance(stage, dict) for stage in stages):
        raise StudioProjectMapError("Studio project map stages must be objects")
    identifiers = tuple(str(stage.get("id") or "") for stage in stages)
    if identifiers != EXPECTED_STAGE_IDS:
        raise StudioProjectMapError("Studio project map stages changed order or identity")
    if [stage.get("order") for stage in stages] != list(range(1, 9)):
        raise StudioProjectMapError("Studio project map stage order is invalid")
    for stage in stages:
        views = stage.get("human_views")
        agent = stage.get("agent")
        if not all(
            isinstance(stage.get(field), str) and stage[field].strip()
            for field in ("title", "purpose")
        ):
            raise StudioProjectMapError(f"{stage['id']} has invalid presentation text")
        if not isinstance(views, list) or not views:
            raise StudioProjectMapError(f"{stage['id']} has no researcher view")
        if not all(
            isinstance(view, dict)
            and isinstance(view.get("label"), str)
            and bool(view["label"].strip())
            and isinstance(view.get("route"), str)
            for view in views
        ):
            raise StudioProjectMapError(f"{stage['id']} has an invalid researcher view")
        if any(view["route"] not in ALLOWED_ROUTES for view in views):
            raise StudioProjectMapError(f"{stage['id']} declares an unknown Studio route")
        if not isinstance(agent, dict):
            raise StudioProjectMapError(f"{stage['id']} has no agent read contract")
        if not all(
            isinstance(agent.get(field), str) and bool(agent[field].strip())
            for field in ("access", "boundary")
        ):
            raise StudioProjectMapError(f"{stage['id']} has an invalid agent boundary")
        if not isinstance(agent.get("reads"), list) or not all(
            isinstance(value, str) and bool(value.strip()) for value in agent["reads"]
        ):
            raise StudioProjectMapError(f"{stage['id']} has no agent read contract")
        if not isinstance(agent.get("commands"), list) or not all(
            isinstance(value, str) and bool(value.strip()) for value in agent["commands"]
        ):
            raise StudioProjectMapError(f"{stage['id']} has an invalid command contract")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or set(authority) != EXPECTED_AUTHORITY_KEYS
        or any(not isinstance(value, bool) for value in authority.values())
        or any(authority.values())
    ):
        raise StudioProjectMapError("Studio project map authority must remain closed")
    return payload, _sha256_file(path)


def _factory_binding(repo_root: Path, path: Path) -> dict[str, Any]:
    try:
        project = _load_object(path, "Learning Factory project declaration")
        source = project["source_of_truth"]
        state_relative = Path(str(source["project_state"]))
        if state_relative.is_absolute() or ".." in state_relative.parts:
            raise StudioProjectMapError("Learning Factory state path is not repository-relative")
        state_path = (repo_root / state_relative).resolve()
        if not state_path.is_relative_to(repo_root.resolve()):
            raise StudioProjectMapError("Learning Factory state path leaves the repository")
        expected = str(source["project_state_sha256"])
        observed = _sha256_file(state_path)
        if observed != expected:
            raise StudioProjectMapError("Learning Factory project-state binding is stale")
        return {
            "available": True,
            "status": "bound",
            "project_id": project.get("project_id"),
            "project_state_path": state_relative.as_posix(),
            "project_state_sha256": observed,
        }
    except (KeyError, TypeError, StudioProjectMapError, OSError, ValueError) as error:
        return {
            "available": False,
            "status": "unavailable",
            "reason": str(error),
        }


def _stage_observations(
    catalog: dict[str, Any],
    sail: dict[str, Any] | None,
    factory: dict[str, Any],
    *,
    read_only: bool,
    recorder_control_enabled: bool,
    orchestrator_available: bool,
) -> dict[str, dict[str, Any]]:
    episodes = [row for row in catalog.get("episodes", []) if isinstance(row, dict)]
    summary = catalog.get("summary") if isinstance(catalog.get("summary"), dict) else {}
    project = catalog.get("project") if isinstance(catalog.get("project"), dict) else {}
    physical_sources = [
        row
        for row in episodes
        if row.get("proof_class") == "physical_teleoperation_source_unqualified"
    ]
    dual_camera_sources = [
        row for row in physical_sources if len(row.get("recording_feeds") or []) >= 2
    ]
    hil_packets = [
        row
        for row in episodes
        if row.get("proof_class") == "physical_hil_unloaded_joint_observation"
    ]
    admitted_hil = [row for row in hil_packets if row.get("status") == "passed"]
    rejected_hil = [row for row in hil_packets if row.get("status") == "failed"]
    paired_physics = [
        row
        for row in physical_sources
        if bool(
            (
                (row.get("comparison") or {}).get("physics_replay") or {}
            ).get("available")
        )
    ]
    calibration_count = len(catalog.get("calibrations") or [])
    robot_count = len(catalog.get("robots") or [])
    sail_available = bool(sail and sail.get("available"))
    sail_episode_count = len(sail.get("episodes") or []) if sail_available else 0
    training_lock = str(project.get("training_lock") or "closed")
    return {
        "capture": {
            "status": "partial" if physical_sources or hil_packets else "missing",
            "measure": (
                (
                    f"{len(physical_sources)} physical sources · "
                    f"{len(dual_camera_sources)} source dual-camera · "
                    f"{len(hil_packets)} bounded HIL packets"
                )
                if hil_packets
                else (
                    f"{len(physical_sources)} physical sources · "
                    f"{len(dual_camera_sources)} dual-camera"
                )
            ),
            "proof": (
                "recorded source + unloaded HIL evidence · not training-admitted"
                if hil_packets
                else "recorded source evidence · not training-admitted"
            ),
            "missing": ["evaluator admission", "held-out consequence"],
            "detail": (
                "Interactive loopback capture is available."
                if recorder_control_enabled
                else "Capture commands are unavailable in read-only Studio."
            ),
        },
        "scene": {
            "status": "partial" if calibration_count else "missing",
            "measure": f"{calibration_count} visual calibration asset",
            "proof": "relative visual reconstruction",
            "missing": ["metric scale", "collision validation", "coverage certificate"],
            "detail": "Visual reconstruction is present; metric and collision authority remain separate.",
        },
        "simulate": {
            "status": "available" if robot_count else "missing",
            "measure": f"{robot_count} MuJoCo embodiments · canonical CPU/fp32 evaluation",
            "proof": "simulation evidence",
            "missing": ["physical-transfer consequence"],
            "detail": "MuJoCo remains the canonical physics and collision runtime.",
        },
        "replay": {
            "status": "partial" if episodes else "missing",
            "measure": (
                f"{len(episodes)} catalog episodes · {len(paired_physics)}/{len(physical_sources)} "
                "physical sources physics-paired"
                + (f" · {len(hil_packets)} HIL" if hil_packets else "")
            ),
            "proof": "separated real · visual-only · action-frozen physics lanes",
            "missing": [
                f"{max(0, len(physical_sources) - len(paired_physics))} physical physics pairings"
            ],
            "detail": "The synchronized replay surface never invents a missing physics lane.",
        },
        "evaluate": {
            "status": "available" if episodes else "missing",
            "measure": (
                f"{summary.get('passed_episodes', 0)} labeled passes / "
                f"{summary.get('episodes', len(episodes))} catalog episodes"
                + (
                    f" · {len(admitted_hil)}/{len(hil_packets)} HIL admitted"
                    if hil_packets
                    else ""
                )
            ),
            "proof": "receipt-scoped evaluator outcomes · non-comparable proof classes stay separate",
            "missing": ["strict physical held-outs", "complete consequence coverage"],
            "detail": (
                "Dense margins explain progress; frozen gates define acceptance."
                + (
                    f" HIL retained {len(admitted_hil)} admitted unloaded "
                    f"measurement(s) and {len(rejected_hil)} rejected packet(s)."
                    if hil_packets
                    else ""
                )
            ),
        },
        "diagnose": {
            "status": "available" if sail_available else "unavailable",
            "measure": (
                f"{sail_episode_count} receipt-bound SAIL episodes"
                if sail_available
                else "SAIL observatory unavailable"
            ),
            "proof": "residual → mechanism → intervention → consequence",
            "missing": (
                list((sail or {}).get("missingness", {}).get("global") or [])
                if sail_available
                else ["receipt-verified SAIL observatory"]
            ),
            "detail": (
                "Agents may read structured diagnosis; the evaluator retains scoring authority."
                if sail_available
                else "Diagnosis fails closed until the observatory receipt verifies."
            )
            + (
                " The HIL shoulder candidate remains rejected; elbow coupling and "
                "strict task consequence are next evidence prerequisites."
                if hil_packets
                else ""
            ),
        },
        "improve": {
            "status": "bounded" if factory.get("available") else "unavailable",
            "measure": (
                "Learning Factory bound · Task Orchestrator "
                + ("available" if orchestrator_available else "read-only/unavailable")
                if factory.get("available")
                else "Learning Factory binding unavailable"
            ),
            "proof": "proposal-only governed outer loop",
            "missing": (
                ["promoted compatible checkpoint", "admitted corrective evidence"]
                if factory.get("available")
                else [factory.get("reason") or "verified project binding"]
            ),
            "detail": "Agents propose bounded work; deterministic executors, budgets, and evaluators decide.",
        },
        "learn_transfer": {
            "status": "closed",
            "measure": training_lock.replace("_", " "),
            "proof": "no active training or physical-task authority",
            "missing": [
                "training admission",
                "held-out checkpoint pass",
                "physical canary authority",
            ],
            "detail": (
                "Read-only Studio." if read_only else "Interactive Studio does not itself grant training or motion authority."
            ),
        },
    }


def build_project_map(
    *,
    repo_root: Path = REPO_ROOT,
    config_path: Path | None = None,
    factory_project_path: Path | None = None,
    read_only: bool,
    recorder_control_enabled: bool,
    orchestrator_available: bool,
) -> dict[str, Any]:
    """Build the shared researcher/agent map from existing verified surfaces."""

    root = repo_root.resolve()
    resolved_config = config_path or (root / DEFAULT_CONFIG.relative_to(REPO_ROOT))
    resolved_factory = factory_project_path or (
        root / DEFAULT_FACTORY_PROJECT.relative_to(REPO_ROOT)
    )
    config, config_sha256 = _validated_config(resolved_config)
    catalog = build_catalog(root)
    try:
        sail = load_studio_observatory(repo_root=root)
    except (StudioObservatoryError, OSError, ValueError, json.JSONDecodeError):
        sail = None
    factory = _factory_binding(root, resolved_factory)
    observations = _stage_observations(
        catalog,
        sail,
        factory,
        read_only=read_only,
        recorder_control_enabled=recorder_control_enabled,
        orchestrator_available=orchestrator_available,
    )
    catalog_episodes = [
        row for row in catalog.get("episodes", []) if isinstance(row, dict)
    ]
    hil_packets = [
        row
        for row in catalog_episodes
        if row.get("proof_class") == "physical_hil_unloaded_joint_observation"
    ]
    stages = []
    for declared in config["stages"]:
        observation = observations[declared["id"]]
        stages.append(
            {
                **declared,
                **observation,
            }
        )
    return {
        "schema_version": API_SCHEMA,
        "available": True,
        "read_only": True,
        "physical_authority": False,
        "project_id": config["project_id"],
        "title": config["title"],
        "objective": config["objective"],
        "config": {
            "path": resolved_config.relative_to(root).as_posix(),
            "sha256": config_sha256,
        },
        "interface": {
            "human": "Studio routes and contextual drawers",
            "agent": "Loopback JSON endpoints plus content-addressed repository artifacts",
            "shared_truth": "The same receipts, proof classes, evaluator outputs, and authority gates",
            "agent_entrypoint": "GET /api/project-map",
        },
        "stages": stages,
        "hil_evidence": {
            "available": bool(hil_packets),
            "proof_class": "physical_hil_unloaded_joint_observation",
            "packets": len(hil_packets),
            "admitted_unloaded_measurements": sum(
                row.get("status") == "passed" for row in hil_packets
            ),
            "rejected_packets": sum(
                row.get("status") == "failed" for row in hil_packets
            ),
            "task_score_changed": False,
            "simulator_parameter_promoted": False,
            "next_prerequisite": (
                "elbow coupling plus strict task consequence"
                if hil_packets
                else "receipt-verified HIL publication"
            ),
        },
        "factory": factory,
        "authority": {
            **config["authority"],
            "read_only_surface": True,
            "recorder_control_exposed": bool(recorder_control_enabled),
            "orchestrator_control_exposed": bool(orchestrator_available),
        },
    }


__all__ = [
    "API_SCHEMA",
    "CONFIG_SCHEMA",
    "DEFAULT_CONFIG",
    "StudioProjectMapError",
    "build_project_map",
]
