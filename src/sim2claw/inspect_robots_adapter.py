from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    import inspect_robots
    from inspect_robots import (
        Action,
        ActionChunk,
        ActionSemantics,
        Box,
        CameraSpec,
        EmbodimentBase,
        EmbodimentInfo,
        EvalLog,
        Observation,
        ObservationSpace,
        PolicyBase,
        PolicyConfig,
        PolicyInfo,
        Scene,
        StateField,
        StateSpec,
        StepResult,
        Task,
        TrialRecord,
        episode_length,
        read_eval_log,
    )
    from inspect_robots.logging import JsonLogSink
except ImportError as error:  # pragma: no cover - exercised by the base-only CLI
    raise ImportError(
        "Inspect Robots support is optional; run with `uv run --extra inspect-robots ...`"
    ) from error

from .paths import REPO_ROOT
from .physical_gateway import GATEWAY_SCHEMA
from .scene import ROBOT_JOINTS
from .source_episode import load_source_contract


FIXTURE_SCHEMA = "sim2claw.inspect_robots_offline_fixture.v1"
RUN_SCHEMA = "sim2claw.inspect_robots_offline_run.v1"
TRIAL_SCHEMA = "sim2claw.inspect_robots_trial_provenance.v1"
REQUIRED_INSPECT_ROBOTS_VERSION = "0.22.0"
DEFAULT_FIXTURE_PATH = (
    REPO_ROOT / "configs/integrations/inspect_robots_offline_fixture.json"
)
PROOF_CLASS = "synthetic_deterministic_replay_compatibility"


class InspectRobotsIntegrationError(ValueError):
    pass


def _plain_vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != len(ROBOT_JOINTS):
        raise InspectRobotsIntegrationError(
            f"{label} must contain exactly {len(ROBOT_JOINTS)} joints"
        )
    vector = [float(item) for item in value]
    if not all(math.isfinite(item) for item in vector):
        raise InspectRobotsIntegrationError(f"{label} contains a non-finite value")
    return vector


def _vector_sha256(vector: list[float]) -> str:
    payload = json.dumps(
        [float(item) for item in vector],
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exact_dependency() -> None:
    if inspect_robots.__version__ != REQUIRED_INSPECT_ROBOTS_VERSION:
        raise InspectRobotsIntegrationError(
            "Inspect Robots version mismatch: "
            f"required {REQUIRED_INSPECT_ROBOTS_VERSION}, "
            f"found {inspect_robots.__version__}"
        )


def load_offline_fixture(path: Path = DEFAULT_FIXTURE_PATH) -> dict[str, Any]:
    _require_exact_dependency()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InspectRobotsIntegrationError(
            f"cannot read Inspect Robots fixture {path}: {error}"
        ) from error
    if not isinstance(payload, dict) or payload.get("schema_version") != FIXTURE_SCHEMA:
        raise InspectRobotsIntegrationError("unsupported Inspect Robots fixture schema")
    if payload.get("proof_class") != PROOF_CLASS:
        raise InspectRobotsIntegrationError(
            "offline slice must remain synthetic deterministic replay proof"
        )
    if payload.get("evaluator_admission") is not False:
        raise InspectRobotsIntegrationError(
            "offline compatibility replay cannot grant evaluator admission"
        )
    if payload.get("physical_authority") is not False:
        raise InspectRobotsIntegrationError(
            "offline compatibility replay cannot grant physical authority"
        )
    if payload.get("gateway_schema") != GATEWAY_SCHEMA:
        raise InspectRobotsIntegrationError(
            "fixture must reference the current guarded gateway contract"
        )
    if payload.get("joint_order") != list(ROBOT_JOINTS):
        raise InspectRobotsIntegrationError("fixture joint order is not the SO-101 order")

    source_path = REPO_ROOT / str(payload.get("source_task_contract", ""))
    try:
        source_contract = load_source_contract(source_path)
    except (OSError, ValueError) as error:
        raise InspectRobotsIntegrationError(
            f"canonical source task contract is invalid: {error}"
        ) from error
    if source_contract["contract_id"] != payload.get("task_id"):
        raise InspectRobotsIntegrationError(
            "fixture task identity does not match its canonical source contract"
        )

    cameras = payload.get("cameras")
    if not isinstance(cameras, list) or len(cameras) != 2:
        raise InspectRobotsIntegrationError("fixture must declare exactly two cameras")
    camera_names: set[str] = set()
    camera_roles: set[str] = set()
    for camera in cameras:
        if not isinstance(camera, dict):
            raise InspectRobotsIntegrationError("camera specifications must be objects")
        name = str(camera.get("name", ""))
        role = str(camera.get("role", ""))
        if (
            not name
            or not role
            or int(camera.get("height", 0)) <= 0
            or int(camera.get("width", 0)) <= 0
            or int(camera.get("channels", 0)) != 3
        ):
            raise InspectRobotsIntegrationError("camera specification is incomplete")
        camera_names.add(name)
        camera_roles.add(role)
    if camera_names != {"top", "wrist"}:
        raise InspectRobotsIntegrationError(
            "fixture camera names must match the canonical top/wrist streams"
        )
    if len(camera_roles) != 2:
        raise InspectRobotsIntegrationError("camera roles must be distinct")

    observations = payload.get("observations")
    actions = payload.get("actions")
    if (
        not isinstance(observations, list)
        or not isinstance(actions, list)
        or len(actions) < 1
        or len(observations) != len(actions) + 1
    ):
        raise InspectRobotsIntegrationError(
            "fixture needs one more observation than action"
        )
    previous_time = -math.inf
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            raise InspectRobotsIntegrationError("observations must be objects")
        timestamp = float(observation.get("time_s", math.nan))
        if not math.isfinite(timestamp) or timestamp <= previous_time:
            raise InspectRobotsIntegrationError(
                "observation timestamps must be finite and strictly increasing"
            )
        previous_time = timestamp
        _plain_vector(
            observation.get("joint_position_rad"),
            f"observations[{index}].joint_position_rad",
        )
        _plain_vector(
            observation.get("joint_velocity_rad_s"),
            f"observations[{index}].joint_velocity_rad_s",
        )
        refs = observation.get("camera_refs")
        if (
            not isinstance(refs, dict)
            or set(refs) != camera_names
            or not all(isinstance(ref, str) and ref for ref in refs.values())
        ):
            raise InspectRobotsIntegrationError(
                f"observations[{index}] must preserve both camera references"
            )
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise InspectRobotsIntegrationError("actions must be objects")
        _plain_vector(
            action.get("requested_action_rad"),
            f"actions[{index}].requested_action_rad",
        )
        _plain_vector(
            action.get("applied_action_rad"),
            f"actions[{index}].applied_action_rad",
        )
    control_hz = float(payload.get("control_hz", math.nan))
    if not math.isfinite(control_hz) or control_hz <= 0.0:
        raise InspectRobotsIntegrationError("control_hz must be finite and positive")
    return payload


def _action_space() -> Box:
    return Box(
        shape=(len(ROBOT_JOINTS),),
        semantics=ActionSemantics(
            control_mode="joint_pos",
            rotation_repr="none",
            gripper="continuous",
            frame="base",
            dim_labels=ROBOT_JOINTS,
        ),
    )


def _observation_space(fixture: dict[str, Any]) -> ObservationSpace:
    return ObservationSpace(
        cameras=tuple(
            CameraSpec(
                name=str(camera["name"]),
                height=int(camera["height"]),
                width=int(camera["width"]),
                channels=int(camera["channels"]),
            )
            for camera in fixture["cameras"]
        ),
        state=StateSpec(
            fields=(
                StateField(
                    key="joint_pos",
                    shape=(len(ROBOT_JOINTS),),
                    unit="rad",
                ),
                StateField(
                    key="joint_vel",
                    shape=(len(ROBOT_JOINTS),),
                    unit="rad/s",
                ),
            )
        ),
    )


def _observation(
    fixture: dict[str, Any],
    index: int,
    *,
    instruction: str,
) -> Observation:
    raw = fixture["observations"][index]
    return Observation(
        images={},
        state={
            "joint_pos": np.asarray(raw["joint_position_rad"], dtype=np.float64),
            "joint_vel": np.asarray(raw["joint_velocity_rad_s"], dtype=np.float64),
        },
        instruction=instruction,
        state_time=float(raw["time_s"]),
        extra={
            "sim2claw_replay_index": index,
            "camera_refs": dict(raw["camera_refs"]),
            "camera_data_present": False,
            "proof_class": fixture["proof_class"],
            "physical_authority": False,
        },
    )


class Sim2ClawReplayPolicy(PolicyBase):
    def __init__(self, fixture: dict[str, Any]):
        self._fixture = fixture
        self._next_action = 0
        self.info = PolicyInfo(
            name="sim2claw-deterministic-replay",
            action_space=_action_space(),
            observation_space=_observation_space(fixture),
            control_hz=float(fixture["control_hz"]),
        )
        self.config = PolicyConfig(action_horizon=1, replan_interval=1)

    def reset(self, scene: Scene) -> None:
        self._next_action = 0

    def act(self, observation: Observation) -> ActionChunk:
        index = int(observation.extra.get("sim2claw_replay_index", -1))
        if index != self._next_action or index >= len(self._fixture["actions"]):
            raise InspectRobotsIntegrationError(
                f"replay policy expected observation {self._next_action}, got {index}"
            )
        requested = _plain_vector(
            self._fixture["actions"][index]["requested_action_rad"],
            f"actions[{index}].requested_action_rad",
        )
        self._next_action += 1
        return ActionChunk(
            actions=(
                Action(
                    data=np.asarray(requested, dtype=np.float64),
                    meta={
                        "sim2claw_step": index,
                        "requested_action_rad": requested,
                        "requested_action_sha256": _vector_sha256(requested),
                    },
                ),
            ),
            control_hz=float(self._fixture["control_hz"]),
        )

    def on_trial_end(self, record: TrialRecord, log_dir: str, run_id: str) -> None:
        transitions: list[dict[str, Any]] = []
        for step in record.steps:
            requested = _plain_vector(
                list(np.asarray(step.action.data, dtype=np.float64)),
                f"record.steps[{step.t}].requested_action",
            )
            applied = _plain_vector(
                step.result.info.get("sim2claw_applied_action_rad"),
                f"record.steps[{step.t}].applied_action",
            )
            requested_hash = _vector_sha256(requested)
            applied_hash = _vector_sha256(applied)
            transitions.append(
                {
                    "step": step.t,
                    "observation_time_s": float(step.observation.state_time),
                    "camera_refs": dict(step.observation.extra["camera_refs"]),
                    "joint_position_rad": [
                        float(value) for value in step.observation.state["joint_pos"]
                    ],
                    "joint_velocity_rad_s": [
                        float(value) for value in step.observation.state["joint_vel"]
                    ],
                    "requested_action_rad": requested,
                    "requested_action_sha256": requested_hash,
                    "applied_action_rad": applied,
                    "applied_action_sha256": applied_hash,
                    "requested_applied_exact": requested_hash == applied_hash,
                }
            )
        requested_sequence = [
            transition["requested_action_sha256"] for transition in transitions
        ]
        applied_sequence = [
            transition["applied_action_sha256"] for transition in transitions
        ]
        record.metadata["sim2claw"] = {
            "schema_version": TRIAL_SCHEMA,
            "fixture_id": self._fixture["fixture_id"],
            "task_id": self._fixture["task_id"],
            "source_task_contract": self._fixture["source_task_contract"],
            "proof_class": self._fixture["proof_class"],
            "evaluator_admission": False,
            "physical_authority": False,
            "gateway_schema": self._fixture["gateway_schema"],
            "gateway_invoked": False,
            "joint_order": list(ROBOT_JOINTS),
            "action_representation": "absolute_joint_position_target",
            "action_unit": "rad",
            "camera_roles": {
                str(camera["name"]): str(camera["role"])
                for camera in self._fixture["cameras"]
            },
            "transitions": transitions,
            "requested_action_sequence_sha256": _vector_sha256_text(
                requested_sequence
            ),
            "applied_action_sequence_sha256": _vector_sha256_text(applied_sequence),
            "requested_applied_sequence_exact": requested_sequence
            == applied_sequence,
        }


def _vector_sha256_text(values: list[str]) -> str:
    payload = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Sim2ClawReplayEmbodiment(EmbodimentBase):
    def __init__(self, fixture: dict[str, Any]):
        self._fixture = fixture
        self._instruction = str(fixture["instruction"])
        self._next_action = 0
        self.info = EmbodimentInfo(
            name="sim2claw-offline-replay",
            action_space=_action_space(),
            observation_space=_observation_space(fixture),
            control_hz=float(fixture["control_hz"]),
            is_simulated=True,
            capabilities=frozenset({"seedable", "resettable", "auto_reset"}),
            docs=(
                "Deterministic offline fixture. It references two camera streams "
                "but opens no camera, simulator, transport, serial device, or "
                "physical gateway."
            ),
        )

    def reset(self, scene: Scene, *, seed: int | None = None) -> Observation:
        self._instruction = scene.instruction
        self._next_action = 0
        return _observation(self._fixture, 0, instruction=self._instruction)

    def step(self, action: Action) -> StepResult:
        index = self._next_action
        if index >= len(self._fixture["actions"]):
            raise InspectRobotsIntegrationError("offline replay has no remaining action")
        requested = _plain_vector(
            list(np.asarray(action.data, dtype=np.float64)),
            f"step[{index}].requested_action",
        )
        expected = _plain_vector(
            self._fixture["actions"][index]["requested_action_rad"],
            f"actions[{index}].requested_action_rad",
        )
        if _vector_sha256(requested) != _vector_sha256(expected):
            raise InspectRobotsIntegrationError(
                f"requested action {index} does not match the sealed replay input"
            )
        applied = _plain_vector(
            self._fixture["actions"][index]["applied_action_rad"],
            f"actions[{index}].applied_action_rad",
        )
        self._next_action += 1
        final = self._next_action == len(self._fixture["actions"])
        return StepResult(
            observation=_observation(
                self._fixture,
                self._next_action,
                instruction=self._instruction,
            ),
            terminated=final,
            termination_reason="fixture_complete" if final else None,
            info={
                "sim2claw_requested_action_rad": requested,
                "sim2claw_requested_action_sha256": _vector_sha256(requested),
                "sim2claw_applied_action_rad": applied,
                "sim2claw_applied_action_sha256": _vector_sha256(applied),
                "physical_authority": False,
                "gateway_invoked": False,
            },
        )


def build_offline_components(
    fixture: dict[str, Any],
) -> tuple[Task, Sim2ClawReplayPolicy, Sim2ClawReplayEmbodiment]:
    task = Task(
        name="sim2claw-offline-replay",
        scenes=(
            Scene(
                id=str(fixture["fixture_id"]),
                instruction=str(fixture["instruction"]),
                init_seed=0,
                metadata={
                    "task_id": fixture["task_id"],
                    "proof_class": fixture["proof_class"],
                    "evaluator_admission": False,
                    "physical_authority": False,
                },
            ),
        ),
        scorer=episode_length(),
        max_steps=len(fixture["actions"]),
        metadata={
            "proof_class": fixture["proof_class"],
            "evaluator_admission": False,
            "physical_authority": False,
        },
    )
    return task, Sim2ClawReplayPolicy(fixture), Sim2ClawReplayEmbodiment(fixture)


def validate_eval_log(log_or_path: EvalLog | Path) -> dict[str, Any]:
    _require_exact_dependency()
    log = (
        read_eval_log(str(log_or_path))
        if isinstance(log_or_path, Path)
        else log_or_path
    )
    if log.version != EvalLog.SCHEMA_VERSION or log.status != "success":
        raise InspectRobotsIntegrationError("Inspect Robots EvalLog did not succeed")
    if (
        log.eval.task != "sim2claw-offline-replay"
        or log.eval.policy != "sim2claw-deterministic-replay"
        or log.eval.embodiment != "sim2claw-offline-replay"
    ):
        raise InspectRobotsIntegrationError("EvalLog component identity changed")
    if (
        log.eval.inspect_robots_version != REQUIRED_INSPECT_ROBOTS_VERSION
        or log.eval.embodiment_info.get("is_simulated") is not True
        or len(log.samples) != 1
        or len(log.samples[0].trial_metadata) != 1
    ):
        raise InspectRobotsIntegrationError("EvalLog compatibility metadata is incomplete")
    provenance = log.samples[0].trial_metadata[0].get("sim2claw")
    if not isinstance(provenance, dict) or provenance.get("schema_version") != TRIAL_SCHEMA:
        raise InspectRobotsIntegrationError("EvalLog lacks Sim2Claw trial provenance")
    if provenance.get("proof_class") != PROOF_CLASS:
        raise InspectRobotsIntegrationError("EvalLog proof class changed")
    if provenance.get("evaluator_admission") is not False:
        raise InspectRobotsIntegrationError("EvalLog improperly grants evaluator admission")
    if provenance.get("physical_authority") is not False:
        raise InspectRobotsIntegrationError("EvalLog improperly grants physical authority")
    if provenance.get("gateway_invoked") is not False:
        raise InspectRobotsIntegrationError("offline slice invoked a physical gateway")
    if provenance.get("gateway_schema") != GATEWAY_SCHEMA:
        raise InspectRobotsIntegrationError("EvalLog gateway contract identity changed")
    if provenance.get("joint_order") != list(ROBOT_JOINTS):
        raise InspectRobotsIntegrationError("EvalLog joint order changed")
    camera_roles = provenance.get("camera_roles")
    if not isinstance(camera_roles, dict) or set(camera_roles) != {"top", "wrist"}:
        raise InspectRobotsIntegrationError("EvalLog did not preserve both camera roles")
    transitions = provenance.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise InspectRobotsIntegrationError("EvalLog contains no replay transitions")
    requested_hashes: list[str] = []
    applied_hashes: list[str] = []
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            raise InspectRobotsIntegrationError("transition provenance must be an object")
        if set(transition.get("camera_refs", {})) != {"top", "wrist"}:
            raise InspectRobotsIntegrationError(
                f"transition {index} lacks both camera references"
            )
        requested = _plain_vector(
            transition.get("requested_action_rad"),
            f"transitions[{index}].requested_action_rad",
        )
        applied = _plain_vector(
            transition.get("applied_action_rad"),
            f"transitions[{index}].applied_action_rad",
        )
        requested_hash = _vector_sha256(requested)
        applied_hash = _vector_sha256(applied)
        if transition.get("requested_action_sha256") != requested_hash:
            raise InspectRobotsIntegrationError(
                f"transition {index} requested-action hash disagrees"
            )
        if transition.get("applied_action_sha256") != applied_hash:
            raise InspectRobotsIntegrationError(
                f"transition {index} applied-action hash disagrees"
            )
        if transition.get("requested_applied_exact") is not (
            requested_hash == applied_hash
        ):
            raise InspectRobotsIntegrationError(
                f"transition {index} action-identity label disagrees"
            )
        requested_hashes.append(requested_hash)
        applied_hashes.append(applied_hash)
    if (
        provenance.get("requested_action_sequence_sha256")
        != _vector_sha256_text(requested_hashes)
        or provenance.get("applied_action_sequence_sha256")
        != _vector_sha256_text(applied_hashes)
        or provenance.get("requested_applied_sequence_exact")
        is not (requested_hashes == applied_hashes)
    ):
        raise InspectRobotsIntegrationError("action sequence provenance disagrees")
    return {
        "schema_version": RUN_SCHEMA,
        "status": "pass",
        "inspect_robots_version": log.eval.inspect_robots_version,
        "eval_log_schema_version": log.version,
        "task": log.eval.task,
        "policy": log.eval.policy,
        "embodiment": log.eval.embodiment,
        "proof_class": provenance["proof_class"],
        "evaluator_admission": provenance["evaluator_admission"],
        "physical_authority": provenance["physical_authority"],
        "gateway_schema": provenance["gateway_schema"],
        "gateway_invoked": provenance["gateway_invoked"],
        "camera_roles": provenance["camera_roles"],
        "transition_count": len(transitions),
        "requested_applied_sequence_exact": provenance[
            "requested_applied_sequence_exact"
        ],
        "episode_length": log.samples[0].reduced.get("episode_length"),
        "task_success_claimed": False,
    }


def run_offline_slice(
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    output_dir: Path,
) -> dict[str, Any]:
    fixture = load_offline_fixture(fixture_path)
    task, policy, embodiment = build_offline_components(fixture)
    sink = JsonLogSink(str(output_dir))
    try:
        logs = inspect_robots.eval(
            task,
            policy,
            embodiment,
            log_dir=str(output_dir),
            sinks=[sink],
            seed=0,
            fail_on_error=True,
            store_frames=False,
        )
    finally:
        embodiment.close()
    if len(logs) != 1 or sink.path is None or not sink.path.is_file():
        raise InspectRobotsIntegrationError(
            "Inspect Robots did not finalize exactly one canonical EvalLog"
        )
    report = validate_eval_log(sink.path)
    report.update(
        {
            "eval_log_path": str(sink.path),
            "eval_log_sha256": _sha256_file(sink.path),
            "fixture_path": str(fixture_path),
            "fixture_sha256": _sha256_file(fixture_path),
        }
    )
    return report
