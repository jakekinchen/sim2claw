from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file
from sim2claw.sail.contracts import verify_contract
from sim2claw.sail.retrospective_case import (
    RetrospectiveCaseError,
    build_case,
    compile_case,
    load_config,
    verify_receipt,
)

REPO_ROOT = Path(__file__).parents[1]
CONFIG_PATH = REPO_ROOT / "configs/sail/retrospective_case_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs/sail/retired-workcell-case-v1"


def _loaded() -> tuple[dict, dict[str, dict]]:
    raw = json.loads(CONFIG_PATH.read_text())
    missing = [binding["path"] for binding in raw["source_bindings"].values() if not (REPO_ROOT / binding["path"]).is_file()]
    if missing:
        pytest.skip("owner-local retained sources unavailable: " + ", ".join(missing))
    config = load_config(CONFIG_PATH)
    sources = {name: json.loads((REPO_ROOT / binding["path"]).read_text()) for name, binding in config["source_bindings"].items()}
    return config, sources


def test_history_is_complete_retrospective_and_source_bound() -> None:
    config, sources = _loaded()
    case = build_case(config, sources)
    assert len(case["history"]) == 12
    assert all(not row["prospective"] and not row["fresh_held_out"] for row in case["history"])
    assert all(len(row["source_sha256"]) == 64 for row in case["history"])
    assert {"fixed-pad-09", "timestep-045", "rubber-friction-20"} <= {row["candidate_id"].split(":", 1)[1] for row in case["history"]}


def test_boundary_reversal_mixed_vector_and_union_findings_are_explicit() -> None:
    config, sources = _loaded()
    findings = {row["finding_id"]: row for row in build_case(config, sources)["findings"]}
    assert findings["boundary-load-bias"]["facts"]["at_boundary"] is True
    assert findings["rms-versus-lift-reversal"]["facts"]["candidate_lifts"] < findings["rms-versus-lift-reversal"]["facts"]["baseline_lifts"]
    assert findings["friction-partial-reversal"]["facts"]["ee_rms_guard_pass"] is False
    assert findings["family-union-without-single-model"]["facts"]["union_lifts"] == 6
    assert findings["family-union-without-single-model"]["facts"]["single_candidate_gate_pass"] is False


def test_every_graph_edit_has_intervention_candidate_verdict_bindings() -> None:
    config, sources = _loaded()
    edits = build_case(config, sources)["graph_edits"]
    assert len(edits) == 2
    assert {row["intervention_id"] for row in edits} == {"intervention:fidelity-rms-closeout", "intervention:load-bias-boundary"}
    assert all(len(row["required_edges"]) == 2 and not row["historical_result_mutated"] for row in edits)


def test_five_reconstructions_preserve_honest_fixture_boundary() -> None:
    config, sources = _loaded()
    rows = {row["method"]: row for row in build_case(config, sources)["reconstructions"]}
    assert list(rows) == config["reconstruction_order"]
    assert rows["sequential_no_revisit"]["structure_recovered_on_frozen_mechanism_fixture"] is False
    assert rows["full_batch"]["structure_recovered_on_frozen_mechanism_fixture"] is True
    assert rows["sail_sparse_loop_closure"]["structure_recovered_on_frozen_mechanism_fixture"] is True
    assert rows["sail_sparse_loop_closure"]["recomputed_decision_count"] == 2
    assert rows["full_batch"]["recomputed_decision_count"] == 8
    assert rows["sail_sparse_loop_closure"]["sparse_full_score_loss_fraction"] <= 1e-9
    assert all(not row["physical_truth_claim"] for row in rows.values())


def test_current_certificate_is_tw_replay_and_keeps_data_closed() -> None:
    config, sources = _loaded()
    certificate = build_case(config, sources)["twin_worthiness_certificate"]
    assert verify_contract(certificate)["canonical_digest"] == certificate["canonical_digest"]
    assert certificate["level"] == "TW-REPLAY"
    assert certificate["gates"]["TW-G0"]["status"] == "pass"
    assert certificate["gates"]["TW-G1"]["status"] == "pass"
    assert certificate["gates"]["TW-G2"]["status"] == "not_evaluable"
    assert certificate["authority"] == {"data_generation": False, "policy_selection": False, "physical_canary": False, "robot_motion": False}


def test_conclusions_never_claim_measured_physical_parameters() -> None:
    config, sources = _loaded()
    conclusions = build_case(config, sources)["conclusion_changes"]
    assert set(conclusions) == {"scale", "timing", "deadband", "load", "contact"}
    assert all(row["measured_physical_parameter"] is False for row in conclusions.values())


def test_compile_is_deterministic_and_emits_vector_figures(tmp_path: Path) -> None:
    _loaded()
    first = compile_case(CONFIG_PATH, output_root=tmp_path / "case")
    receipt_sha = sha256_file(tmp_path / "case/receipt.json")
    second = compile_case(CONFIG_PATH, output_root=tmp_path / "case")
    assert first["receipt_digest"] == second["receipt_digest"]
    assert receipt_sha == sha256_file(tmp_path / "case/receipt.json")
    for name, boundary_word in (("history_timeline.svg", "retrospective"), ("reconstruction_comparison.svg", "physical")):
        text = (tmp_path / "case" / name).read_text()
        assert text.startswith("<svg") and boundary_word in text.lower()


def test_receipt_tampering_fails_closed(tmp_path: Path) -> None:
    _loaded()
    compile_case(CONFIG_PATH, output_root=tmp_path / "case")
    receipt = json.loads((tmp_path / "case/receipt.json").read_text())
    verify_receipt(receipt, output_root=tmp_path / "case")
    changed = copy.deepcopy(receipt)
    changed["authority"]["training_admission"] = True
    unsigned = copy.deepcopy(changed)
    unsigned.pop("receipt_digest")
    changed["receipt_digest"] = canonical_digest(unsigned)
    with pytest.raises(RetrospectiveCaseError, match="authority widened"):
        verify_receipt(changed, output_root=tmp_path / "case")


def test_owner_local_output_receipt_verifies_when_present() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local retrospective receipt unavailable")
    verify_receipt(json.loads(path.read_text()), output_root=OUTPUT_ROOT)
