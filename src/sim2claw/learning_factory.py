"""Project-scoped controller for the Codex-driven Sim2Claw learning factory."""

from __future__ import annotations

import platform
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    admit_dataset_candidates,
    atomic_write_json,
    canonical_digest,
    capture_training_candidate,
    compare_calibration_candidates,
    compile_cousin_batch,
    evaluate_policy_candidates,
    load_json_object,
    normalize_counterexamples,
    promotion_state,
    sha256_file,
)
from .learning_factory_contracts import (
    ATTEMPT_SCHEMA,
    AdapterDescriptor,
    ContentAddressedArtifactStore,
    FunctionStageAdapter,
    StageLease,
    StageOutcome,
)
from .learning_factory_identity import build_implementation_identity
from .paths import REPO_ROOT
from .project_bundle import PROJECT_AUTHORITY_CONTRACT, ProjectBundleError, inspect_project


GRAPH_SCHEMA = "sim2claw.learning_factory_graph.v1"
RUN_SCHEMA = "sim2claw.learning_factory_run.v1"
STAGE_RESULT_SCHEMA = "sim2claw.learning_factory_stage_result.v1"
STATUS_SCHEMA = "sim2claw.learning_factory_status.v1"
INSPECTION_SCHEMA = "sim2claw.factory_project_inspection.v1"
STAGE_IDS = tuple(f"LF-{index:02d}" for index in range(14))
STAGE_STATUSES = (
    "not_ready",
    "ready",
    "running",
    "passed",
    "partial",
    "blocked",
    "failed",
    "terminal_negative",
    "superseded",
)
STAGE_COMPONENT_MODULES: dict[str, tuple[str, ...]] = {
    "LF-00": ("sim2claw.project_bundle", "sim2claw.doctor"),
    "LF-01": ("sim2claw.iphone_3dgs", "sim2claw.learning_factory_components"),
    "LF-02": ("sim2claw.scene", "sim2claw.learning_factory_components"),
    "LF-03": (
        "sim2claw.scene",
        "sim2claw.contact_sensitivity",
        "sim2claw.learning_factory_components",
    ),
    "LF-04": (
        "sim2claw.source_episode",
        "sim2claw.pawn_source_evaluator",
        "sim2claw.learning_factory_components",
    ),
    "LF-05": (
        "sim2claw.recorded_replay",
        "sim2claw.system_identification",
        "sim2claw.learning_factory_components",
    ),
    "LF-06": (
        "sim2claw.system_identification",
        "sim2claw.contact_sensitivity",
        "sim2claw.learning_factory_components",
    ),
    "LF-07": (
        "sim2claw.system_identification",
        "sim2claw.learning_factory_components",
        "sim2claw.learning_factory_calibration_eval",
    ),
    "LF-08": (
        "sim2claw.act_pick_place",
        "sim2claw.learning_factory_goal_data",
    ),
    "LF-09": (
        "sim2claw.act_pick_place",
        "sim2claw.source_episode",
        "sim2claw.pawn_source_evaluator",
        "sim2claw.pawn_groot_dataset",
        "sim2claw.groot_multisource_dataset",
    ),
    "LF-10": ("sim2claw.goal_act_training", "sim2claw.act_model"),
    "LF-11": (
        "sim2claw.goal_act_evaluator",
        "sim2claw.learning_factory_components",
        "sim2claw.act_model",
    ),
    "LF-12": (
        "sim2claw.learning_factory_artifacts",
        "sim2claw.learning_factory_recursion",
    ),
    "LF-13": (
        "sim2claw.learning_factory_artifacts",
        "sim2claw.learning_factory_promotion",
        "sim2claw.learning_factory_components",
        "sim2claw.orchestrator_skills",
    ),
}
STAGE_EXTERNAL_TOOLS: dict[str, tuple[str, ...]] = {
    "LF-01": ("ffmpeg", "ffprobe", "colmap", "brush"),
}
RESOURCE_CLEANUP_STAGES = frozenset({"LF-01", "LF-06", "LF-10", "LF-11"})
DEPENDENCY_TERMINAL_STATUSES: dict[tuple[str, str], frozenset[str]] = {
    ("LF-12", "LF-11"): frozenset({"passed", "terminal_negative"}),
}
CAMPAIGN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class LearningFactoryError(RuntimeError):
    """Raised when execution cannot preserve the factory contract."""


@dataclass(frozen=True)
class FactoryContext:
    project_path: Path
    project: dict[str, Any]
    project_manifest: dict[str, Any]
    graph_path: Path
    graph: dict[str, Any]
    profile: str
    campaign_id: str
    generation: int
    parent_generation: int | None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _inside(repo_root: Path, declared: str, *, label: str) -> Path:
    path = Path(declared)
    if not declared or path.is_absolute() or ".." in path.parts:
        raise LearningFactoryError(f"{label} must be repo-relative: {declared!r}")
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        raise LearningFactoryError(f"{label} escapes the repository: {declared}")
    return resolved


def validate_stage_graph(graph: dict[str, Any]) -> dict[str, Any]:
    if graph.get("schema_version") != GRAPH_SCHEMA:
        raise LearningFactoryError("unsupported learning-factory graph schema")
    stages = graph.get("stages")
    if not isinstance(stages, list):
        raise LearningFactoryError("learning-factory graph stages must be a list")
    observed = tuple(str(stage.get("stage_id")) for stage in stages if isinstance(stage, dict))
    if observed != STAGE_IDS:
        raise LearningFactoryError(
            f"learning-factory graph must contain ordered LF-00 through LF-13, observed {observed!r}"
        )
    seen: set[str] = set()
    for index, stage in enumerate(stages):
        required = {
            "stage_id",
            "name",
            "purpose",
            "dependencies",
            "output_contract",
            "verdict_owner",
            "codex_action",
            "next_stage",
        }
        if set(stage) != required:
            raise LearningFactoryError(
                f"stage {stage.get('stage_id')} keys mismatch: expected {sorted(required)!r}"
            )
        dependencies = stage["dependencies"]
        if not isinstance(dependencies, list) or any(item not in seen for item in dependencies):
            raise LearningFactoryError(
                f"stage {stage['stage_id']} has a missing or forward dependency"
            )
        expected_next = STAGE_IDS[index + 1] if index + 1 < len(STAGE_IDS) else None
        if stage["next_stage"] != expected_next:
            raise LearningFactoryError(f"stage {stage['stage_id']} has an invalid next stage")
        seen.add(stage["stage_id"])
    for edge in graph.get("recursive_edges", []):
        if not isinstance(edge, dict) or edge.get("from") not in seen or edge.get("to") not in seen:
            raise LearningFactoryError("learning-factory recursive edge is invalid")
    return graph


class LearningFactory:
    """Resolve, execute, resume, and explain one immutable project graph."""

    def __init__(
        self,
        project_path: Path,
        *,
        repo_root: Path = REPO_ROOT,
        generation: int | None = None,
        parent_generation: int | None = None,
    ):
        self.repo_root = repo_root.resolve()
        try:
            project = inspect_project(project_path, repo_root=self.repo_root)
        except ProjectBundleError as error:
            raise LearningFactoryError(str(error)) from error
        resolved_project = _inside(
            self.repo_root, project["project_path"], label="project manifest"
        )
        manifest = load_json_object(resolved_project, label="project manifest")
        declaration = manifest.get("learning_factory")
        if not isinstance(declaration, dict):
            raise LearningFactoryError("project has no learning_factory declaration")
        graph_path = _inside(
            self.repo_root, str(declaration.get("graph", "")), label="factory graph"
        )
        graph = validate_stage_graph(load_json_object(graph_path, label="factory graph"))
        profile = str(declaration.get("profile", ""))
        if profile == "local_act_fixture":
            raise LearningFactoryError(
                "local_act_fixture is quarantined: its ACT checkpoint was trained on an "
                "internally generated rook dataset rather than the LF-09 dataset receipt"
            )
        if profile not in {"physical_campaign", "deterministic_fixture"}:
            raise LearningFactoryError(f"unsupported learning-factory profile: {profile!r}")
        campaign = declaration.get("campaign", {})
        if not isinstance(campaign, dict):
            raise LearningFactoryError("learning_factory campaign must be an object")
        campaign_id = str(campaign.get("campaign_id", "default"))
        if CAMPAIGN_ID_PATTERN.fullmatch(campaign_id) is None:
            raise LearningFactoryError(f"invalid learning-factory campaign id: {campaign_id!r}")
        try:
            declared_generation = int(campaign.get("generation", 0))
        except (TypeError, ValueError) as error:
            raise LearningFactoryError("learning-factory generation must be an integer") from error
        generation = declared_generation if generation is None else int(generation)
        if generation < 0:
            raise LearningFactoryError("learning-factory generation must be non-negative")
        raw_parent = (
            campaign.get("parent_generation")
            if parent_generation is None
            else parent_generation
        )
        try:
            parent_generation = None if raw_parent is None else int(raw_parent)
        except (TypeError, ValueError) as error:
            raise LearningFactoryError(
                "parent_generation must be an integer or null"
            ) from error
        if parent_generation is not None and not (0 <= parent_generation < generation):
            raise LearningFactoryError(
                "parent_generation must be non-negative and lower than generation"
            )
        self.context = FactoryContext(
            project_path=resolved_project,
            project=project,
            project_manifest=manifest,
            graph_path=graph_path,
            graph=graph,
            profile=profile,
            campaign_id=campaign_id,
            generation=generation,
            parent_generation=parent_generation,
        )
        self.root = (
            self.repo_root
            / "runs"
            / "learning-factory"
            / "projects"
            / project["project_id"]
            / "campaigns"
            / campaign_id
            / "generations"
            / f"{generation:04d}"
        )
        self._specs = {item["stage_id"]: item for item in graph["stages"]}
        self._identity_cache: dict[str, dict[str, Any]] = {}
        self._artifact_store = ContentAddressedArtifactStore(
            self.root / "artifacts", path_root=self.repo_root
        )

    def _adapter_descriptor(self, stage_id: str) -> AdapterDescriptor:
        spec = self._specs[stage_id]
        return AdapterDescriptor(
            stage_id=stage_id,
            dependencies=tuple(spec["dependencies"]),
            output_contract=str(spec["output_contract"]),
            verdict_owner=str(spec["verdict_owner"]),
            component_modules=STAGE_COMPONENT_MODULES[stage_id],
            external_tools=STAGE_EXTERNAL_TOOLS.get(stage_id, ()),
            cleanup_required=stage_id in RESOURCE_CLEANUP_STAGES,
        )

    def _stage_adapter(self, stage_id: str) -> FunctionStageAdapter:
        descriptor = self._adapter_descriptor(stage_id)
        return FunctionStageAdapter(
            descriptor=descriptor,
            function=lambda attempt_dir: self._execute_adapter(stage_id, attempt_dir),
        )

    def _implementation_identity(self, stage_id: str | None = None) -> dict[str, Any]:
        cache_key = stage_id or "all"
        cached = self._identity_cache.get(cache_key)
        if cached is not None:
            return cached
        if stage_id is None:
            modules = tuple(
                sorted({item for rows in STAGE_COMPONENT_MODULES.values() for item in rows})
            )
            tools = tuple(
                sorted({item for rows in STAGE_EXTERNAL_TOOLS.values() for item in rows})
            )
        else:
            descriptor = self._adapter_descriptor(stage_id)
            modules = descriptor.component_modules
            tools = descriptor.external_tools
        identity = build_implementation_identity(
            repo_root=self.repo_root,
            component_modules=modules,
            external_tools=tools,
        )
        self._identity_cache[cache_key] = identity
        return identity

    def _latest_path(self, stage_id: str) -> Path:
        return self.root / "stages" / stage_id / "latest.json"

    def _load_latest(self, stage_id: str) -> dict[str, Any] | None:
        path = self._latest_path(stage_id)
        if not path.is_file():
            return None
        result = load_json_object(path, label="factory stage result")
        self._validate_result(result, stage_id)
        return result

    def _validate_result(self, result: dict[str, Any], stage_id: str) -> None:
        expected = {
            "schema_version": STAGE_RESULT_SCHEMA,
            "project_id": self.context.project["project_id"],
            "project_path": self.context.project["project_path"],
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "stage_id": stage_id,
            "authority": PROJECT_AUTHORITY_CONTRACT,
        }
        for key, value in expected.items():
            if result.get(key) != value:
                raise LearningFactoryError(
                    f"saved {stage_id} result {key} mismatch: expected {value!r}, observed {result.get(key)!r}"
                )
        for digest_key in (
            "project_manifest_sha256",
            "evaluation_contract_sha256",
            "graph_sha256",
            "input_sha256",
        ):
            value = result.get(digest_key)
            if not isinstance(value, str) or len(value) != 64:
                raise LearningFactoryError(
                    f"saved {stage_id} result has an invalid {digest_key}"
                )
        if result.get("status") not in STAGE_STATUSES:
            raise LearningFactoryError(f"saved {stage_id} result has an invalid status")
        output = result.get("output")
        reference = result.get("output_ref")
        if output is None:
            if reference is not None or result.get("output_sha256") is not None:
                raise LearningFactoryError(
                    f"saved {stage_id} null output has an artifact reference"
                )
        else:
            if not isinstance(output, dict) or not isinstance(reference, dict):
                raise LearningFactoryError(
                    f"saved {stage_id} output or artifact reference is invalid"
                )
            try:
                artifact_path = self._artifact_store.verify(reference)
                artifact_value = load_json_object(
                    artifact_path, label=f"{stage_id} content-addressed output"
                )
            except (FactoryArtifactError, OSError, ValueError) as error:
                raise LearningFactoryError(str(error)) from error
            if artifact_value != output:
                raise LearningFactoryError(
                    f"saved {stage_id} embedded output differs from immutable artifact"
                )
            if result.get("output_sha256") != reference.get("sha256"):
                raise LearningFactoryError(
                    f"saved {stage_id} output digest differs from artifact reference"
                )
        unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
        if result.get("result_sha256") != canonical_digest(unsigned):
            raise LearningFactoryError(f"saved {stage_id} result digest mismatch")

    def _dependency_results(self, stage_id: str) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for dependency in self._specs[stage_id]["dependencies"]:
            latest = self._load_latest(dependency)
            if latest is not None:
                results[dependency] = latest
        return results

    def _dependency_passed(
        self, stage_id: str, dependency: str, result: dict[str, Any]
    ) -> bool:
        accepted = DEPENDENCY_TERMINAL_STATUSES.get(
            (stage_id, dependency), frozenset({"passed"})
        )
        return str(result.get("status")) in accepted

    def _input_digest(self, stage_id: str) -> str:
        dependencies = self._dependency_results(stage_id)
        declaration = self.context.project_manifest["learning_factory"]
        payload = {
            "project_manifest_sha256": self.context.project["project_manifest_sha256"],
            "evaluation_contract_sha256": self.context.project[
                "evaluation_contract_sha256"
            ],
            "graph_sha256": sha256_file(self.context.graph_path),
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "parent_generation": self.context.parent_generation,
            "stage": self._specs[stage_id],
            "factory_declaration": declaration,
            "dependencies": {
                key: value["result_sha256"] for key, value in sorted(dependencies.items())
            },
            "implementation": self._implementation_identity(stage_id)["sha256"],
        }
        return canonical_digest(payload)

    def _card(self, stage_id: str) -> dict[str, Any]:
        spec = self._specs[stage_id]
        dependencies = self._dependency_results(stage_id)
        blockers: list[str] = []
        for dependency in spec["dependencies"]:
            result = dependencies.get(dependency)
            if result is None:
                blockers.append(f"{dependency} has no result")
            elif not self._dependency_passed(stage_id, dependency, result):
                blockers.append(f"{dependency} is {result['status']}")
        latest = self._load_latest(stage_id)
        current_input_digest = self._input_digest(stage_id)
        if latest is not None and latest["input_sha256"] == current_input_digest:
            status = latest["status"]
            latest_evidence = latest.get("result_path")
            blockers.extend(str(item) for item in latest.get("blockers", []))
        elif latest is not None:
            status = "superseded"
            latest_evidence = latest.get("result_path")
            blockers.append("stage inputs or implementation changed since the latest attempt")
        elif blockers:
            status = "not_ready"
            latest_evidence = None
        else:
            status = "ready"
            latest_evidence = None
        return {
            "stage": stage_id,
            "name": spec["name"],
            "purpose": spec["purpose"],
            "status": status,
            "required_inputs": list(spec["dependencies"]),
            "latest_input_sha256": current_input_digest,
            "output_contract": spec["output_contract"],
            "verdict_owner": spec["verdict_owner"],
            "latest_evidence": latest_evidence,
            "blockers": blockers,
            "available_codex_action": spec["codex_action"],
            "next_stage_when_passed": spec["next_stage"],
            "resume_command": (
                f"uv run sim2claw factory-run --project {self.context.project['project_path']} "
                f"--generation {self.context.generation} "
                + (
                    f"--parent-generation {self.context.parent_generation} "
                    if self.context.parent_generation is not None
                    else ""
                )
                + f"--from {stage_id} --through {stage_id}"
            ),
        }

    def inspect(self) -> dict[str, Any]:
        from .doctor import run_doctor

        cards = [self._card(stage_id) for stage_id in STAGE_IDS]
        declared_target = self.context.project_manifest["learning_factory"].get(
            "doctor_target"
        )
        doctor_target = str(
            declared_target
            or ("mac" if platform.system() == "Darwin" else "linux-cpu")
        )
        doctor = run_doctor(target=doctor_target, render_probe=False)
        unsigned = {
            "schema_version": INSPECTION_SCHEMA,
            "project": self.context.project,
            "factory_profile": self.context.profile,
            "graph_id": self.context.graph["graph_id"],
            "graph_sha256": sha256_file(self.context.graph_path),
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "parent_generation": self.context.parent_generation,
            "implementation": self._implementation_identity(),
            "doctor": doctor,
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
            "stages": cards,
        }
        return {**unsigned, "inspection_sha256": canonical_digest(unsigned)}

    def status(self) -> dict[str, Any]:
        cards = [self._card(stage_id) for stage_id in STAGE_IDS]
        next_ready = next((item["stage"] for item in cards if item["status"] == "ready"), None)
        first_unpassed = next((item for item in cards if item["status"] != "passed"), None)
        return {
            "schema_version": STATUS_SCHEMA,
            "project_id": self.context.project["project_id"],
            "project_path": self.context.project["project_path"],
            "graph_id": self.context.graph["graph_id"],
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "parent_generation": self.context.parent_generation,
            "next_ready_stage": next_ready,
            "current_stage": first_unpassed["stage"] if first_unpassed else None,
            "overall_status": "passed" if first_unpassed is None else first_unpassed["status"],
            "stages": cards,
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        }

    def explain(self, stage_id: str) -> dict[str, Any]:
        if stage_id not in self._specs:
            raise LearningFactoryError(f"unknown learning-factory stage: {stage_id}")
        card = self._card(stage_id)
        latest = self._load_latest(stage_id)
        return {
            "schema_version": "sim2claw.learning_factory_explanation.v1",
            **card,
            "latest_result": latest,
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        }

    def _write_result(
        self,
        stage_id: str,
        attempt_id: str,
        input_sha256: str,
        payload: dict[str, Any],
        attempt_dir: Path,
        *,
        started_at: str,
    ) -> dict[str, Any]:
        status = str(payload.get("status", ""))
        if status not in STAGE_STATUSES or status in {"ready", "running", "superseded"}:
            raise LearningFactoryError(f"stage adapter returned invalid terminal status: {status}")
        output = payload.get("output")
        if output is not None and not isinstance(output, dict):
            raise LearningFactoryError("stage adapter output must be an object or null")
        output_ref = self._artifact_store.put_json(output) if output is not None else None
        output_sha256 = output_ref["sha256"] if output_ref is not None else None
        relative_result = (
            attempt_dir / "stage_result.json"
        ).relative_to(self.repo_root).as_posix()
        unsigned = {
            "schema_version": STAGE_RESULT_SCHEMA,
            "project_id": self.context.project["project_id"],
            "project_path": self.context.project["project_path"],
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "parent_generation": self.context.parent_generation,
            "project_manifest_sha256": self.context.project["project_manifest_sha256"],
            "evaluation_set_id": self.context.project["evaluation_set_id"],
            "evaluation_contract_sha256": self.context.project[
                "evaluation_contract_sha256"
            ],
            "graph_sha256": sha256_file(self.context.graph_path),
            "stage_id": stage_id,
            "attempt_id": attempt_id,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "status": status,
            "summary": str(payload.get("summary", "")),
            "blockers": list(payload.get("blockers", [])),
            "output": output,
            "output_ref": output_ref,
            "proof_class": str(payload.get("proof_class", "fixture")),
            "diagnostics": dict(payload.get("diagnostics", {})),
            "verdict_owner": self._specs[stage_id]["verdict_owner"],
            "adapter": asdict(self._adapter_descriptor(stage_id)),
            "implementation": self._implementation_identity(stage_id),
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
            "physical_authority": False,
            "robot_motion_allowed": False,
            "result_path": relative_result,
        }
        result = {**unsigned, "result_sha256": canonical_digest(unsigned)}
        atomic_write_json(attempt_dir / "stage_result.json", result)
        atomic_write_json(self._latest_path(stage_id), result)
        return result

    def _write_terminal_attempt(
        self,
        attempt_dir: Path,
        *,
        stage_id: str,
        attempt_id: str,
        input_sha256: str,
        started_at: str,
        result: dict[str, Any],
    ) -> None:
        atomic_write_json(
            attempt_dir / "attempt.json",
            {
                "schema_version": ATTEMPT_SCHEMA,
                "project_id": self.context.project["project_id"],
                "campaign_id": self.context.campaign_id,
                "generation": self.context.generation,
                "stage_id": stage_id,
                "attempt_id": attempt_id,
                "status": result["status"],
                "input_sha256": input_sha256,
                "started_at": started_at,
                "finished_at": result["finished_at"],
                "result_path": result["result_path"],
                "result_sha256": result["result_sha256"],
            },
        )

    def run_stage(self, stage_id: str, *, force: bool = False) -> dict[str, Any]:
        if stage_id not in self._specs:
            raise LearningFactoryError(f"unknown learning-factory stage: {stage_id}")
        card = self._card(stage_id)
        if card["status"] == "passed" and not force:
            latest = self._load_latest(stage_id)
            assert latest is not None
            return {**latest, "reused": True}
        input_sha256 = self._input_digest(stage_id)
        attempt_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:10]}"
        attempt_dir = self.root / "stages" / stage_id / "attempts" / attempt_id
        lease = StageLease(
            self.root / "leases" / f"{stage_id}.json",
            stage_id=stage_id,
            attempt_id=attempt_id,
        )
        try:
            lease.acquire()
        except RuntimeError as error:
            raise LearningFactoryError(str(error)) from error
        started_at = _utc_now()
        atomic_write_json(
            attempt_dir / "attempt.json",
            {
                "schema_version": ATTEMPT_SCHEMA,
                "project_id": self.context.project["project_id"],
                "campaign_id": self.context.campaign_id,
                "generation": self.context.generation,
                "stage_id": stage_id,
                "attempt_id": attempt_id,
                "status": "running",
                "input_sha256": input_sha256,
                "started_at": started_at,
            },
        )
        result: dict[str, Any] | None = None
        try:
            blockers = []
            for dependency in self._specs[stage_id]["dependencies"]:
                dependency_result = self._load_latest(dependency)
                if dependency_result is None or not self._dependency_passed(
                    stage_id, dependency, dependency_result
                ):
                    blockers.append(
                        f"{dependency} is {dependency_result['status'] if dependency_result is not None else 'not_ready'}"
                    )
            if blockers:
                payload = {
                    "status": "not_ready",
                    "summary": "A required upstream stage has not passed.",
                    "blockers": blockers,
                    "output": None,
                    "proof_class": "workflow_control",
                }
            else:
                outcome = self._stage_adapter(stage_id).run(attempt_dir)
                payload = outcome.as_payload()
            result = self._write_result(
                stage_id,
                attempt_id,
                input_sha256,
                payload,
                attempt_dir,
                started_at=started_at,
            )
        except Exception as error:
            failed_outcome = StageOutcome(
                status="failed",
                summary=f"Stage execution contract failed: {error}",
                blockers=(type(error).__name__,),
                output=None,
                proof_class="workflow_control_failure",
                diagnostics={
                    "exception_type": type(error).__name__,
                    "exception_message": str(error),
                },
            )
            result = self._write_result(
                stage_id,
                attempt_id,
                input_sha256,
                failed_outcome.as_payload(),
                attempt_dir,
                started_at=started_at,
            )
        finally:
            if result is not None:
                self._write_terminal_attempt(
                    attempt_dir,
                    stage_id=stage_id,
                    attempt_id=attempt_id,
                    input_sha256=input_sha256,
                    started_at=started_at,
                    result=result,
                )
            lease.release()
        assert result is not None
        return result

    def run_range(self, start: str, through: str) -> dict[str, Any]:
        if start not in STAGE_IDS or through not in STAGE_IDS:
            raise LearningFactoryError("factory range uses an unknown stage")
        start_index, end_index = STAGE_IDS.index(start), STAGE_IDS.index(through)
        if start_index > end_index:
            raise LearningFactoryError("factory --from must not follow --through")
        results: list[dict[str, Any]] = []
        for stage_id in STAGE_IDS[start_index : end_index + 1]:
            result = self.run_stage(stage_id)
            results.append(result)
            if result["status"] != "passed":
                break
        return self._run_summary("range", results)

    def run_next(self) -> dict[str, Any]:
        status = self.status()
        stage_id = status["next_ready_stage"]
        if stage_id is None:
            return self._run_summary("next", [], message="No stage is currently ready.")
        return self._run_summary("next", [self.run_stage(stage_id)])

    def resume(self) -> dict[str, Any]:
        cards = self.status()["stages"]
        stage_id = next(
            (
                card["stage"]
                for card in cards
                if card["status"] in {"ready", "superseded", "failed", "blocked", "partial", "terminal_negative"}
            ),
            None,
        )
        if stage_id is None:
            return self._run_summary("resume", [], message="Nothing is resumable.")
        return self._run_summary("resume", [self.run_stage(stage_id, force=True)])

    def fork_generation(
        self,
        *,
        route_targets: list[str],
        through: str = "LF-11",
    ) -> dict[str, Any]:
        """Create a child generation, inherit immutable parents, and run its route."""

        allowed = {
            str(edge["to"])
            for edge in self.context.graph.get("recursive_edges", [])
            if edge.get("from") == "LF-12"
        }
        targets = sorted(set(route_targets), key=STAGE_IDS.index)
        if not targets or any(target not in allowed for target in targets):
            raise LearningFactoryError("recursion targets must be declared LF-12 graph edges")
        if through not in STAGE_IDS or STAGE_IDS.index(through) < STAGE_IDS.index(targets[0]):
            raise LearningFactoryError("recursion through-stage precedes its route target")
        child = LearningFactory(
            Path(self.context.project["project_path"]),
            repo_root=self.repo_root,
            generation=self.context.generation + 1,
            parent_generation=self.context.generation,
        )
        if child.root.exists() and any(child.root.iterdir()):
            raise LearningFactoryError("child generation already contains evidence")
        first = targets[0]
        inherited: list[dict[str, Any]] = []
        for stage_id in STAGE_IDS[: STAGE_IDS.index(first)]:
            parent_result = self._load_latest(stage_id)
            if parent_result is None or parent_result["status"] != "passed":
                raise LearningFactoryError(
                    f"cannot inherit {stage_id}; parent generation is not passed"
                )
            attempt_id = f"inherited-g{self.context.generation:04d}-{stage_id.lower()}"
            attempt_dir = child.root / "stages" / stage_id / "attempts" / attempt_id
            started = _utc_now()
            result = child._write_result(
                stage_id,
                attempt_id,
                child._input_digest(stage_id),
                {
                    "status": "passed",
                    "summary": (
                        f"Inherited immutable {stage_id} evidence from generation "
                        f"{self.context.generation}."
                    ),
                    "output": parent_result["output"],
                    "proof_class": "inherited_parent_generation_evidence",
                    "diagnostics": {
                        "parent_generation": self.context.generation,
                        "parent_result_sha256": parent_result["result_sha256"],
                    },
                },
                attempt_dir,
                started_at=started,
            )
            child._write_terminal_attempt(
                attempt_dir,
                stage_id=stage_id,
                attempt_id=attempt_id,
                input_sha256=result["input_sha256"],
                started_at=started,
                result=result,
            )
            inherited.append(
                {"stage_id": stage_id, "parent_result_sha256": parent_result["result_sha256"]}
            )
        recursion = {
            "schema_version": "sim2claw.learning_factory_recursion.v1",
            "campaign_id": self.context.campaign_id,
            "parent_generation": self.context.generation,
            "generation": child.context.generation,
            "route_targets": targets,
            "first_stage": first,
            "through_stage": through,
            "inherited": inherited,
        }
        atomic_write_json(child.root / "recursion.json", recursion)
        run = child.run_range(first, through)
        return {**recursion, "run": run}

    def _run_summary(
        self,
        mode: str,
        results: list[dict[str, Any]],
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        unsigned = {
            "schema_version": RUN_SCHEMA,
            "project_id": self.context.project["project_id"],
            "campaign_id": self.context.campaign_id,
            "generation": self.context.generation,
            "mode": mode,
            "message": message,
            "results": results,
            "final_status": results[-1]["status"] if results else self.status()["overall_status"],
            "next_ready_stage": self.status()["next_ready_stage"],
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        }
        return {**unsigned, "run_sha256": canonical_digest(unsigned)}

    def _dependency_output(self, stage_id: str) -> dict[str, Any]:
        result = self._load_latest(stage_id)
        if result is None or result["status"] != "passed" or not isinstance(result.get("output"), dict):
            raise LearningFactoryError(f"dependency {stage_id} has no passed object output")
        return result["output"]

    def _execute_adapter(self, stage_id: str, attempt_dir: Path) -> dict[str, Any]:
        if stage_id == "LF-00":
            inspection = self.inspect()
            if inspection["doctor"]["passed"] is not True:
                failed_checks = [
                    item["name"]
                    for item in inspection["doctor"]["checks"]
                    if item["passed"] is not True
                ]
                return {
                    "status": "blocked",
                    "summary": "The target-appropriate runtime doctor did not pass.",
                    "blockers": [f"doctor check failed: {name}" for name in failed_checks],
                    "output": inspection,
                    "proof_class": "contract_inspection",
                }
            return {
                "status": "passed",
                "summary": "Project, evaluator, graph, and exact authority contract agree.",
                "output": inspection,
                "proof_class": "contract_inspection",
            }
        if self.context.profile == "physical_campaign":
            return self._execute_physical(stage_id, attempt_dir)
        return self._execute_fixture(stage_id, attempt_dir)

    def _execute_physical(self, stage_id: str, attempt_dir: Path) -> dict[str, Any]:
        declaration = self.context.project_manifest["learning_factory"]
        if stage_id == "LF-01":
            from .learning_factory_components import execute_visual_context

            visual = declaration.get("visual_context")
            if not isinstance(visual, dict):
                return {
                    "status": "blocked",
                    "summary": "Visual-context declaration is missing.",
                    "blockers": ["learning_factory.visual_context must be an object"],
                    "output": None,
                    "proof_class": "visual_context_only",
                }
            output = execute_visual_context(
                visual, repo_root=self.repo_root, attempt_dir=attempt_dir
            )
            return {
                "status": "passed",
                "summary": (
                    "Visual context was executed or hash-verified without granting metric authority."
                    if output["mode"] != "not_provided_optional"
                    else "Optional visual context is absent; the declared repo-native twin remains independent."
                ),
                "output": output,
                "proof_class": "visual_context_only",
            }
        if stage_id == "LF-02":
            from .learning_factory_components import build_twin_candidate

            twin = declaration["twin_candidate"]
            if not isinstance(twin, dict):
                raise LearningFactoryError("twin_candidate must be an object")
            output = build_twin_candidate(
                twin,
                repo_root=self.repo_root,
                implementation_sha256=self._implementation_identity("LF-02")["sha256"],
            )
            return {
                "status": "passed",
                "summary": "Twin candidate dependencies, uncertainties, and authorship are identity-bound.",
                "output": output,
                "proof_class": "simulation_candidate",
            }
        if stage_id == "LF-03":
            from .learning_factory_components import validate_twin_candidate

            output = validate_twin_candidate(
                self._dependency_output("LF-02"),
                repo_root=self.repo_root,
                attempt_dir=attempt_dir,
            )
            return {
                "status": "passed" if output["passed"] else "terminal_negative",
                "summary": (
                    "Twin candidate passed compile, dynamics, geometry, camera, render, and identity gates."
                    if output["passed"]
                    else "Twin candidate completed validation but failed one or more frozen gates."
                ),
                "blockers": [
                    f"twin validation gate failed: {name}"
                    for name, passed in output["gates"].items()
                    if not passed
                ],
                "output": output,
                "proof_class": "simulation_validation",
            }
        if stage_id == "LF-04":
            from .learning_factory_components import (
                inspect_canonical_source_episodes,
                inspect_demonstration_inputs,
            )

            catalog_path = _inside(
                self.repo_root,
                self.context.project["physical_source_catalog"],
                label="physical source catalog",
            )
            replay_declaration = declaration.get("replay")
            if not isinstance(replay_declaration, dict):
                raise LearningFactoryError("learning_factory.replay must be an object")
            config_path = _inside(
                self.repo_root,
                str(replay_declaration.get("sysid_config", "")),
                label="system-identification config",
            )
            report = inspect_demonstration_inputs(
                catalog_path=catalog_path,
                config_path=config_path,
                repo_root=self.repo_root,
                output_path=attempt_dir / "demonstration_input_report.json",
            )
            canonical_directories = declaration.get("canonical_source_episodes", [])
            if not isinstance(canonical_directories, list) or any(
                not isinstance(item, str) for item in canonical_directories
            ):
                raise LearningFactoryError(
                    "canonical_source_episodes must be a list of repo-relative directories"
                )
            canonical_inventory = inspect_canonical_source_episodes(
                canonical_directories, repo_root=self.repo_root
            )
            output = {
                "schema_version": "sim2claw.factory_source_catalog.v1",
                "catalog": self.context.project["physical_source_catalog"],
                "catalog_sha256": sha256_file(catalog_path),
                "source_mode": declaration["source_mode"],
                "normalization_repairs_applied": 0,
                "training_admitted": False,
                "canonical_source_inventory": canonical_inventory,
                "input_report": report,
            }
            return {
                "status": "passed",
                "summary": "Every declared demonstration payload was parsed, hash-audited, and normalized into an explicit readiness inventory.",
                "output": output,
                "proof_class": "physical_source_catalog_unqualified",
            }
        if stage_id == "LF-05":
            from .learning_factory_components import freeze_and_replay_ready_episodes

            source_inventory = self._dependency_output("LF-04")
            report = source_inventory["input_report"]
            ready_count = int(report.get("joint_replay_ready_episode_count", 0))
            transform = report.get("physical_joint_transform") or {}
            transform_status = str(transform.get("review_status", "missing"))
            minimum_ready = int(
                (declaration.get("replay") or {}).get("minimum_ready_episodes", 2)
            )
            blockers: list[str] = []
            if ready_count < minimum_ready:
                blockers.append(
                    f"exact joint/timing replay-ready episodes {ready_count}/{minimum_ready} required"
                )
            if transform.get("calibration_approved") is not True:
                blockers.append(f"joint transform is {transform_status}")
            limits = report.get("aggregate_joint_limit_validation") or {}
            if limits.get("all_audited_values_within_limits") is not True:
                measured = (limits.get("measured_trajectory") or {})
                commands = (limits.get("recorded_commands") or {})
                blockers.append(
                    "joint/control range audit failed: "
                    f"{measured.get('violating_row_count', 0)} measured and "
                    f"{commands.get('violating_row_count', 0)} command rows violate limits"
                )
            if blockers:
                return {
                    "status": "blocked",
                    "summary": "Current physical demonstrations cannot yet identify or validate calibration.",
                    "blockers": blockers,
                    "output": {
                        "schema_version": "sim2claw.factory_replay_readiness.v1",
                        "input_report_sha256": canonical_digest(report),
                        "ready_episode_count": ready_count,
                        "minimum_ready_episode_count": minimum_ready,
                        "joint_transform_status": transform_status,
                        "aggregate_joint_limit_validation": limits,
                        "aggregate_observable_status": report.get(
                            "aggregate_observable_status"
                        ),
                        "held_out_rows_opened": 0,
                        "split_frozen": False,
                    },
                    "proof_class": "physical_read_only_readiness",
                }
            replay_declaration = declaration["replay"]
            catalog_path = _inside(
                self.repo_root,
                self.context.project["physical_source_catalog"],
                label="physical source catalog",
            )
            config_path = _inside(
                self.repo_root,
                replay_declaration["sysid_config"],
                label="system-identification config",
            )
            output = freeze_and_replay_ready_episodes(
                catalog_path=catalog_path,
                config_path=config_path,
                output_directory=attempt_dir / "replay",
                repo_root=self.repo_root,
                strategy=str(replay_declaration.get("split_strategy", "deterministic_hash")),
                held_out_column=replay_declaration.get("held_out_column"),
            )
            return {
                "status": "passed",
                "summary": "Every admitted episode passed exact replay and an evaluator-owned whole-episode split was frozen.",
                "output": output,
                "proof_class": "physical_read_only_replay",
            }
        if stage_id == "LF-06":
            from .learning_factory_components import run_calibration_fit

            replay = self._dependency_output("LF-05")
            split_path = _inside(
                self.repo_root,
                str(replay["split_manifest_path"]),
                label="split manifest",
            )
            replay_declaration = declaration["replay"]
            config_path = _inside(
                self.repo_root,
                str(replay_declaration["sysid_config"]),
                label="system-identification config",
            )
            twin = self._dependency_output("LF-03")
            output = run_calibration_fit(
                split_manifest_path=split_path,
                config_path=config_path,
                output_directory=attempt_dir / "system_identification",
                repo_root=self.repo_root,
                baseline_twin_id=str(twin["twin_candidate_id"]),
                backend=str(replay_declaration.get("sysid_backend", "auto")),
            )
            return {
                "status": "passed",
                "summary": "Bounded system identification completed and produced an immutable, unpromoted twin candidate.",
                "output": output,
                "proof_class": "replay_calibration_candidate",
            }
        if stage_id == "LF-07":
            from .learning_factory_components import (
                run_independent_calibration_evaluator,
            )

            fit = self._dependency_output("LF-06")
            evaluation = run_independent_calibration_evaluator(
                split_manifest_path=_inside(
                    self.repo_root,
                    str(fit["split_manifest_path"]),
                    label="split manifest",
                ),
                config_path=_inside(
                    self.repo_root,
                    str(fit["sysid_config_path"]),
                    label="system-identification config",
                ),
                fit_receipt_path=_inside(
                    self.repo_root,
                    str(fit["fit_receipt_path"]),
                    label="fit receipt",
                ),
                output_directory=attempt_dir / "independent_evaluation",
                repo_root=self.repo_root,
            )
            output = {
                "schema_version": "sim2claw.factory_calibration_comparison.v1",
                "baseline_twin_id": fit["baseline_twin_id"],
                "candidate_twin_id": fit["candidate_twin_id"],
                "evaluation": evaluation,
                "verdict": evaluation["verdict"],
                "reasons": list(evaluation.get("reasons", [])),
                "verdict_owner": evaluation["evaluator_owner"],
            }
            admitted = output["verdict"] == "admitted"
            return {
                "status": "passed" if admitted else "terminal_negative",
                "summary": (
                    "Independent held-out calibration evaluation admitted the candidate."
                    if admitted
                    else "Independent held-out calibration evaluation rejected the candidate."
                ),
                "blockers": list(output.get("reasons", [])),
                "output": output,
                "proof_class": "independent_calibration_evaluation",
            }
        if stage_id == "LF-08":
            from .learning_factory_goal_data import compile_goal_act_curriculum

            curriculum = declaration.get("curriculum")
            if not isinstance(curriculum, dict):
                return {
                    "status": "blocked",
                    "summary": "No bounded cousin curriculum is declared.",
                    "blockers": ["learning_factory.curriculum must be an object"],
                    "output": None,
                    "proof_class": "simulation_curriculum_plan",
                }
            sources = curriculum.get("admitted_source_episodes")
            if not isinstance(sources, list) or not sources:
                return {
                    "status": "blocked",
                    "summary": "Cousin compilation has no evaluator-admitted source episode.",
                    "blockers": [
                        "at least one admitted B-G-compatible source episode with segment lineage is required"
                    ],
                    "output": {
                        "schema_version": "sim2claw.goal_act_curriculum_blocker.v1",
                        "task_contract": curriculum.get("task_contract"),
                        "admitted_source_episode_count": 0,
                        "held_out_rows_opened": 0,
                    },
                    "proof_class": "simulation_curriculum_plan",
                }
            task_path = _inside(
                self.repo_root,
                str(curriculum.get("task_contract", "")),
                label="goal-conditioned ACT task contract",
            )
            comparison = self._dependency_output("LF-07")
            output = compile_goal_act_curriculum(
                parent_twin_id=str(comparison["candidate_twin_id"]),
                source_episodes=sources,
                maximum_candidates=int(curriculum.get("maximum_candidates", 8)),
                generation=self.context.generation,
                task_contract_path=task_path,
            )
            return {
                "status": "passed",
                "summary": "Training-only pose, target, seed, and distractor coverage was compiled without opening held-outs.",
                "output": output,
                "proof_class": "simulation_curriculum_plan",
            }
        if stage_id == "LF-09":
            from .learning_factory_goal_data import build_goal_act_dataset

            curriculum_declaration = declaration.get("curriculum") or {}
            executions = curriculum_declaration.get("candidate_executions")
            if not isinstance(executions, list) or not executions:
                return {
                    "status": "blocked",
                    "summary": "The curriculum has no generated candidate episodes to replay and evaluate.",
                    "blockers": [
                        "candidate_executions must bind generated episode directories and planner/IK lineage"
                    ],
                    "output": None,
                    "proof_class": "simulation_dataset_admission",
                }
            output = build_goal_act_dataset(
                self._dependency_output("LF-08"),
                executions=executions,
                output_directory=attempt_dir / "goal_act_dataset",
                task_contract_path=_inside(
                    self.repo_root,
                    str(curriculum_declaration.get("task_contract", "")),
                    label="goal-conditioned ACT task contract",
                ),
            )
            accepted = int(output["accepted_count"])
            return {
                "status": "passed" if accepted else "terminal_negative",
                "summary": (
                    "Strict replay/evaluation admitted an immutable ACT and GR00T dataset."
                    if accepted
                    else "Every generated cousin was retained as a strict evaluator rejection."
                ),
                "blockers": (
                    [] if accepted else ["no candidate passed strict replay and consequence evaluation"]
                ),
                "output": output,
                "proof_class": "simulation_dataset_admission",
            }
        if stage_id == "LF-10":
            from .goal_act_training import train_goal_act

            training = declaration.get("training")
            if not isinstance(training, dict):
                raise LearningFactoryError("learning_factory.training must be an object")
            dataset = self._dependency_output("LF-09")
            receipt_path = Path(str(dataset.get("dataset_receipt_path") or "")).resolve()
            if not receipt_path.is_relative_to(self.repo_root.resolve()):
                raise LearningFactoryError("LF-09 dataset receipt escaped the repository")
            output = train_goal_act(
                dataset_receipt_path=receipt_path,
                output_directory=attempt_dir / "goal_act_training",
                recipe_path=_inside(
                    self.repo_root,
                    str(training.get("recipe", "")),
                    label="goal ACT training recipe",
                ),
                task_contract_path=_inside(
                    self.repo_root,
                    str((declaration.get("curriculum") or {}).get("task_contract", "")),
                    label="goal ACT task contract",
                ),
            )
            return {
                "status": "passed",
                "summary": "ACT training consumed the exact LF-09 immutable dataset and atomically captured its checkpoint.",
                "output": output,
                "proof_class": "simulation_goal_conditioned_policy_candidate",
            }
        if stage_id == "LF-11":
            from .learning_factory_components import run_independent_goal_act_evaluator

            training = self._dependency_output("LF-10")
            declaration_training = declaration.get("training") or {}
            cohort_text = str(declaration_training.get("evaluation_cohort", ""))
            if not cohort_text:
                return {
                    "status": "blocked",
                    "summary": "No sealed goal-conditioned evaluation cohort is declared.",
                    "blockers": ["learning_factory.training.evaluation_cohort is required"],
                    "output": None,
                    "proof_class": "independent_goal_conditioned_policy_evaluation",
                }
            output = run_independent_goal_act_evaluator(
                checkpoint_path=Path(training["checkpoint_path"]),
                training_receipt_path=Path(training["checkpoint_path"]).parent
                / "training_receipt.json",
                cohort_path=_inside(
                    self.repo_root,
                    cohort_text,
                    label="sealed goal ACT evaluation cohort",
                ),
                task_contract_path=_inside(
                    self.repo_root,
                    str((declaration.get("curriculum") or {}).get("task_contract", "")),
                    label="goal ACT task contract",
                ),
                output_directory=attempt_dir / "independent_policy_evaluation",
                repo_root=self.repo_root,
            )
            admitted = output["verdict"] == "admitted"
            return {
                "status": "passed" if admitted else "terminal_negative",
                "summary": (
                    "The separate CPU/fp32 evaluator admitted the goal-conditioned checkpoint."
                    if admitted
                    else "The separate CPU/fp32 evaluator retained the checkpoint as terminal-negative."
                ),
                "blockers": (
                    [] if admitted else ["goal-conditioned held-out consequence gate failed"]
                ),
                "output": output,
                "proof_class": "independent_goal_conditioned_policy_evaluation",
            }
        if stage_id == "LF-12":
            from .learning_factory_recursion import (
                attach_corrections,
                persist_counterexample_registry,
            )

            evaluation = self._dependency_output("LF-11")
            recursion_declaration = declaration.get("recursion") or {}
            previous_text = str(recursion_declaration.get("previous_registry") or "")
            registry = persist_counterexample_registry(
                evaluation,
                output_path=attempt_dir / "counterexample_registry.json",
                previous_registry_path=(
                    _inside(
                        self.repo_root,
                        previous_text,
                        label="previous counterexample registry",
                    )
                    if previous_text
                    else None
                ),
            )
            corrections = recursion_declaration.get("correction_candidates", [])
            if not isinstance(corrections, list):
                raise LearningFactoryError("correction_candidates must be a list")
            if corrections:
                registry = attach_corrections(registry, corrections)
                atomic_write_json(attempt_dir / "counterexample_registry.json", registry)
            output = {
                **registry,
                "registry_path": (
                    attempt_dir / "counterexample_registry.json"
                ).relative_to(self.repo_root).as_posix(),
                "registry_file_sha256": sha256_file(
                    attempt_dir / "counterexample_registry.json"
                ),
                "parent_generation": self.context.generation,
                "next_generation": self.context.generation + 1,
            }
            return {
                "status": "passed",
                "summary": (
                    "Evaluator failures were deduplicated and routed with zero raw training rows."
                    if output["counterexample_count"]
                    else "The evaluator produced no counterexamples; the empty registry is persisted."
                ),
                "output": output,
                "proof_class": "trace_native_counterexample_registry",
            }
        if stage_id == "LF-13":
            from .learning_factory_components import run_independent_promotion

            required_stages = ("LF-03", "LF-07", "LF-09", "LF-10", "LF-11", "LF-12")
            stage_results: dict[str, dict[str, Any]] = {}
            for required_stage in required_stages:
                result = self._load_latest(required_stage)
                if result is None:
                    raise LearningFactoryError(
                        f"promotion input is missing {required_stage}"
                    )
                stage_results[required_stage] = result
            output = run_independent_promotion(
                project_path=self.context.project_path,
                stage_results=stage_results,
                task_contract_path=_inside(
                    self.repo_root,
                    str((declaration.get("curriculum") or {}).get("task_contract", "")),
                    label="goal ACT task contract",
                ),
                output_directory=attempt_dir / "promotion",
                repo_root=self.repo_root,
            )
            return {
                "status": "passed",
                "summary": (
                    "Independent promotion published an exact simulation-only skill package."
                    if output["state"] == "promoted"
                    else "Independent promotion issued an authenticated rejection; no skill package was published."
                ),
                "blockers": list(output.get("reasons", [])),
                "output": output,
                "proof_class": "independent_promotion_decision",
            }
        return {
            "status": "blocked",
            "summary": "The physical campaign has not supplied the admitted upstream artifact for this stage.",
            "blockers": [f"{self._specs[stage_id]['dependencies'][0]} must pass with eligible physical evidence"],
            "output": None,
            "proof_class": "physical_campaign_control",
        }

    def _execute_fixture(self, stage_id: str, attempt_dir: Path) -> dict[str, Any]:
        project_id = self.context.project["project_id"]
        if stage_id == "LF-01":
            output = {"reconstruction_id": "fixture-3dgs-v1", "relative_scale_only": True, "metric_authority": False, "collision_authority": False}
        elif stage_id == "LF-02":
            output = {"twin_candidate_id": "fixture-baseline-twin-v1", "authored_by": "Codex", "accepted": False, "uncertain_parameters": ["contact_friction", "actuator_damping"]}
        elif stage_id == "LF-03":
            output = {"twin_candidate_id": "fixture-baseline-twin-v1", "compiled": True, "finite": True, "validation_owner": "twin_validator"}
        elif stage_id == "LF-04":
            output = {"catalog_id": "fixture-canonical-sources-v1", "episode_ids": ["cal-1", "cal-2", "val-1", "held-1"], "conflicts": [], "silent_repairs": 0}
        elif stage_id == "LF-05":
            output = {"split_id": "fixture-split-v1", "calibration_episode_ids": ["cal-1", "cal-2"], "validation_episode_ids": ["val-1"], "held_out_episode_ids": ["held-1"], "held_out_rows_opened": 0, "exact_replay_ready_count": 3}
        elif stage_id == "LF-06":
            output = {
                "schema_version": "sim2claw.calibration_experiment.v1",
                "experiment_id": "fixture-calibration-v1",
                "baseline_twin_id": "fixture-baseline-twin-v1",
                "candidate_twin_id": "fixture-calibrated-twin-v2",
                "calibration_episode_ids": ["cal-1", "cal-2"],
                "validation_episode_ids": ["val-1"],
                "held_out_episode_ids": ["held-1"],
                "minimum_normalized_sensitivity": 0.05,
                "minimum_improved_fidelity_metrics": 3,
                "regression_tolerance": 0.0,
                "parameters": [
                    {"name": "contact_friction", "lower": 0.4, "upper": 1.2, "normalized_sensitivity": 0.31},
                    {"name": "actuator_damping", "lower": 0.01, "upper": 0.2, "normalized_sensitivity": 0.18},
                ],
                "fit_used_roles": ["calibration"],
            }
        elif stage_id == "LF-07":
            experiment = self._dependency_output("LF-06")
            baseline = {"twin_id": "fixture-baseline-twin-v1", "evaluated_episode_ids": ["val-1"], "trajectory_rmse": 0.08, "contact_timing_mae": 0.06, "outcome_disagreement_rate": 0.4, "sim_real_success_gap": 0.35, "simulated_policy_success_rate": 0.9}
            candidate = {"twin_id": "fixture-calibrated-twin-v2", "evaluated_episode_ids": ["val-1"], "trajectory_rmse": 0.04, "contact_timing_mae": 0.03, "outcome_disagreement_rate": 0.1, "sim_real_success_gap": 0.12, "simulated_policy_success_rate": 0.75}
            output = compare_calibration_candidates(experiment, baseline, candidate)
            if output["verdict"] != "admitted":
                return {"status": "terminal_negative", "summary": "Fixture calibrated twin failed its frozen fidelity gate.", "output": output, "proof_class": "synthetic_calibration_evaluation"}
        elif stage_id == "LF-08":
            output = compile_cousin_batch(
                {
                    "schema_version": "sim2claw.cousin_experiment.v1",
                    "experiment_id": "fixture-cousins-v1",
                    "parent_twin_id": "fixture-calibrated-twin-v2",
                    "max_candidates": 4,
                    "variation_envelope": {"maximum_planar_offset_m": 0.02, "allowed_distractors": ["none", "known_pawn"]},
                    "proposals": [
                        {"source_cell": "c1", "target_offset_xy_m": [0.01, 0.0], "distractor": "none", "role": "train"},
                        {"source_cell": "e1", "target_offset_xy_m": [-0.01, 0.01], "distractor": "known_pawn", "role": "train"},
                        {"source_cell": "g1", "target_offset_xy_m": [0.0, -0.01], "distractor": "known_pawn", "role": "debug"},
                        {"source_cell": "d1", "target_offset_xy_m": [0.005, 0.005], "distractor": "none", "role": "held_out"},
                    ],
                }
            )
        elif stage_id == "LF-09":
            batch = self._dependency_output("LF-08")
            rows = []
            for index, candidate in enumerate(batch["candidates"]):
                rows.append({**candidate, "source_sha256": canonical_digest(candidate), "replay_passed": index != 1, "evaluator_passed": index != 1})
            output = admit_dataset_candidates(rows)
            if output["accepted_count"] == 0:
                return {"status": "terminal_negative", "summary": "No fixture cousin passed replay and separate evaluation.", "output": output, "proof_class": "synthetic_dataset_evaluation"}
        elif stage_id == "LF-10":
            dataset = self._dependency_output("LF-09")
            checkpoint = attempt_dir / "fixture_checkpoint.json"
            atomic_write_json(checkpoint, {"architecture": "ACT_fixture", "dataset_sha256": dataset["dataset_sha256"], "weights": [0.25, -0.5, 0.75]})
            task_id = "fixture_pose_conditioned_contact_skill"
            architecture = "ACT_fixture"
            recipe_id = "deterministic_fixture_recipe_v1"
            output = capture_training_candidate(checkpoint, dataset_receipt=dataset, task_id=task_id, recipe_id=recipe_id, architecture=architecture)
        elif stage_id == "LF-11":
            trained = self._dependency_output("LF-10")
            success_rate = 0.8
            output = evaluate_policy_candidates(
                task_id=trained["task_id"],
                evaluator_id="separate_cpu_fp32_consequence_evaluator",
                candidates=[
                    {"candidate_id": "fixture-candidate-v2", "checkpoint_sha256": trained["checkpoint_sha256"], "success_rate": success_rate, "minimum_success_rate": 0.75},
                    {"candidate_id": "fixture-terminal-negative-v1", "checkpoint_sha256": "0" * 64, "success_rate": 0.25, "minimum_success_rate": 0.75},
                ],
            )
        elif stage_id == "LF-12":
            scorecard = self._dependency_output("LF-11")
            output = normalize_counterexamples(
                [
                    {"source_id": "fixture-debug-cousin", "candidate_id": candidate_id, "evaluator_id": scorecard["evaluator_id"], "failure_code": "missed_contact", "source_role": "debug", "trace_sha256": "1" * 64, "disposition": "cousin_coverage"}
                    for candidate_id in scorecard["terminal_negative_candidate_ids"]
                ]
            )
        elif stage_id == "LF-13":
            scorecard = self._dependency_output("LF-11")
            dataset = self._dependency_output("LF-09")
            output = promotion_state(
                scorecard,
                project_id=project_id,
                twin_id="fixture-calibrated-twin-v2",
                dataset_sha256=dataset["dataset_sha256"],
                scope_compatible=True,
            )
        else:
            raise LearningFactoryError(f"fixture adapter does not implement {stage_id}")
        return {"status": "passed", "summary": f"{stage_id} deterministic fixture contract passed.", "output": output, "proof_class": "synthetic_fixture"}


def factory_inspect(project_path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return LearningFactory(project_path, repo_root=repo_root).inspect()


def factory_status(project_path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    return LearningFactory(project_path, repo_root=repo_root).status()


def factory_explain(
    project_path: Path, stage_id: str, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    return LearningFactory(project_path, repo_root=repo_root).explain(stage_id)
