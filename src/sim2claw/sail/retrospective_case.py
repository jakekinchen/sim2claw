"""Retired-workcell retrospective SAIL loop-closure case study."""

from __future__ import annotations

import copy
import html
import random
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, load_json_object, sha256_file
from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract
from .loop_closure import validate_loop_closure
from .twin_worthiness import capabilities_for_level, resolve_level

CONFIG_SCHEMA = "sim2claw.sail_retrospective_case_campaign.v1"
CASE_SCHEMA = "sim2claw.sail_retrospective_case.v1"
RECEIPT_SCHEMA = "sim2claw.sail_retrospective_case_receipt.v1"


class RetrospectiveCaseError(SailContractError):
    """The retrospective reconstruction changed frozen evidence or claims."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RetrospectiveCaseError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RetrospectiveCaseError(f"{label} escapes repository") from error
    return path


def load_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    value = load_json_object(resolved, label="SAIL retrospective case config")
    _require(value.get("schema_version") == CONFIG_SCHEMA, "unsupported retrospective case schema")
    _require(value.get("proof_class") == "development_informed_retrospective_case_study", "retrospective proof class changed")
    _require(value.get("reconstruction_order") == ["chronological", "shuffled_order", "sequential_no_revisit", "full_batch", "sail_sparse_loop_closure"], "reconstruction inventory changed")
    _require(value.get("conclusion_families") == ["scale", "timing", "deadband", "load", "contact"], "conclusion family inventory changed")
    authority = value.get("authority")
    _require(isinstance(authority, dict) and authority and not any(authority.values()), "retrospective case authority widened")
    for name, binding in value["source_bindings"].items():
        source = _repo_path(repo_root, binding["path"], name)
        _require(source.is_file(), f"retrospective source missing: {name}")
        _require(sha256_file(source) == binding["sha256"], f"retrospective source changed: {name}")
    return value


def _sources(config: Mapping[str, Any], repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: load_json_object(_repo_path(repo_root, binding["path"], name), label=name)
        for name, binding in config["source_bindings"].items()
    }


def _timeline(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes = [row for row in graph["nodes"] if row["type"] == "candidate"]
    result = []
    for candidate in sorted(nodes, key=lambda row: (row["source"].get("created_at", ""), row["id"])):
        suffix = candidate["id"].split(":", 1)[1]
        intervention_id = f"intervention:{suffix}"
        verdict_id = f"verdict:{suffix}"
        intervention = next((row for row in graph["nodes"] if row["id"] == intervention_id), None)
        verdict = next((row for row in graph["nodes"] if row["id"] == verdict_id), None)
        _require(intervention is not None and verdict is not None, f"history triad missing: {suffix}")
        result.append({
            "ordinal": len(result) + 1,
            "created_at": candidate["source"].get("created_at"),
            "intervention_id": intervention_id,
            "candidate_id": candidate["id"],
            "verdict_id": verdict_id,
            "label": candidate["label"],
            "candidate_status": candidate["status"],
            "verdict_status": verdict["status"],
            "declared_scopes": copy.deepcopy(intervention["data"]["declared_scopes"]),
            "source_path": candidate["source"]["path"],
            "source_sha256": candidate["source"]["sha256"],
            "proof_class": candidate["source"]["proof_class"],
            "prospective": False,
            "fresh_held_out": False,
            "physical_parameter_identified": False,
        })
    return result


def _graph_edits(graph: Mapping[str, Any], influence: Mapping[str, Any]) -> list[dict[str, Any]]:
    node_map = {row["id"]: row for row in graph["nodes"]}
    edge_set = {(row["source"], row["type"], row["target"]) for row in graph["edges"]}
    edits = []
    for intervention_id in influence["affected_intervention_ids"]:
        suffix = intervention_id.split(":", 1)[1]
        candidate_id = f"candidate:{suffix}"
        verdict_id = f"verdict:{suffix}"
        required_edges = [
            (candidate_id, "generated-from", intervention_id),
            (candidate_id, "evaluated-on", verdict_id),
        ]
        _require(all(edge in edge_set for edge in required_edges), f"graph edit lacks intervention/result binding: {intervention_id}")
        source = node_map[intervention_id]["source"]
        edits.append({
            "edit_id": f"credit-reassignment:{suffix}",
            "intervention_id": intervention_id,
            "candidate_id": candidate_id,
            "verdict_id": verdict_id,
            "source_path": source["path"],
            "source_sha256": source["sha256"],
            "required_edges": [{"source": left, "type": edge_type, "target": right} for left, edge_type, right in required_edges],
            "operation": "revisit_credit_with_frozen_influence_method",
            "historical_result_mutated": False,
            "physical_parameter_identified": False,
        })
    return edits


def _findings(fidelity: Mapping[str, Any], grasp: Mapping[str, Any], friction: Mapping[str, Any]) -> list[dict[str, Any]]:
    pooled = fidelity["pooled_cross_validated_metrics"]
    consequence = fidelity["target_piece_consequence_comparison"]
    boundary = fidelity["boundary_disclosure"]
    union = grasp["frozen_family_union"]
    friction_candidate = friction["frozen_full_set_candidate"]
    return [
        {
            "finding_id": "boundary-load-bias",
            "kind": "boundary_fit",
            "evidence_path": "fidelity_closeout.boundary_disclosure",
            "facts": {"parameter": boundary["parameter"], "selected_value": boundary["selected_value"], "frozen_grid_lower_bound": boundary["frozen_grid_lower_bound"], "at_boundary": boundary["selection_at_grid_boundary"]},
            "conclusion": "load-response model class supported; coefficient magnitude not identified; no post-hoc expansion",
        },
        {
            "finding_id": "rms-versus-lift-reversal",
            "kind": "mixed_vector_reversal",
            "evidence_path": "fidelity_closeout.pooled_cross_validated_metrics_and_target_piece_consequence_comparison",
            "facts": {"joint_rms_relative_improvement": pooled["joint_rms_relative_improvement"], "ee_rms_relative_improvement": pooled["ee_rms_relative_improvement"], "baseline_lifts": consequence["current_baseline"]["lifted"], "candidate_lifts": consequence["selected_load_bias"]["lifted"], "strict_successes": consequence["selected_load_bias"]["task_consequence_successes"]},
            "conclusion": "trace fidelity improved while lift regressed; RMS is not interaction fidelity",
        },
        {
            "finding_id": "timestep-bounded-win",
            "kind": "bounded_sensitivity",
            "evidence_path": "grasp_closeout.verified_wins",
            "facts": {"lifts_doubled_from_2_to_4": grasp["verified_wins"]["v3_lifts_double_from_2_to_4_with_trace_guard_pass"], "composite_promoted": grasp["promotion_gate"]["simulator_composite_promoted"]},
            "conclusion": "2.25 ms timestep is a bounded simulator sensitivity win, not a promoted physical timing parameter",
        },
        {
            "finding_id": "friction-partial-reversal",
            "kind": "mixed_vector_reversal",
            "evidence_path": "friction_closeout.frozen_full_set_candidate",
            "facts": {"retention_relative_delta": friction_candidate["metric_deltas"]["mean_retention_seconds"]["relative_delta"], "target_distance_relative_delta": friction_candidate["metric_deltas"]["mean_final_target_distance_m"]["relative_delta"], "lift_delta": friction_candidate["count_deltas"]["lifted"], "transport_delta": friction_candidate["count_deltas"]["lift_and_transport"], "ee_rms_guard_pass": friction_candidate["trace_guard"]["ee_rms_pass"]},
            "conclusion": "friction improved retention and endpoint metrics but not counts and failed the EE guard",
        },
        {
            "finding_id": "family-union-without-single-model",
            "kind": "coverage_without_single_model_success",
            "evidence_path": "grasp_closeout.frozen_family_union",
            "facts": {"candidate_count": len(union["candidate_names"]), "union_lifts": union["lifted"], "union_lift_and_transport": union["lift_and_transport"], "single_candidate_gate_pass": grasp["promotion_gate"]["single_candidate_minimum_6_of_11_lift_and_transport"] or grasp["promotion_gate"]["single_candidate_strict_success"]},
            "conclusion": "family coverage is sensitivity evidence only; no single simulator explains the outcomes",
        },
    ]


def _conclusions() -> dict[str, dict[str, Any]]:
    return {
        "scale": {"before": "nominal-print-conditioned plausibility", "after": "unchanged diagnostic only", "measured_physical_parameter": False, "reason": "no tag-family/dimension/camera solve establishes metric scale"},
        "timing": {"before": "accepted simulator timing diagnostic", "after": "possible compensator jointly reconsidered with load", "measured_physical_parameter": False, "reason": "simulator-side delay is not measured command-to-actuation latency"},
        "deadband": {"before": "cross-validated simulator model-class diagnostic", "after": "retained but task consequence gate failed", "measured_physical_parameter": False, "reason": "no firmware torque/current calibration identifies physical deadband"},
        "load": {"before": "lower-bound trace diagnostic", "after": "influence-supported explanatory family with unidentified magnitude", "measured_physical_parameter": False, "reason": "selected coefficient is at the frozen boundary and load proxy is missing"},
        "contact": {"before": "multiple sensitivity candidates", "after": "underidentified; partial friction/timestep effects and no single-model success", "measured_physical_parameter": False, "reason": "physical contact state/force and metric object trajectory are absent"},
    }


def _reconstructions(config: Mapping[str, Any], timeline: list[dict[str, Any]], closure: Mapping[str, Any], edits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chronological = [row["intervention_id"] for row in timeline]
    shuffled = list(chronological)
    random.Random(int(config["shuffled_order_seed"])).shuffle(shuffled)
    full_count = int(closure["full_batch"]["recomputed_decision_count"])
    sparse_count = int(closure["sparse"]["recomputed_decision_count"])
    shared = _conclusions()
    return [
        {"method": "chronological", "order": chronological, "recomputed_decision_count": len(chronological), "graph_edit_count": 0, "conclusions": copy.deepcopy(shared), "order_role": "recorded_history", "physical_truth_claim": False},
        {"method": "shuffled_order", "order": shuffled, "recomputed_decision_count": len(shuffled), "graph_edit_count": 0, "conclusions": copy.deepcopy(shared), "order_role": "seeded_order_sensitivity_control", "terminal_inventory_equal": set(shuffled) == set(chronological), "physical_truth_claim": False},
        {"method": "sequential_no_revisit", "order": chronological, "recomputed_decision_count": 1, "graph_edit_count": 0, "conclusions": {**copy.deepcopy(shared), "timing": {**shared["timing"], "after": "overcredited possible compensator"}, "load": {**shared["load"], "after": "boundary diagnostic not jointly revisited"}}, "structure_recovered_on_frozen_mechanism_fixture": closure["sequential_no_revisit"]["structure_recovered"], "physical_truth_claim": False},
        {"method": "full_batch", "order": chronological, "recomputed_decision_count": full_count, "graph_edit_count": len(edits), "conclusions": copy.deepcopy(shared), "structure_recovered_on_frozen_mechanism_fixture": closure["full_batch"]["structure_recovered"], "fixture_sse": closure["full_batch"]["sse"], "physical_truth_claim": False},
        {"method": "sail_sparse_loop_closure", "order": chronological, "recomputed_decision_count": sparse_count, "graph_edit_count": len(edits), "conclusions": copy.deepcopy(shared), "structure_recovered_on_frozen_mechanism_fixture": closure["sparse"]["structure_recovered"], "fixture_sse": closure["sparse"]["sse"], "sparse_full_score_loss_fraction": closure["comparison"]["sparse_full_score_loss_fraction"], "unaffected_posterior_digests_unchanged": closure["sparse"]["unaffected_posterior_digests_unchanged"], "physical_truth_claim": False},
    ]


def _certificate(config: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    fidelity = sources["fidelity_closeout"]
    grasp = sources["grasp_closeout"]
    invariance = sources["retained_invariance"]
    gates = {
        "TW-G0": {"status": "pass", "reason": "11 retained episode action hashes are byte-identical across the frozen replay lane and evaluator identities are bound", "evidence_ids": ["grasp-closeout-action-invariance", "belief-graph-evaluator-bindings"]},
        "TW-G1": {"status": "pass", "reason": "whole-episode joint, gripper, end-effector, and timing evidence is present; joint and EE RMS improve without source-action mutation", "evidence_ids": ["phase-aligned-residual-field", "fidelity-rms-closeout"]},
        "TW-G2": {"status": "not_evaluable", "reason": "physical contact state/force and metric object trajectories are absent; heuristic contact cannot count as measured interaction fidelity", "evidence_ids": ["retained-invariance-missing-contact-observables", "grasp-closeout-terminal-negative"]},
        "TW-G3": {"status": "not_evaluable", "reason": "three learned-policy candidates with independent physical outcomes and simulator ranking are absent", "evidence_ids": []},
        "TW-G4": {"status": "not_evaluable", "reason": f"all {invariance['counts']['mechanism_count']} retained mechanism invariance checks are not evaluable", "evidence_ids": ["retained-invariance-inventory"]},
    }
    level = resolve_level(gates)
    _require(level == config["acceptance"]["expected_current_twin_worthiness_level"], "unexpected TwinWorthiness level")
    capabilities = capabilities_for_level(level)
    evaluator_identity = canonical_digest(sorted({row["source"].get("evaluator_identity", "") for row in sources["belief_graph"]["nodes"] if row["source"].get("evaluator_identity")}))
    unsigned = {
        "schema_version": "sim2claw.twin_worthiness_certificate.v1",
        "certificate_id": "retired-workcell-current-20260722-v1",
        "campaign_id": config["campaign_id"],
        "identities": {
            "evidence": [config["source_bindings"][name]["sha256"] for name in ("evidence_catalog", "residual_field", "influence_set", "retained_invariance")],
            "graph": config["source_bindings"]["belief_graph"]["sha256"],
            "posterior": config["source_bindings"]["retained_particles"]["sha256"],
            "simulator": config["source_bindings"]["fidelity_closeout"]["sha256"],
            "evaluator": evaluator_identity,
            "policy_candidates": [],
        },
        "gates": gates,
        "level": level,
        "authority": {"data_generation": capabilities["data_generation"], "policy_selection": capabilities["policy_selection"], "physical_canary": capabilities["physical_canary"], "robot_motion": False},
        "issued_at": config["generated_at"],
    }
    certificate = seal_contract(unsigned)
    verify_contract(certificate)
    _require(certificate["gates"]["TW-G2"]["status"] != "pass" and not certificate["authority"]["data_generation"], "TW-G2/TW-DATA opened without evidence")
    _require(fidelity["advancement_gates"]["action_invariance_gate"] and grasp["action_invariance"]["all_candidate_episode_arrays_byte_identical"], "replay identity did not pass")
    return certificate


def _timeline_svg(timeline: list[dict[str, Any]]) -> str:
    width, row_height = 1240, 54
    height = 92 + row_height * len(timeline)
    colors = {"trace_fidelity_accepted": "#16a34a", "bounded_sensitivity_win": "#2563eb", "partial_improvement": "#d97706", "closed": "#dc2626"}
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="#f8fafc"/>', '<text x="28" y="38" font-family="system-ui" font-size="24" font-weight="700" fill="#0f172a">Retired-workcell intervention history</text>', '<text x="28" y="64" font-family="system-ui" font-size="13" fill="#475569">Development-informed retrospective evidence; no row is prospective or fresh held-out.</text>']
    for index, row in enumerate(timeline):
        y = 92 + index * row_height
        color = colors.get(row["candidate_status"], "#64748b")
        lines.extend([f'<circle cx="42" cy="{y}" r="9" fill="{color}"/>', f'<line x1="42" y1="{y + 9}" x2="42" y2="{y + row_height - 9}" stroke="#cbd5e1" stroke-width="2"/>', f'<text x="68" y="{y - 4}" font-family="system-ui" font-size="14" font-weight="650" fill="#0f172a">{html.escape(row["label"])}</text>', f'<text x="68" y="{y + 17}" font-family="ui-monospace" font-size="11" fill="#475569">{html.escape(row["candidate_status"])} · {html.escape(", ".join(row["declared_scopes"]))}</text>', f'<text x="910" y="{y + 8}" font-family="ui-monospace" font-size="10" fill="#64748b">{html.escape(row["source_sha256"][:18])}…</text>'])
    lines.append('</svg>')
    return "\n".join(lines)


def _comparison_svg(rows: list[dict[str, Any]]) -> str:
    width, height = 1240, 430
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="#ffffff"/>', '<text x="28" y="38" font-family="system-ui" font-size="24" font-weight="700" fill="#0f172a">Reconstruction comparison</text>', '<text x="28" y="64" font-family="system-ui" font-size="13" fill="#475569">Numerical structure recovery is from the frozen mechanism fixture; retrospective conclusions remain explanatory, not physical identification.</text>', '<text x="34" y="105" font-family="system-ui" font-size="12" font-weight="700">method</text>', '<text x="510" y="105" font-family="system-ui" font-size="12" font-weight="700">recomputed</text>', '<text x="650" y="105" font-family="system-ui" font-size="12" font-weight="700">graph edits</text>', '<text x="790" y="105" font-family="system-ui" font-size="12" font-weight="700">fixture recovery</text>']
    for index, row in enumerate(rows):
        y = 138 + index * 56
        fill = "#f1f5f9" if index % 2 == 0 else "#ffffff"
        recovered = row.get("structure_recovered_on_frozen_mechanism_fixture", "n/a")
        lines.extend([f'<rect x="24" y="{y - 24}" width="1188" height="44" rx="7" fill="{fill}"/>', f'<text x="34" y="{y + 3}" font-family="ui-monospace" font-size="13" fill="#0f172a">{html.escape(row["method"])}</text>', f'<text x="540" y="{y + 3}" font-family="ui-monospace" font-size="13" fill="#0f172a">{row["recomputed_decision_count"]}</text>', f'<text x="690" y="{y + 3}" font-family="ui-monospace" font-size="13" fill="#0f172a">{row["graph_edit_count"]}</text>', f'<text x="840" y="{y + 3}" font-family="ui-monospace" font-size="13" fill="#0f172a">{str(recovered).lower()}</text>'])
    lines.extend(['<text x="28" y="410" font-family="system-ui" font-size="12" fill="#7f1d1d">Current certificate: TW-REPLAY. TW-G2 and TW-DATA remain closed.</text>', '</svg>'])
    return "\n".join(lines)


def build_case(config: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    graph = sources["belief_graph"]
    influence = sources["influence_set"]
    closure = validate_loop_closure(sources["sparse_loop_closure"])
    timeline = _timeline(graph)
    edits = _graph_edits(graph, influence)
    _require(len(timeline) == config["acceptance"]["expected_intervention_count"], "history count changed")
    _require(len(edits) == config["acceptance"]["expected_graph_edit_count"], "graph edit count changed")
    _require(influence["metrics"]["precision"] == config["acceptance"]["expected_influence_precision"] and influence["metrics"]["recall"] == config["acceptance"]["expected_influence_recall"], "influence recovery changed")
    reconstructions = _reconstructions(config, timeline, closure, edits)
    certificate = _certificate(config, sources)
    unsigned = {
        "schema_version": CASE_SCHEMA,
        "campaign_id": config["campaign_id"],
        "proof_class": config["proof_class"],
        "claim_boundary": "Development-informed retrospective reconstruction only. The seeded benchmark carries unbiased structural recovery; explanatory simulator mechanisms are not measured physical parameters.",
        "history": timeline,
        "findings": _findings(sources["fidelity_closeout"], sources["grasp_closeout"], sources["friction_closeout"]),
        "influence_discovery": {"mechanism_family": influence["mechanism_family"], "affected_intervention_ids": influence["affected_intervention_ids"], "precision": influence["metrics"]["precision"], "recall": influence["metrics"]["recall"], "physical_cause_asserted": influence["physical_cause_asserted"]},
        "graph_edits": edits,
        "reconstructions": reconstructions,
        "conclusion_changes": _conclusions(),
        "twin_worthiness_certificate": certificate,
        "acceptance": {"historical_rows_relabelled": False, "every_graph_edit_source_bound": True, "explanatory_mechanisms_are_measured_parameters": False, "tw_g2_closed": certificate["gates"]["TW-G2"]["status"] != "pass", "tw_data_closed": not certificate["authority"]["data_generation"], "action_bytes_unchanged": True, "historical_results_mutated": False},
        "authority": copy.deepcopy(config["authority"]),
    }
    return {**unsigned, "case_digest": canonical_digest(unsigned)}


def verify_receipt(receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "unexpected retrospective receipt schema")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "retrospective receipt digest mismatch")
    _require(not any(normalized["authority"].values()), "retrospective receipt authority widened")
    config_path = _repo_path(repo_root, normalized["config"]["path"], "receipt config")
    _require(sha256_file(config_path) == normalized["config"]["sha256"], "retrospective config changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        _require(path.is_file() and sha256_file(path) == binding["sha256"], f"retrospective output changed: {name}")
    return {**normalized, "receipt_digest": observed}


def compile_case(config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_config(resolved, repo_root=repo_root)
    sources = _sources(config, repo_root)
    case = build_case(config, sources)
    output_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_root / "retrospective_case.json", case)
    atomic_write_json(output_root / "twin_worthiness_certificate.json", case["twin_worthiness_certificate"])
    (output_root / "history_timeline.svg").write_text(_timeline_svg(case["history"]), encoding="utf-8")
    (output_root / "reconstruction_comparison.svg").write_text(_comparison_svg(case["reconstructions"]), encoding="utf-8")
    outputs = {name: {"path": path.name, "sha256": sha256_file(path)} for name, path in {
        "case": output_root / "retrospective_case.json",
        "certificate": output_root / "twin_worthiness_certificate.json",
        "history_figure": output_root / "history_timeline.svg",
        "comparison_figure": output_root / "reconstruction_comparison.svg",
    }.items()}
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)},
        "compiler_sha256": sha256_file(repo_root / "src/sim2claw/sail/retrospective_case.py"),
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "counts": {"history_items": len(case["history"]), "findings": len(case["findings"]), "graph_edits": len(case["graph_edits"]), "reconstructions": len(case["reconstructions"]), "figures": 2},
        "twin_worthiness": {"level": case["twin_worthiness_certificate"]["level"], "tw_g2_status": case["twin_worthiness_certificate"]["gates"]["TW-G2"]["status"], "data_generation": case["twin_worthiness_certificate"]["authority"]["data_generation"]},
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {"schema_version": "sim2claw.sail_retrospective_case_compile_result.v1", "status": "compiled", "counts": receipt["counts"], "twin_worthiness": receipt["twin_worthiness"], "case_sha256": outputs["case"]["sha256"], "certificate_sha256": outputs["certificate"]["sha256"], "receipt_sha256": sha256_file(output_root / "receipt.json"), "receipt_digest": receipt["receipt_digest"], "output_root": str(output_root), "training_admitted": False, "physical_authority": False}


__all__ = ["RetrospectiveCaseError", "build_case", "compile_case", "load_config", "verify_receipt"]
