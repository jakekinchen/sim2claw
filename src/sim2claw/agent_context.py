"""Compile bounded, role-specific agent context from current repository state."""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file


MANIFEST_SCHEMA = "sim2claw.agent_current_state.v1"
CONTEXT_SCHEMA = "sim2claw.agent_context.v1"
CHECK_SCHEMA = "sim2claw.agent_workspace_check.v1"
DEFAULT_MANIFEST = Path("configs/agent/current_state_v1.json")
SCHEMA_PATH = Path("configs/agent/schemas/current_state_v1.json")
ROLES = {"executor", "reviewer", "manager"}
CARD_PATTERN = re.compile(r"^([A-Z]+\d+[A-Z]?)_")
EXECUTOR_OPERATIONS = {"read", "test", "write", "commit"}


class AgentContextError(ValueError):
    """Current agent state is stale, ambiguous, or wider than declared."""


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AgentContextError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise AgentContextError(f"{label} must contain an object: {path}")
    return value


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    relative = Path(str(value))
    if relative.is_absolute():
        raise AgentContextError(f"{label} must be repository-relative")
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    if resolved != root and root not in resolved.parents:
        raise AgentContextError(f"{label} escapes the repository")
    return resolved


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _nested(value: Mapping[str, Any], dotted_path: str) -> object:
    current: object = value
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise AgentContextError(f"missing current-state field {dotted_path}")
        current = current[segment]
    return current


def _git(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AgentContextError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _manifest(repo_root: Path, manifest_path: Path) -> tuple[dict[str, Any], Path]:
    path = _repo_path(repo_root, manifest_path, label="agent-state manifest")
    manifest = _load_object(path, label="agent-state manifest")
    schema_path = _repo_path(repo_root, SCHEMA_PATH, label="agent-state schema")
    schema = _load_object(schema_path, label="agent-state schema")
    try:
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).validate(manifest)
    except ValidationError as error:
        location = ".".join(str(value) for value in error.absolute_path) or "<root>"
        raise AgentContextError(
            f"agent-state schema violation at {location}: {error.message}"
        ) from error
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise AgentContextError("unexpected agent-state manifest schema")
    return manifest, path


def _source_binding(
    repo_root: Path,
    graph: Mapping[str, Any],
    name: str,
) -> dict[str, str]:
    bindings = graph.get("source_bindings")
    if not isinstance(bindings, Mapping) or not isinstance(bindings.get(name), Mapping):
        raise AgentContextError(f"campaign graph has no {name} source binding")
    binding = dict(bindings[name])
    path = _repo_path(repo_root, binding.get("path"), label=f"{name} binding")
    if not path.is_file():
        raise AgentContextError(f"{name} binding is missing: {_relative(repo_root, path)}")
    observed = sha256_file(path)
    if observed != binding.get("sha256"):
        raise AgentContextError(f"{name} binding hash drift")
    return {
        "path": _relative(repo_root, path),
        "sha256": observed,
        "proof_class": str(binding.get("proof_class", "")),
    }


def _historical_control_planes(
    repo_root: Path,
    manifest: Mapping[str, Any],
    project_state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for declaration in manifest["historical_control_planes"]:
        name = str(declaration["name"])
        state_key = str(declaration["project_state_key"])
        state = project_state.get(state_key)
        if not isinstance(state, Mapping):
            raise AgentContextError(f"historical control plane {name} is missing")
        if state.get("operational_scope") != declaration["operational_scope"]:
            raise AgentContextError(
                f"historical control plane {name} is not explicitly archived"
            )
        closeout = _nested(project_state, str(declaration["closeout_state_path"]))
        if not isinstance(closeout, Mapping):
            raise AgentContextError(f"historical closeout for {name} is malformed")
        required = {"path", "file_sha256", "packet_digest", "head", "terminal_authority"}
        if not required.issubset(closeout) or closeout.get("terminal_authority") is not True:
            raise AgentContextError(f"historical closeout for {name} is incomplete")
        closeout_path = _repo_path(repo_root, closeout["path"], label=f"{name} closeout")
        locally_verified = False
        if closeout_path.is_file():
            if sha256_file(closeout_path) != closeout["file_sha256"]:
                raise AgentContextError(f"historical closeout for {name} has hash drift")
            locally_verified = True
        result.append(
            {
                "name": name,
                "operational_scope": declaration["operational_scope"],
                "committed_candidate_status": state.get("status"),
                "terminal_packet": {
                    "path": str(closeout["path"]),
                    "sha256": str(closeout["file_sha256"]),
                    "packet_digest": str(closeout["packet_digest"]),
                    "head": str(closeout["head"]),
                    "locally_verified": locally_verified,
                },
            }
        )
    return result


def _load_current(
    repo_root: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    root = repo_root.resolve()
    manifest, resolved_manifest_path = _manifest(root, manifest_path)
    project_path = _repo_path(
        root, manifest["project_state_path"], label="project state"
    )
    graph_path = _repo_path(
        root, manifest["campaign_graph_path"], label="campaign graph"
    )
    agent_rules_path = root / "AGENTS.md"
    goal_path = _repo_path(root, manifest["goal_path"], label="goal")
    history_path = _repo_path(root, manifest["goal_history_path"], label="goal history")
    project_state = _load_object(project_path, label="project state")
    graph = _load_object(graph_path, label="campaign graph")
    queue = _source_binding(root, graph, "queue")

    if project_state.get("active_campaign") != graph.get("campaign_id"):
        raise AgentContextError("project state and campaign graph disagree on active campaign")
    milestone = str(project_state.get("current_milestone", ""))
    match = CARD_PATTERN.match(milestone)
    if match is None:
        raise AgentContextError("current milestone has no card identity")
    milestone_card = match.group(1)
    active_card = graph.get("active_card")
    if active_card is not None and str(active_card) != milestone_card:
        raise AgentContextError("active card disagrees with current milestone")
    if active_card is None and milestone_card.lower() not in str(graph.get("status", "")).lower():
        raise AgentContextError("terminal campaign status disagrees with current milestone")

    history = _historical_control_planes(root, manifest, project_state)
    if not goal_path.is_file():
        raise AgentContextError("concise GOAL.md is missing")
    if not history_path.is_file():
        raise AgentContextError("historical GOAL archive is missing")
    if not agent_rules_path.is_file():
        raise AgentContextError("root AGENTS.md is missing")
    return {
        "manifest": manifest,
        "manifest_path": resolved_manifest_path,
        "project_path": project_path,
        "project_state": project_state,
        "graph_path": graph_path,
        "graph": graph,
        "goal_path": goal_path,
        "history_path": history_path,
        "agent_rules_path": agent_rules_path,
        "queue": queue,
        "historical_control_planes": history,
        "milestone_card": milestone_card,
    }


def _latest_card_binding(current: Mapping[str, Any]) -> dict[str, str] | None:
    graph = current["graph"]
    milestone_card = str(current["milestone_card"]).lower()
    bindings = graph.get("source_bindings")
    if not isinstance(bindings, Mapping):
        return None
    candidates = [
        name
        for name in bindings
        if str(name).lower() == milestone_card
        or str(name).lower().startswith(f"{milestone_card}_")
    ]
    if not candidates:
        return None
    preferred = milestone_card if milestone_card in candidates else sorted(candidates)[0]
    return _source_binding(
        current["project_path"].parents[2],
        graph,
        preferred,
    )


def _active_card_contract(
    repo_root: Path,
    graph: Mapping[str, Any],
) -> dict[str, Any] | None:
    active_card = graph.get("active_card")
    if active_card is None:
        if graph.get("active_card_contract") is not None:
            raise AgentContextError(
                "terminal campaign must not retain an active-card contract"
            )
        return None
    raw = graph.get("active_card_contract")
    if not isinstance(raw, Mapping):
        raise AgentContextError(
            "active card requires a card-specific allowed-path contract"
        )
    contract = dict(raw)
    if str(contract.get("card_id", "")) != str(active_card):
        raise AgentContextError("active-card contract identity mismatch")
    proof_target = str(contract.get("proof_target", "")).strip()
    if not proof_target:
        raise AgentContextError("active-card contract has no proof target")
    paths = contract.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        raise AgentContextError("active-card contract has no allowed paths")
    normalized_paths: list[str] = []
    for index, value in enumerate(paths):
        path = _repo_path(
            repo_root,
            value,
            label=f"active-card allowed path {index}",
        )
        normalized_paths.append(_relative(repo_root, path))
    if len(normalized_paths) != len(set(normalized_paths)):
        raise AgentContextError("active-card allowed paths are not unique")
    operations = contract.get("allowed_operations")
    if not isinstance(operations, list) or not operations:
        raise AgentContextError("active-card contract has no allowed operations")
    normalized_operations = [str(value) for value in operations]
    if (
        set(normalized_operations) - EXECUTOR_OPERATIONS
        or "read" not in normalized_operations
        or "write" not in normalized_operations
    ):
        raise AgentContextError("active-card operations exceed executor scope")
    validations = contract.get("validation_commands")
    if not isinstance(validations, list) or not validations:
        raise AgentContextError("active-card contract has no validation commands")
    normalized_validations = [str(value).strip() for value in validations]
    if any(not value for value in normalized_validations):
        raise AgentContextError("active-card validation command is empty")
    commit = contract.get("commit")
    push_origin_main = contract.get("push_origin_main")
    if not isinstance(commit, bool) or not isinstance(push_origin_main, bool):
        raise AgentContextError("active-card git authority must be boolean")
    if push_origin_main and not commit:
        raise AgentContextError("active-card push requires commit authority")
    return {
        "card_id": str(active_card),
        "proof_target": proof_target,
        "allowed_paths": normalized_paths,
        "allowed_operations": normalized_operations,
        "validation_commands": normalized_validations,
        "commit": commit,
        "push_origin_main": push_origin_main,
    }


def render_goal(
    repo_root: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> str:
    root = repo_root.resolve()
    current = _load_current(root, manifest_path)
    project_state = current["project_state"]
    graph = current["graph"]
    active_card = graph.get("active_card")
    authority = graph.get("authority")
    if not isinstance(authority, Mapping):
        raise AgentContextError("campaign authority must be an object")
    false_authority = sorted(name for name, value in authority.items() if value is False)
    widened = sorted(name for name, value in authority.items() if value is not False)
    if widened:
        raise AgentContextError(f"campaign authority widened: {','.join(widened)}")
    latest = _latest_card_binding(current)
    latest_lines = (
        [
            f"- Closeout: `{latest['path']}`.",
            f"- Closeout SHA-256: `{latest['sha256']}`.",
            f"- Proof class: `{latest['proof_class']}`.",
        ]
        if latest is not None
        else [f"- Proof class: `{project_state['proof_class']}`."]
    )
    card_text = (
        f"`{active_card}`"
        if active_card is not None
        else "`none` — the campaign is at an external-input boundary"
    )
    lines = [
        "# sim2claw Goal",
        "",
        f"Status: `{str(graph['status']).upper()}`",
        "",
        "## Active mission",
        "",
        f"Advance `{graph['campaign_id']}` without crossing the repository's proof,",
        "hardware, held-out, training, promotion, or paid-compute boundaries.",
        "",
        "## Current milestone",
        "",
        f"`{project_state['current_milestone']}`",
        "",
        "## Current card",
        "",
        card_text,
        "",
        "## Current evidence",
        "",
        *latest_lines,
        "",
        "## Authority",
        "",
        f"All current external authorities are false: `{', '.join(false_authority)}`.",
        "",
        "## Canonical sources",
        "",
        f"- Current-state map: `{_relative(root, current['manifest_path'])}`.",
        f"- Campaign graph: `{_relative(root, current['graph_path'])}`.",
        f"- Campaign queue: `{current['queue']['path']}`.",
        f"- Historical narrative: `{_relative(root, current['history_path'])}`.",
        "",
        "## Next transition",
        "",
        f"`{graph['next_transition']}`",
        "",
        "## Stop conditions",
        "",
        "- Do not start an Executor write turn without a non-null active card and",
        "  an exact role-context packet that grants the required paths and operations.",
        "- Stop on identity drift, widened authority, missing closeouts, or a failed",
        "  `uv run --locked sim2claw check --profile agent`.",
        "",
        "## Human constraints",
        "",
        "- External service and fresh authority remain user-owned prerequisites.",
        "- Repository evidence outranks historical prose and advisory research.",
    ]
    rendered = "\n".join(lines) + "\n"
    if len(rendered.splitlines()) > int(current["manifest"]["max_goal_lines"]):
        raise AgentContextError("rendered GOAL.md exceeds the line budget")
    return rendered


def compile_agent_context(
    repo_root: Path,
    *,
    role: str,
    manifest_path: Path = DEFAULT_MANIFEST,
    check_goal: bool = True,
) -> dict[str, Any]:
    if role not in ROLES:
        raise AgentContextError(f"unsupported agent role: {role}")
    root = repo_root.resolve()
    current = _load_current(root, manifest_path)
    manifest = current["manifest"]
    graph = current["graph"]
    project_state = current["project_state"]
    expected_goal = render_goal(root, manifest_path=manifest_path)
    observed_goal = current["goal_path"].read_text(encoding="utf-8")
    goal_lines = len(observed_goal.splitlines())
    if check_goal and observed_goal != expected_goal:
        raise AgentContextError("GOAL.md is not the generated current-state projection")
    if goal_lines > int(manifest["max_goal_lines"]):
        raise AgentContextError("GOAL.md exceeds the declared line budget")

    active_card = graph.get("active_card")
    execution_admitted = role == "executor" and active_card is not None
    active_contract = _active_card_contract(root, graph)
    role_operations = {
        "executor": (
            list(active_contract["allowed_operations"])
            if execution_admitted and active_contract is not None
            else ["read", "diagnose", "report"]
        ),
        "reviewer": ["read", "test", "review", "report"],
        "manager": ["read", "diagnose", "report", "propose_transition"],
    }
    write_paths = (
        list(active_contract["allowed_paths"])
        if execution_admitted and active_contract is not None
        else []
    )
    authority = {
        "commit": bool(
            execution_admitted
            and active_contract is not None
            and active_contract["commit"]
        ),
        "push_origin_main": bool(
            execution_admitted
            and active_contract is not None
            and active_contract["push_origin_main"]
        ),
        **{str(name): bool(value) for name, value in graph["authority"].items()},
    }
    external_authority = {
        name: value
        for name, value in authority.items()
        if name not in {"commit", "push_origin_main"}
    }
    if any(external_authority.values()):
        raise AgentContextError("compiled role context widened external authority")

    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    remote_name = str(manifest["expected_remote"])
    remote = _git(root, "rev-parse", remote_name)
    if branch != manifest["expected_branch"]:
        raise AgentContextError(
            f"repository branch drift: expected {manifest['expected_branch']}, got {branch}"
        )
    if (
        active_card is None
        and manifest["require_remote_equality_at_boundary"] is True
        and head != remote
    ):
        raise AgentContextError(
            f"repository identity drift: HEAD differs from {remote_name}"
        )
    unsigned = {
        "schema_version": CONTEXT_SCHEMA,
        "status": "pass",
        "role": role,
        "execution_admitted": execution_admitted,
        "campaign": {
            "id": graph["campaign_id"],
            "status": graph["status"],
            "active_card": active_card,
            "current_milestone": project_state["current_milestone"],
            "proof_class": project_state["proof_class"],
            "next_transition": graph["next_transition"],
        },
        "repository": {
            "root": str(root),
            "branch": branch,
            "head": head,
            "expected_remote": remote_name,
            "remote_head": remote,
            "worktree_clean": not bool(_git(root, "status", "--porcelain")),
        },
        "scope": {
            "read_paths": [
                "AGENTS.md",
                _relative(root, current["manifest_path"]),
                _relative(root, current["graph_path"]),
                current["queue"]["path"],
                _relative(root, current["goal_path"]),
            ],
            "write_paths": write_paths,
            "allowed_operations": role_operations[role],
            "proof_target": (
                active_contract["proof_target"]
                if execution_admitted and active_contract is not None
                else None
            ),
            "validation_commands": (
                list(active_contract["validation_commands"])
                if execution_admitted and active_contract is not None
                else ["uv run --locked sim2claw check --profile agent"]
            ),
        },
        "authority": authority,
        "source_identities": {
            "agent_rules": {
                "path": _relative(root, current["agent_rules_path"]),
                "sha256": sha256_file(current["agent_rules_path"]),
            },
            "manifest": {
                "path": _relative(root, current["manifest_path"]),
                "sha256": sha256_file(current["manifest_path"]),
            },
            "project_state": {
                "path": _relative(root, current["project_path"]),
                "sha256": sha256_file(current["project_path"]),
            },
            "campaign_graph": {
                "path": _relative(root, current["graph_path"]),
                "sha256": sha256_file(current["graph_path"]),
            },
            "queue": current["queue"],
            "goal": {
                "path": _relative(root, current["goal_path"]),
                "sha256": sha256_file(current["goal_path"]),
            },
        },
        "historical_control_planes": copy.deepcopy(
            current["historical_control_planes"]
        ),
        "limits": {
            "max_context_bytes": int(manifest["max_context_bytes"]),
            "goal_lines": goal_lines,
            "max_goal_lines": int(manifest["max_goal_lines"]),
        },
        "blockers": (
            [str(graph["next_transition"])] if active_card is None else []
        ),
    }
    packet = {**unsigned, "context_digest": ""}
    packet["limits"]["context_bytes"] = 0
    for _ in range(3):
        unsigned_with_size = {
            key: value for key, value in packet.items() if key != "context_digest"
        }
        packet["context_digest"] = canonical_digest(unsigned_with_size)
        observed_bytes = len(
            json.dumps(packet, indent=2, sort_keys=True).encode("utf-8")
        )
        if packet["limits"]["context_bytes"] == observed_bytes:
            break
        packet["limits"]["context_bytes"] = observed_bytes
    encoded_bytes = len(json.dumps(packet, indent=2, sort_keys=True).encode("utf-8"))
    if packet["limits"]["context_bytes"] != encoded_bytes:
        raise AgentContextError("compiled role context byte count did not converge")
    if encoded_bytes > int(manifest["max_context_bytes"]):
        raise AgentContextError("compiled role context exceeds the byte budget")
    return packet


def check_agent_workspace(
    repo_root: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    root = repo_root.resolve()
    contexts = {
        role: compile_agent_context(root, role=role, manifest_path=manifest_path)
        for role in sorted(ROLES)
    }
    return {
        "schema_version": CHECK_SCHEMA,
        "status": "pass",
        "profile": "agent",
        "campaign": contexts["manager"]["campaign"],
        "roles": {
            role: {
                "execution_admitted": packet["execution_admitted"],
                "context_bytes": packet["limits"]["context_bytes"],
                "context_digest": packet["context_digest"],
            }
            for role, packet in contexts.items()
        },
        "historical_control_planes": contexts["manager"][
            "historical_control_planes"
        ],
    }


def write_context(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_json(path, payload)


__all__ = [
    "AgentContextError",
    "CHECK_SCHEMA",
    "CONTEXT_SCHEMA",
    "DEFAULT_MANIFEST",
    "compile_agent_context",
    "check_agent_workspace",
    "render_goal",
    "write_context",
]
