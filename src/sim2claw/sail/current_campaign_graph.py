"""Deterministic adapter from a live campaign checkpoint to the SAIL graph."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .belief_graph import (
    EDGE_TYPES,
    NODE_TYPES,
    BeliefGraphError,
    _canonical_graph,
    _edge,
    _node,
    validate_graph,
)
from .contracts import REPO_ROOT


CONFIG_SCHEMA = "sim2claw.sail_current_campaign_graph_config.v1"


def _repo_file(
    repo_root: Path,
    binding: Mapping[str, Any],
) -> Path:
    relative = Path(str(binding.get("path", "")))
    if not relative.as_posix() or relative.is_absolute():
        raise BeliefGraphError("current-campaign source path is invalid")
    path = (repo_root / relative).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as error:
        raise BeliefGraphError(
            "current-campaign source escapes repository"
        ) from error
    if not path.is_file() or sha256_file(path) != binding.get("sha256"):
        raise BeliefGraphError(
            f"current-campaign source changed: {relative.as_posix()}"
        )
    return path


def _validated_source_bindings(
    config: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, dict[str, Any]]:
    bindings = config.get("source_bindings")
    if not isinstance(bindings, dict) or not bindings:
        raise BeliefGraphError("current-campaign sources are missing")
    validated: dict[str, dict[str, Any]] = {}
    for binding_id, raw in bindings.items():
        if not isinstance(raw, dict):
            raise BeliefGraphError("current-campaign source is invalid")
        binding = copy.deepcopy(raw)
        path = _repo_file(repo_root, binding)
        declared_proof = binding.get("proof_class")
        payload_contract = binding.get("payload_contract")
        if payload_contract is not None:
            if not isinstance(payload_contract, dict) or not payload_contract:
                raise BeliefGraphError(
                    f"current-campaign payload contract is invalid: {binding_id}"
                )
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as error:
                raise BeliefGraphError(
                    f"current-campaign JSON source is unreadable: {binding_id}"
                ) from error
            if not isinstance(payload, dict):
                raise BeliefGraphError(
                    f"current-campaign JSON source is not an object: {binding_id}"
                )
            for field, expected in payload_contract.items():
                if payload.get(field) != expected:
                    raise BeliefGraphError(
                        f"current-campaign source changed {field}: {binding_id}"
                    )
        if not isinstance(declared_proof, str) or not declared_proof:
            raise BeliefGraphError(
                f"current-campaign source lost proof class: {binding_id}"
            )
        validated[str(binding_id)] = binding
    return validated


def load_current_campaign_config(
    path: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        config = json.loads(resolved.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise BeliefGraphError(
            "current-campaign graph config is unavailable"
        ) from error
    if not isinstance(config, dict) or config.get("schema_version") != CONFIG_SCHEMA:
        raise BeliefGraphError("unexpected current-campaign graph config schema")
    if tuple(config.get("node_types") or ()) != NODE_TYPES:
        raise BeliefGraphError("current-campaign node vocabulary changed")
    if tuple(config.get("edge_types") or ()) != EDGE_TYPES:
        raise BeliefGraphError("current-campaign edge vocabulary changed")
    authority = config.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise BeliefGraphError("current-campaign graph widened authority")
    _validated_source_bindings(config, repo_root=repo_root)
    return config


def build_current_campaign_graph(
    config: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Build one canonical graph plus its backtrackable revision timeline."""

    sources = _validated_source_bindings(config, repo_root=repo_root)
    node_specs = config.get("nodes")
    edge_specs = config.get("edges")
    if not isinstance(node_specs, list) or not node_specs:
        raise BeliefGraphError("current-campaign graph has no nodes")
    if not isinstance(edge_specs, list):
        raise BeliefGraphError("current-campaign graph edges are invalid")

    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for spec in node_specs:
        if not isinstance(spec, dict):
            raise BeliefGraphError("current-campaign node is invalid")
        node_id = str(spec.get("id", ""))
        node_type = str(spec.get("type", ""))
        source_id = str(spec.get("source_binding", ""))
        if (
            not node_id
            or node_id in node_ids
            or node_type not in NODE_TYPES
            or source_id not in sources
        ):
            raise BeliefGraphError("current-campaign node identity is invalid")
        node_ids.add(node_id)
        source = sources[source_id]
        evaluator_identity = spec.get("evaluator_identity")
        nodes.append(
            _node(
                node_id,
                node_type,
                str(spec.get("label", "")),
                str(spec.get("status", "")),
                str(source["proof_class"]),
                source,
                evaluator_identity=(
                    str(evaluator_identity) if evaluator_identity else None
                ),
                data={
                    **copy.deepcopy(spec.get("data") or {}),
                    "source_binding_id": source_id,
                },
            )
        )

    edges: list[dict[str, Any]] = []
    for spec in edge_specs:
        if not isinstance(spec, dict):
            raise BeliefGraphError("current-campaign edge is invalid")
        source_id = str(spec.get("source", ""))
        target_id = str(spec.get("target", ""))
        edge_type = str(spec.get("type", ""))
        if (
            source_id not in node_ids
            or target_id not in node_ids
            or edge_type not in EDGE_TYPES
        ):
            raise BeliefGraphError("current-campaign edge identity is invalid")
        edges.append(
            _edge(
                source_id,
                edge_type,
                target_id,
                metadata=spec.get("metadata") or {},
            )
        )

    revisions = copy.deepcopy(config.get("revision_timeline"))
    if not isinstance(revisions, list) or not revisions:
        raise BeliefGraphError("current-campaign revision timeline is missing")
    observed_revision_nodes: set[str] = set()
    for index, revision in enumerate(revisions):
        if (
            not isinstance(revision, dict)
            or revision.get("revision") != index
            or revision.get("source_binding") not in sources
        ):
            raise BeliefGraphError("current-campaign revisions are not canonical")
        additions = revision.get("node_ids_added")
        if (
            not isinstance(additions, list)
            or not additions
            or any(node_id not in node_ids for node_id in additions)
            or any(node_id in observed_revision_nodes for node_id in additions)
        ):
            raise BeliefGraphError("current-campaign revision lineage is invalid")
        observed_revision_nodes.update(additions)
        binding = sources[str(revision["source_binding"])]
        revision["source_sha256"] = binding["sha256"]
    if observed_revision_nodes != node_ids:
        raise BeliefGraphError("current-campaign revision lineage is incomplete")

    active_pointer = copy.deepcopy(config.get("active_pointer"))
    if (
        not isinstance(active_pointer, dict)
        or active_pointer.get("node_id") not in node_ids
    ):
        raise BeliefGraphError("current-campaign active pointer is invalid")

    graph = _canonical_graph(
        campaign_id=str(config.get("campaign_id", "")),
        generated_at=str(config.get("generated_at", "")),
        nodes=nodes,
        edges=edges,
        source_identities=[
            {"id": source_id, **copy.deepcopy(binding)}
            for source_id, binding in sources.items()
        ],
        authority=copy.deepcopy(config["authority"]),
    )
    unsigned = {key: value for key, value in graph.items() if key != "graph_digest"}
    unsigned.update(
        {
            "active_pointer": active_pointer,
            "revision_timeline": revisions,
            "configuration_context": copy.deepcopy(
                config.get("configuration_context") or {}
            ),
            "delta_assessment": copy.deepcopy(config.get("delta_assessment") or {}),
        }
    )
    return validate_graph({**unsigned, "graph_digest": canonical_digest(unsigned)})


def compile_current_campaign_graph(
    config_path: Path,
    *,
    output_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config = load_current_campaign_config(config_path, repo_root=repo_root)
    graph = build_current_campaign_graph(config, repo_root=repo_root)
    resolved_output = (
        output_path if output_path.is_absolute() else repo_root / output_path
    )
    try:
        resolved_output.resolve().relative_to(repo_root.resolve())
    except ValueError as error:
        raise BeliefGraphError(
            "current-campaign graph output escapes repository"
        ) from error
    atomic_write_json(resolved_output, graph)
    return graph


__all__ = [
    "CONFIG_SCHEMA",
    "build_current_campaign_graph",
    "compile_current_campaign_graph",
    "load_current_campaign_config",
]
