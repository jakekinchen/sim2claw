"""Deterministic, proof-preserving SAIL belief-graph compilation."""

from __future__ import annotations

import copy
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .belief_visuals import write_belief_visuals
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import load_json_object
from .receipts import verify_compile_receipt
from .residuals import verify_residual_receipt


CONFIG_SCHEMA = "sim2claw.sail_belief_graph_campaign.v1"
GRAPH_SCHEMA = "sim2claw.sail_belief_graph.v1"
RECEIPT_SCHEMA = "sim2claw.sail_belief_graph_compile_receipt.v1"

NODE_TYPES = (
    "workcell",
    "session",
    "context",
    "evidence",
    "residual_channel",
    "simulator_version",
    "mechanism",
    "parameter_posterior",
    "intervention",
    "candidate",
    "evaluator_verdict",
    "twin_worthiness_certificate",
    "dataset",
    "checkpoint",
    "policy",
    "counterexample",
)
EDGE_TYPES = (
    "observed-by",
    "generated-from",
    "applied-to",
    "affected-by",
    "fitted-on",
    "evaluated-on",
    "invalidates",
    "compensates-for",
    "predicts",
    "admitted-to",
    "counterexample-to",
)
REQUIRED_HISTORY_FAMILIES = frozenset(
    {
        "geometry_scale",
        "reset_reference",
        "timing",
        "deadband_hysteresis",
        "load_compliance",
        "fingertip_contact",
        "timestep",
        "fixed_pad",
        "contact_friction",
        "terminal_evaluator",
    }
)


class BeliefGraphError(SailContractError):
    """Belief-graph compilation would lose identity or invent lineage."""


def _binding_path(binding: Mapping[str, Any], *, repo_root: Path) -> Path:
    path = repo_root / str(binding.get("path", ""))
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError as error:
        raise BeliefGraphError("belief-graph source escapes repository") from error
    if not path.is_file() or sha256_file(path) != binding.get("sha256"):
        raise BeliefGraphError(f"belief-graph source changed: {binding.get('path')}")
    return path


def _verify_generic_receipt(payload: Mapping[str, Any], binding: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != binding.get("schema_version"):
        raise BeliefGraphError("history source schema changed")
    if payload.get("proof_class") != binding.get("proof_class"):
        raise BeliefGraphError("history source proof class changed")
    if payload.get("created_at") != binding.get("created_at"):
        raise BeliefGraphError("history source chronology changed")
    contract = payload.get("contract") or {}
    if contract.get("sha256") != binding.get("evaluator_identity"):
        raise BeliefGraphError("history source evaluator identity changed")
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop("receipt_digest", None)
    if not isinstance(observed, str) or observed != canonical_digest(normalized):
        raise BeliefGraphError("history source receipt digest changed")
    authority = payload.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise BeliefGraphError("history source widened authority")


def load_belief_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL belief-graph config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise BeliefGraphError("unexpected SAIL belief-graph config schema")
    if tuple(config.get("required_node_types") or ()) != NODE_TYPES:
        raise BeliefGraphError("belief-graph node vocabulary changed")
    if tuple(config.get("required_edge_types") or ()) != EDGE_TYPES:
        raise BeliefGraphError("belief-graph edge vocabulary changed")
    authority = config.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise BeliefGraphError("belief-graph config widened authority")
    for binding in (config.get("source_bindings") or {}).values():
        verify_source_binding(binding, repo_root=repo_root)
    for binding in (config.get("history_sources") or {}).values():
        _binding_path(binding, repo_root=repo_root)
    history = config.get("history") or []
    ids = [str(row.get("id", "")) for row in history]
    if not ids or len(ids) != len(set(ids)):
        raise BeliefGraphError("belief-graph history IDs are empty or duplicated")
    source_ids = set(config.get("history_sources") or {})
    for row in history:
        if row.get("source_id") not in source_ids:
            raise BeliefGraphError("belief-graph history source is undeclared")
        scopes = row.get("declared_scopes")
        if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)):
            raise BeliefGraphError("belief-graph intervention scopes are invalid")
        if row.get("promoted") is not False:
            raise BeliefGraphError("retained belief history promoted a candidate")
    if not REQUIRED_HISTORY_FAMILIES.issubset({str(row.get("family")) for row in history}):
        raise BeliefGraphError("belief-graph retained chronology is incomplete")
    return config


def _source(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(binding[key])
        for key in (
            "path",
            "sha256",
            "schema_version",
            "proof_class",
            "created_at",
            "evaluator_identity",
        )
        if key in binding
    }


def _node(
    node_id: str,
    node_type: str,
    label: str,
    status: str,
    proof_class: str,
    source: Mapping[str, Any],
    *,
    evaluator_identity: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "status": status,
        "proof_class": proof_class,
        "source": copy.deepcopy(dict(source)),
        "evaluator_identity": evaluator_identity,
        "data": copy.deepcopy(dict(data or {})),
    }


def _edge(
    source: str, edge_type: str, target: str, *, metadata: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "source": source,
        "type": edge_type,
        "target": target,
        "metadata": copy.deepcopy(dict(metadata or {})),
    }


def _canonical_graph(
    *,
    campaign_id: str,
    generated_at: str,
    nodes: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    source_identities: Sequence[Mapping[str, Any]],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_nodes = sorted((copy.deepcopy(dict(row)) for row in nodes), key=lambda row: row["id"])
    ordered_edges = sorted(
        (copy.deepcopy(dict(row)) for row in edges),
        key=lambda row: (
            row["source"],
            row["type"],
            row["target"],
            canonical_digest(row.get("metadata") or {}),
        ),
    )
    unsigned = {
        "schema_version": GRAPH_SCHEMA,
        "campaign_id": campaign_id,
        "generated_at": generated_at,
        "node_types": list(NODE_TYPES),
        "edge_types": list(EDGE_TYPES),
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "source_identities": sorted(
            (copy.deepcopy(dict(row)) for row in source_identities),
            key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))),
        ),
        "counts": {
            "nodes": len(ordered_nodes),
            "edges": len(ordered_edges),
            "nodes_by_type": dict(sorted(Counter(row["type"] for row in ordered_nodes).items())),
            "edges_by_type": dict(sorted(Counter(row["type"] for row in ordered_edges).items())),
            "negative_or_nonpromoted_candidates": sum(
                row["type"] == "candidate" and row["status"] != "promoted"
                for row in ordered_nodes
            ),
        },
        "authority": copy.deepcopy(dict(authority)),
        "claim_boundary": "This graph preserves declared lineage and influence scope. Connectivity, similarity, and chronology are not causal identification, simulator promotion, training admission, policy selection, or physical-transfer evidence.",
    }
    return {**unsigned, "graph_digest": canonical_digest(unsigned)}


def validate_graph(graph: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(graph))
    if normalized.get("schema_version") != GRAPH_SCHEMA:
        raise BeliefGraphError("unexpected SAIL belief-graph schema")
    observed = normalized.pop("graph_digest", None)
    if observed != canonical_digest(normalized):
        raise BeliefGraphError("SAIL belief-graph digest mismatch")
    if tuple(normalized.get("node_types") or ()) != NODE_TYPES:
        raise BeliefGraphError("SAIL belief-graph node vocabulary mismatch")
    if tuple(normalized.get("edge_types") or ()) != EDGE_TYPES:
        raise BeliefGraphError("SAIL belief-graph edge vocabulary mismatch")
    nodes = normalized.get("nodes") or []
    edges = normalized.get("edges") or []
    if nodes != sorted(nodes, key=lambda row: row["id"]):
        raise BeliefGraphError("SAIL belief-graph nodes are not canonical")
    ids = [str(row.get("id", "")) for row in nodes]
    if not ids or len(ids) != len(set(ids)) or any(not value for value in ids):
        raise BeliefGraphError("SAIL belief-graph node identity is invalid")
    node_ids = set(ids)
    node_by_id = {str(row["id"]): row for row in nodes}
    for row in nodes:
        if row.get("type") not in NODE_TYPES:
            raise BeliefGraphError("SAIL belief-graph node type is invalid")
        for key in ("label", "status", "proof_class", "source"):
            if key not in row or row[key] in (None, ""):
                raise BeliefGraphError(f"SAIL belief-graph node lost {key}")
        if row["type"] in {"candidate", "evaluator_verdict"} and not row.get(
            "evaluator_identity"
        ):
            raise BeliefGraphError("result node lost evaluator identity")
        source = row["source"]
        if source.get("proof_class") and row["proof_class"] != source["proof_class"]:
            raise BeliefGraphError("result node changed source proof class")
        if source.get("evaluator_identity") and row.get("evaluator_identity") != source.get(
            "evaluator_identity"
        ):
            raise BeliefGraphError("result node changed source evaluator identity")
    expected_edges = sorted(
        edges,
        key=lambda row: (
            row["source"],
            row["type"],
            row["target"],
            canonical_digest(row.get("metadata") or {}),
        ),
    )
    if edges != expected_edges:
        raise BeliefGraphError("SAIL belief-graph edges are not canonical")
    seen_edges: set[tuple[str, str, str, str]] = set()
    for row in edges:
        if row.get("type") not in EDGE_TYPES:
            raise BeliefGraphError("SAIL belief-graph edge type is invalid")
        if row.get("source") not in node_ids or row.get("target") not in node_ids:
            raise BeliefGraphError("SAIL belief-graph edge is dangling")
        if row["type"] == "admitted-to":
            target = node_by_id[str(row["target"])]
            if target["type"] != "twin_worthiness_certificate" or not str(
                target["status"]
            ).startswith("issued"):
                raise BeliefGraphError("admission edge targets a closed certificate")
        identity = (
            str(row["source"]),
            str(row["type"]),
            str(row["target"]),
            canonical_digest(row.get("metadata") or {}),
        )
        if identity in seen_edges:
            raise BeliefGraphError("SAIL belief-graph edge is duplicated")
        seen_edges.add(identity)
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise BeliefGraphError("SAIL belief-graph widened authority")
    expected_counts = {
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_type": dict(sorted(Counter(row["type"] for row in nodes).items())),
        "edges_by_type": dict(sorted(Counter(row["type"] for row in edges).items())),
        "negative_or_nonpromoted_candidates": sum(
            row["type"] == "candidate" and row["status"] != "promoted" for row in nodes
        ),
    }
    if normalized.get("counts") != expected_counts:
        raise BeliefGraphError("SAIL belief-graph counts changed")
    return {**normalized, "graph_digest": str(observed)}


def _matched_channels(residual: Mapping[str, Any], prefixes: Sequence[str]) -> list[str]:
    channels = {str(row["channel"]) for row in residual["samples"]}
    matched = sorted(
        channel for channel in channels if any(channel.startswith(prefix) for prefix in prefixes)
    )
    if not matched:
        raise BeliefGraphError("declared residual family has no retained channel")
    return matched


def _assemble(
    config: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    residual: Mapping[str, Any],
    history_payloads: Mapping[str, Mapping[str, Any]],
    selected_history: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sources = config["source_bindings"]
    campaign_source = {"campaign_id": config["campaign_id"], "declaration": "config"}
    catalog_source = _source(sources["evidence_catalog"])
    residual_source = _source(sources["residual_field"])
    certificate_source = _source(sources["twin_worthiness_contract"])
    entries = list(catalog["entries"])
    physical_entries = [row for row in entries if row["proof_class"] == "physical_teleoperation_source_unqualified"]
    simulator_entries = [
        row
        for row in entries
        if row["proof_class"] == "retained_action_frozen_simulator_replay"
        and row["split_role"] == "validation"
    ]
    nodes: list[dict[str, Any]] = [
        _node("workcell:retired-bg", "workcell", "Retired B–G workcell", "retired_read_only", "retained_context", catalog_source, data={"physical_authority": False}),
        _node("session:retained-bg", "session", "Retained B–G acquisition context", "closed", "retrospective_single_session_context", catalog_source, data={"episode_count": len(physical_entries)}),
        _node("context:action-frozen", "context", "Byte-identical action-frozen lane", "frozen", "retained_action_identity_context", catalog_source),
        _node("dataset:retained-physical", "dataset", "Retained physical teleoperation sources", "unadmitted", "physical_teleoperation_source_unqualified", catalog_source, data={"episode_count": len(physical_entries), "training_admitted": False}),
        _node("evidence:action-frozen-development", "evidence", "Action-frozen development evidence", "compiled", "retained_action_frozen_simulator_replay", catalog_source, data={"episode_count": len(simulator_entries), "evidence_ids": sorted(row["evidence_id"] for row in simulator_entries)}),
        _node("simulator:retained-v3-family", "simulator_version", "Retained diagnostic simulator family", "not_composite_promoted", "retained_action_frozen_simulation_replay", residual_source),
        _node("posterior:retained-unidentified", "parameter_posterior", "Retained mechanism posterior", "underidentified", "retrospective_diagnostic_posterior", campaign_source, data={"physical_parameter_identified": False}),
        _node("certificate:current-unissued", "twin_worthiness_certificate", "Current TwinWorthiness certificate", "unissued_closed", "contract_only_no_certificate", certificate_source, data={"training_admission": False, "policy_selection": False}),
        _node("checkpoint:campaign-none", "checkpoint", "Current-campaign checkpoint", "absent", "declared_absence", campaign_source),
        _node("policy:campaign-none", "policy", "Current-campaign policy", "not_admitted", "declared_absence", campaign_source),
    ]
    edges: list[dict[str, Any]] = [
        _edge("dataset:retained-physical", "observed-by", "session:retained-bg"),
        _edge("session:retained-bg", "observed-by", "workcell:retired-bg"),
        _edge("evidence:action-frozen-development", "generated-from", "dataset:retained-physical", metadata={"action_identity_only": True, "proof_classes_remain_separate": True}),
        _edge("evidence:action-frozen-development", "observed-by", "context:action-frozen"),
        _edge("simulator:retained-v3-family", "generated-from", "context:action-frozen", metadata={"promotion": False}),
    ]
    residual_family_nodes: dict[str, str] = {}
    scope_to_residuals: dict[str, list[str]] = defaultdict(list)
    for family in config["residual_families"]:
        family_id = str(family["id"])
        node_id = f"residual:{family_id}"
        matched = _matched_channels(residual, family["channel_prefixes"])
        residual_family_nodes[family_id] = node_id
        nodes.append(
            _node(node_id, "residual_channel", family_id.replace("_", " "), "compiled", "phase_aligned_retained_residual", residual_source, data={"channels": matched, "availability_preserved": True})
        )
        edges.append(_edge(node_id, "generated-from", "evidence:action-frozen-development"))
        for scope in family["scopes"]:
            scope_to_residuals[str(scope)].append(node_id)
    mechanism_nodes: set[str] = set()
    influence: list[dict[str, Any]] = []
    history_sources = config["history_sources"]
    for row in selected_history:
        source_id = str(row["source_id"])
        binding = history_sources[source_id]
        payload = history_payloads[source_id]
        source = _source(binding)
        proof_class = str(binding["proof_class"])
        evaluator = str(binding["evaluator_identity"])
        item_id = str(row["id"])
        mechanism_scope = str(row["declared_scopes"][0])
        mechanism_id = f"mechanism:{mechanism_scope}"
        intervention_id = f"intervention:{item_id}"
        candidate_id = f"candidate:{item_id}"
        verdict_id = f"verdict:{item_id}"
        if mechanism_id not in mechanism_nodes:
            nodes.append(
                _node(mechanism_id, "mechanism", mechanism_scope.replace("_", " "), "hypothesis_only", proof_class, source, evaluator_identity=evaluator, data={"physical_parameter_identified": False, "role": "declared_mechanism_hypothesis"})
            )
            mechanism_nodes.add(mechanism_id)
        nodes.extend(
            [
                _node(intervention_id, "intervention", str(row["label"]), "retained", proof_class, source, evaluator_identity=evaluator, data={"declared_scopes": list(row["declared_scopes"]), "scope_precedes_similarity": True}),
                _node(candidate_id, "candidate", str(row["label"]), str(row["candidate_status"]), proof_class, source, evaluator_identity=evaluator, data={"promoted": False, "created_at": binding["created_at"]}),
                _node(verdict_id, "evaluator_verdict", str(row["label"]), str(row["verdict_status"]), proof_class, source, evaluator_identity=evaluator, data={"negative": bool(row["negative"]), "promoted": False, "receipt_digest": payload["receipt_digest"]}),
            ]
        )
        edges.extend(
            [
                _edge(mechanism_id, "predicts", intervention_id, metadata={"declared_scope": mechanism_scope}),
                _edge(intervention_id, "applied-to", "simulator:retained-v3-family"),
                _edge(candidate_id, "generated-from", intervention_id),
                _edge("evidence:action-frozen-development", "applied-to", candidate_id, metadata={"source_actions_mutated": False}),
                _edge(candidate_id, "evaluated-on", verdict_id, metadata={"evaluator_identity": evaluator}),
            ]
        )
        influenced: set[str] = set()
        for scope in row["declared_scopes"]:
            for residual_id in scope_to_residuals.get(str(scope), []):
                influenced.add(residual_id)
        for residual_id in sorted(influenced):
            edges.append(
                _edge(
                    residual_id,
                    "affected-by",
                    intervention_id,
                    metadata={"basis": "declared_scope"},
                )
            )
            edges.append(
                _edge(
                    candidate_id,
                    "compensates-for",
                    residual_id,
                    metadata={"causal_claim": False},
                )
            )
            edges.append(
                _edge(
                    mechanism_id,
                    "fitted-on",
                    residual_id,
                    metadata={"status": "diagnostic_only", "history_event": item_id},
                )
            )
        influence.append(
            {
                "intervention_id": intervention_id,
                "declared_scopes": sorted(str(scope) for scope in row["declared_scopes"]),
                "residual_node_ids": sorted(influenced),
                "method": "declared_scope_only_no_statistical_similarity",
            }
        )
        if row["negative"]:
            counterexample_id = f"counterexample:{item_id}"
            nodes.append(
                _node(counterexample_id, "counterexample", str(row["label"]), "retained_queryable", proof_class, source, evaluator_identity=evaluator, data={"verdict_id": verdict_id})
            )
            edges.extend(
                [
                    _edge(verdict_id, "invalidates", candidate_id, metadata={"promotion_only": True}),
                    _edge(counterexample_id, "counterexample-to", mechanism_id),
                    _edge(counterexample_id, "generated-from", verdict_id),
                ]
            )
    source_identities = [
        {"id": source_id, **_source(binding), "evaluator_identity": binding["evaluator_identity"]}
        for source_id, binding in history_sources.items()
        if any(row["source_id"] == source_id for row in selected_history)
    ]
    graph = _canonical_graph(
        campaign_id=str(config["campaign_id"]),
        generated_at=str(config["generated_at"]),
        nodes=nodes,
        edges=edges,
        source_identities=source_identities,
        authority=config["authority"],
    )
    return validate_graph(graph), sorted(influence, key=lambda row: row["intervention_id"])


def build_belief_graph(
    config: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    residual: Mapping[str, Any],
    history_payloads: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ordered_history = sorted(
        config["history"],
        key=lambda row: (config["history_sources"][row["source_id"]]["created_at"], row["id"]),
    )
    before_graph, _ = _assemble(
        config,
        catalog=catalog,
        residual=residual,
        history_payloads=history_payloads,
        selected_history=[],
    )
    revisions: list[dict[str, Any]] = [
        {
            "revision": 0,
            "event_id": "retained-foundations",
            "created_at": "2026-07-21T00:00:00+00:00",
            "graph_digest": before_graph["graph_digest"],
            "node_count": before_graph["counts"]["nodes"],
            "edge_count": before_graph["counts"]["edges"],
        }
    ]
    graph = before_graph
    influence: list[dict[str, Any]] = []
    for index, event in enumerate(ordered_history, start=1):
        graph, influence = _assemble(
            config,
            catalog=catalog,
            residual=residual,
            history_payloads=history_payloads,
            selected_history=ordered_history[:index],
        )
        revisions.append(
            {
                "revision": index,
                "event_id": event["id"],
                "created_at": config["history_sources"][event["source_id"]]["created_at"],
                "graph_digest": graph["graph_digest"],
                "node_count": graph["counts"]["nodes"],
                "edge_count": graph["counts"]["edges"],
            }
        )
    if set(graph["counts"]["nodes_by_type"]) != set(NODE_TYPES):
        raise BeliefGraphError("SAIL belief-graph does not represent every node type")
    return graph, revisions, influence, before_graph


def traverse_graph(
    graph: Mapping[str, Any], source_id: str, target_id: str
) -> list[str]:
    verified = validate_graph(graph)
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in verified["edges"]:
        adjacency[str(edge["source"])].append(str(edge["target"]))
    queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
    visited = {source_id}
    while queue:
        current, path = queue.popleft()
        if current == target_id:
            return path
        for neighbor in sorted(adjacency.get(current, [])):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, [*path, neighbor]))
    raise BeliefGraphError(f"no belief-graph path from {source_id} to {target_id}")


def query_negative_nodes(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    verified = validate_graph(graph)
    return [
        copy.deepcopy(row)
        for row in verified["nodes"]
        if row["type"] in {"counterexample", "evaluator_verdict"}
        and (row["type"] == "counterexample" or row["data"].get("negative") is True)
    ]


def verify_belief_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise BeliefGraphError("unexpected SAIL belief-graph receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise BeliefGraphError("SAIL belief-graph receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or any(authority.values()):
        raise BeliefGraphError("SAIL belief-graph receipt widened authority")
    config_binding = normalized.get("config") or {}
    config_path = repo_root / str(config_binding.get("path", ""))
    if not config_path.is_file() or sha256_file(config_path) != config_binding.get("sha256"):
        raise BeliefGraphError("SAIL belief-graph receipt config changed")
    for relative_path, expected_sha256 in (normalized.get("compiler_sha256") or {}).items():
        path = repo_root / str(relative_path)
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise BeliefGraphError(f"SAIL belief-graph compiler changed: {relative_path}")
    for name, binding in (normalized.get("outputs") or {}).items():
        path = output_root / str(binding.get("path", ""))
        if not path.is_file() or sha256_file(path) != binding.get("sha256"):
            raise BeliefGraphError(f"SAIL belief-graph output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_belief_graph(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config = load_belief_config(config_path, repo_root=repo_root)
    resolved_config = config_path if config_path.is_absolute() else repo_root / config_path
    source_paths = {
        name: verify_source_binding(binding, repo_root=repo_root)
        for name, binding in config["source_bindings"].items()
    }
    evidence_root = source_paths["evidence_catalog"].parent
    evidence_receipt = load_json_object(source_paths["evidence_receipt"], label="SAIL evidence receipt")
    verify_compile_receipt(evidence_receipt, output_root=evidence_root)
    residual_root = source_paths["residual_field"].parent
    residual_receipt = load_json_object(source_paths["residual_receipt"], label="SAIL residual receipt")
    verify_residual_receipt(residual_receipt, output_root=residual_root, repo_root=repo_root)
    catalog = load_json_object(source_paths["evidence_catalog"], label="SAIL evidence catalog")
    residual = verify_contract(load_json_object(source_paths["residual_field"], label="SAIL residual field"))
    history_payloads: dict[str, dict[str, Any]] = {}
    for source_id, binding in config["history_sources"].items():
        payload = load_json_object(_binding_path(binding, repo_root=repo_root), label=f"belief history {source_id}")
        _verify_generic_receipt(payload, binding)
        history_payloads[source_id] = payload
    graph, revisions, influence, before_graph = build_belief_graph(
        config,
        catalog=catalog,
        residual=residual,
        history_payloads=history_payloads,
    )
    terminal_target = "verdict:publication-terminal-negative"
    action_to_verdict = traverse_graph(graph, "evidence:action-frozen-development", terminal_target)
    negative_nodes = query_negative_nodes(graph)
    output_root.mkdir(parents=True, exist_ok=True)
    graph_path = output_root / "belief_graph.json"
    influence_path = output_root / "influence_candidates.json"
    query_path = output_root / "negative_experiments.json"
    traversal_path = output_root / "action_to_terminal_verdict.json"
    atomic_write_json(graph_path, graph)
    atomic_write_json(influence_path, influence)
    atomic_write_json(query_path, negative_nodes)
    atomic_write_json(
        traversal_path,
        {
            "source": "evidence:action-frozen-development",
            "target": terminal_target,
            "path": action_to_verdict,
            "directed": True,
        },
    )
    visuals = write_belief_visuals(
        output_root=output_root,
        before_graph=before_graph,
        after_graph=graph,
        revisions=revisions,
    )
    code_paths = (
        "src/sim2claw/sail/belief_graph.py",
        "src/sim2claw/sail/belief_visuals.py",
    )
    outputs = {
        "belief_graph": {"path": graph_path.name, "sha256": sha256_file(graph_path)},
        "influence_candidates": {"path": influence_path.name, "sha256": sha256_file(influence_path)},
        "negative_experiments": {"path": query_path.name, "sha256": sha256_file(query_path)},
        "action_to_terminal_verdict": {"path": traversal_path.name, "sha256": sha256_file(traversal_path)},
        **visuals,
    }
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved_config.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved_config)},
        "compiler_sha256": {path: sha256_file(repo_root / path) for path in code_paths},
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "history_source_sha256": {name: binding["sha256"] for name, binding in sorted(config["history_sources"].items())},
        "outputs": outputs,
        "counts": {**graph["counts"], "revisions": len(revisions), "influence_candidates": len(influence), "queryable_negative_nodes": len(negative_nodes)},
        "regeneration_command": "uv run sim2claw sail-compile-belief-graph --config configs/sail/belief_graph_retired_bg_v1.json --output outputs/sail/retired-bg-v1/belief-graph",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": graph["claim_boundary"],
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_belief_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_belief_graph_compile_result.v1",
        "campaign_id": config["campaign_id"],
        "status": "compiled",
        "graph_digest": graph["graph_digest"],
        "graph_sha256": sha256_file(graph_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "counts": receipt["counts"],
        "action_to_terminal_verdict": action_to_verdict,
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "BeliefGraphError",
    "EDGE_TYPES",
    "NODE_TYPES",
    "build_belief_graph",
    "compile_belief_graph",
    "load_belief_config",
    "query_negative_nodes",
    "traverse_graph",
    "validate_graph",
    "verify_belief_receipt",
]
