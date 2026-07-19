from __future__ import annotations

import copy
import hashlib
import json
import socket
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from urllib.request import urlopen

import pytest

from sim2claw.cli import build_parser
from sim2claw.learning_factory import (
    STAGE_IDS,
    LearningFactory,
    LearningFactoryError,
    validate_stage_graph,
)
from sim2claw.learning_factory_artifacts import (
    FactoryArtifactError,
    admit_correction_candidate,
    admit_dataset_candidates,
    atomic_write_json,
    bind_narrow_act_evidence,
    capture_training_candidate,
    compare_calibration_candidates,
    compile_cousin_batch,
    normalize_counterexamples,
    update_counterexample_registry,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.project_bundle import (
    EXPECTED_BG_SKILL_IDS,
    EXPECTED_BG_SKILL_SPECS,
    PROJECT_AUTHORITY_CONTRACT,
    PROJECT_BUNDLE_ENTRIES,
    PROJECT_PIPELINE_CONTRACT,
    PROJECT_TRAINING_LOCK,
)
from sim2claw.studio_server import create_server


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_factory_project(
    repo: Path,
    *,
    project_id: str = "learning-factory-fixture",
    profile: str = "deterministic_fixture",
) -> Path:
    graph_path = repo / "configs/learning_factory/graph_v1.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_bytes(
        (REPO_ROOT / "configs/learning_factory/graph_v1.json").read_bytes()
    )
    contract_path = repo / "configs/evaluations/frozen.json"
    catalog_path = repo / "configs/data/physical_pawn_move_catalog_20260719.json"
    state_path = repo / "docs/autonomous-workflow/project_state.json"
    project_path = Path(f"configs/projects/{project_id}.json")
    _write_json(
        contract_path,
        {
            "schema_version": "sim2claw.pawn_bidirectional_composability_eval.v2",
            "evaluation_set_id": f"{project_id}-evaluation",
            "benchmark_scope": {
                "current_physical_corpus": catalog_path.relative_to(repo).as_posix()
            },
            "skills": list(EXPECTED_BG_SKILL_SPECS),
        },
    )
    _write_json(
        catalog_path,
        {
            "schema_version": "sim2claw.physical_pawn_move_catalog.v1",
            "catalog_id": f"{project_id}-catalog",
            "episodes": [{"recording_id": "fixture-episode"}],
        },
    )
    _write_json(
        state_path,
        {
            "schema_version": "sim2claw.autonomous_project_state.v1",
            "locked_product_evaluation": {
                "evaluation_set_id": f"{project_id}-evaluation",
                "contract": contract_path.relative_to(repo).as_posix(),
                "sha256": _sha256(contract_path),
                "core_directed_cases": 12,
                "files": list("bcdefg"),
                "current_catalog_episode_count": 1,
            },
            "training_lock": PROJECT_TRAINING_LOCK,
            "promotion_owner": PROJECT_PIPELINE_CONTRACT["promotion_owner"],
            "workspace_registration": {"status": "unqualified"},
            "recorded_action_replay": {
                "status": "fixture_ready" if profile != "physical_campaign" else "not_ready",
                "joint_timing_replay_ready_count": 3 if profile != "physical_campaign" else 0,
                "physical_joint_transform_status": "approved" if profile != "physical_campaign" else "provisional_unapproved",
            },
        },
    )
    _write_json(
        repo / "datasets/manipulation_source_recordings/fixture.json",
        {"proof_class": "physical_teleoperation_source_unqualified"},
    )
    _write_json(
        repo / "outputs/pawn_composability/recovered_corpus_v2/fixture.json",
        {"proof_class": "retrospective_source_score_and_review_material"},
    )
    capture_path = repo / "configs/polycam/fixture.json"
    mass_path = repo / "calibration/so101/fixture.json"
    sysid_path = repo / "configs/sysid/fixture.json"
    _write_json(
        capture_path,
        {"simulation_estimates": {"board": {"scene_id": "fixture-scene"}}},
    )
    _write_json(
        mass_path,
        {"schema_version": "sim2claw.so101_mass_profile.v1", "fixture": True},
    )
    _write_json(sysid_path, {"fixture": True})
    _write_json(
        repo / project_path,
        {
            "schema_version": "sim2claw.project.v1",
            "project_id": project_id,
            "source_of_truth": {
                "project_state": state_path.relative_to(repo).as_posix(),
                "project_state_sha256": _sha256(state_path),
                "evaluation_contract": contract_path.relative_to(repo).as_posix(),
                "evaluation_contract_sha256": _sha256(contract_path),
                "physical_source_catalog": catalog_path.relative_to(repo).as_posix(),
                "physical_source_catalog_sha256": _sha256(catalog_path),
            },
            "scope": {
                "files": list("bcdefg"),
                "ranks": [1, 2],
                "directed_skill_count": 12,
                "directed_skill_ids": list(EXPECTED_BG_SKILL_IDS),
                "include_a_or_h": False,
            },
            "bundle_entries": list(PROJECT_BUNDLE_ENTRIES),
            "pipeline": copy.deepcopy(PROJECT_PIPELINE_CONTRACT),
            "learning_factory": {
                "graph": graph_path.relative_to(repo).as_posix(),
                "profile": profile,
                "visual_context": {"required": False, "reason": "fixture"},
                "twin_candidate": {
                    "scene_id": "fixture-scene",
                    "capture_config": capture_path.relative_to(repo).as_posix(),
                    "mass_profile": mass_path.relative_to(repo).as_posix(),
                    "proof_class": "fixture",
                },
                "source_mode": "canonical_physical_catalog",
                "replay": {
                    "sysid_config": sysid_path.relative_to(repo).as_posix(),
                    "minimum_ready_episodes": 2,
                    "split_strategy": "deterministic_hash",
                    "held_out_column": None,
                },
            },
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        },
    )
    return project_path


def _calibration_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    experiment = {
        "schema_version": "sim2claw.calibration_experiment.v1",
        "experiment_id": "cal-v1",
        "calibration_episode_ids": ["c1"],
        "validation_episode_ids": ["v1"],
        "held_out_episode_ids": ["h1"],
        "minimum_normalized_sensitivity": 0.05,
        "minimum_improved_fidelity_metrics": 3,
        "parameters": [
            {
                "name": "friction",
                "lower": 0.1,
                "upper": 1.0,
                "normalized_sensitivity": 0.2,
            }
        ],
    }
    baseline = {
        "twin_id": "base",
        "evaluated_episode_ids": ["v1"],
        "trajectory_rmse": 1.0,
        "contact_timing_mae": 1.0,
        "outcome_disagreement_rate": 0.5,
        "sim_real_success_gap": 0.4,
        "simulated_policy_success_rate": 0.95,
    }
    candidate = {
        "twin_id": "candidate",
        "evaluated_episode_ids": ["v1"],
        "trajectory_rmse": 0.5,
        "contact_timing_mae": 0.4,
        "outcome_disagreement_rate": 0.2,
        "sim_real_success_gap": 0.1,
        "simulated_policy_success_rate": 0.7,
    }
    return experiment, baseline, candidate


def test_graph_is_exact_and_rejects_forward_dependency() -> None:
    graph = json.loads(
        (REPO_ROOT / "configs/learning_factory/graph_v1.json").read_text()
    )
    assert tuple(item["stage_id"] for item in validate_stage_graph(graph)["stages"]) == STAGE_IDS
    graph["stages"][0]["dependencies"] = ["LF-01"]
    with pytest.raises(LearningFactoryError, match="forward dependency"):
        validate_stage_graph(graph)


def test_factory_fixture_completes_all_stages_and_preserves_negative(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    report = factory.run_range("LF-00", "LF-13")
    assert report["final_status"] == "passed"
    assert len(report["results"]) == 14
    doctor = report["results"][0]["output"]["doctor"]
    assert doctor["passed"] is True
    assert doctor["physical_authority"] is False
    status = factory.status()
    assert status["overall_status"] == "passed"
    dataset = factory.explain("LF-09")["latest_result"]["output"]
    assert dataset["accepted_count"] == 1
    assert dataset["held_out_training_rows"] == 0
    assert dataset["rejected_training_rows"] == 0
    scorecard = factory.explain("LF-11")["latest_result"]["output"]
    assert scorecard["eligible_candidate_ids"] == ["fixture-candidate-v2"]
    assert scorecard["terminal_negative_candidate_ids"] == [
        "fixture-terminal-negative-v1"
    ]
    promotion = factory.explain("LF-13")["latest_result"]["output"]
    assert promotion["state"] == "promoted"
    assert promotion["physical_authority"] is False


def test_false_lineage_local_act_profile_is_quarantined(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path, profile="local_act_fixture")
    with pytest.raises(LearningFactoryError, match="quarantined"):
        LearningFactory(project, repo_root=tmp_path)


def test_physical_campaign_stops_at_replay_readiness(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path, profile="physical_campaign")
    factory = LearningFactory(project, repo_root=tmp_path)
    for stage in ("LF-00", "LF-01", "LF-02"):
        assert factory.run_stage(stage)["status"] == "passed"
    with (
        patch(
            "sim2claw.learning_factory_components.validate_twin_candidate",
            return_value={
                "passed": True,
                "gates": {"fixture": True},
                "twin_candidate_id": "fixture",
            },
        ),
        patch(
            "sim2claw.learning_factory_components.inspect_demonstration_inputs",
            return_value={
                "joint_replay_ready_episode_count": 0,
                "physical_joint_transform": {
                    "calibration_approved": False,
                    "review_status": "provisional_unapproved",
                },
                "aggregate_joint_limit_validation": {
                    "all_audited_values_within_limits": False,
                    "measured_trajectory": {"violating_row_count": 1},
                    "recorded_commands": {"violating_row_count": 1},
                },
                "aggregate_observable_status": {},
            },
        ),
    ):
        assert factory.run_stage("LF-03")["status"] == "passed"
        assert factory.run_stage("LF-04")["status"] == "passed"
    readiness = factory.run_stage("LF-05")
    assert readiness["status"] == "blocked"
    assert "exact joint/timing replay-ready episodes 0/2 required" in readiness["blockers"]
    assert factory.status()["stages"][6]["status"] == "not_ready"


def test_factory_resume_reuses_unchanged_passed_stages(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    first = factory.run_range("LF-00", "LF-03")
    second = factory.run_range("LF-00", "LF-03")
    assert all(item["status"] == "passed" for item in first["results"])
    assert all(item["reused"] is True for item in second["results"])


def test_factory_lease_prevents_concurrent_stage_owner(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    lease = factory.root / "leases/LF-00.json"
    atomic_write_json(lease, {"attempt_id": "already-running"})
    with pytest.raises(LearningFactoryError, match="active lease"):
        factory.run_stage("LF-00")


def test_factory_recovers_dead_local_stage_lease(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    lease = factory.root / "leases/LF-00.json"
    _write_json(
        lease,
        {
            "schema_version": "sim2claw.learning_factory_lease.v1",
            "stage_id": "LF-00",
            "attempt_id": "dead-owner",
            "hostname": socket.gethostname(),
            "pid": 999_999_999,
            "started_at": "2026-01-01T00:00:00+00:00",
            "heartbeat_at": "2026-01-01T00:00:00+00:00",
            "timeout_seconds": 300,
        },
    )
    result = factory.run_stage("LF-00")
    assert result["status"] == "passed"
    assert not lease.exists()


def test_factory_writes_terminal_attempt_and_immutable_output(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    result = factory.run_stage("LF-00")
    output_ref = result["output_ref"]
    assert output_ref["immutable"] is True
    assert result["output_sha256"] == output_ref["sha256"]
    artifact = tmp_path / output_ref["path"]
    assert _sha256(artifact) == output_ref["sha256"]
    attempt = json.loads(
        (
            factory.root
            / "stages/LF-00/attempts"
            / result["attempt_id"]
            / "attempt.json"
        ).read_text()
    )
    assert attempt["status"] == "passed"
    assert attempt["result_sha256"] == result["result_sha256"]


def test_factory_returns_structured_failed_adapter_result(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    with patch.object(factory, "_execute_adapter", side_effect=RuntimeError("boom")):
        result = factory.run_stage("LF-00")
    assert result["status"] == "failed"
    assert result["diagnostics"] == {
        "exception_type": "RuntimeError",
        "exception_message": "boom",
    }
    attempt = json.loads(
        (
            factory.root
            / "stages/LF-00/attempts"
            / result["attempt_id"]
            / "attempt.json"
        ).read_text()
    )
    assert attempt["status"] == "failed"
    assert not (factory.root / "leases/LF-00.json").exists()


def test_factory_campaign_generation_namespaces_evidence(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    project_file = tmp_path / project
    manifest = json.loads(project_file.read_text())
    manifest["learning_factory"]["campaign"] = {
        "campaign_id": "repair-loop",
        "generation": 2,
        "parent_generation": 1,
    }
    _write_json(project_file, manifest)
    factory = LearningFactory(project, repo_root=tmp_path)
    assert factory.context.campaign_id == "repair-loop"
    assert factory.context.generation == 2
    assert factory.context.parent_generation == 1
    assert factory.root.as_posix().endswith(
        "/campaigns/repair-loop/generations/0002"
    )
    result = factory.run_stage("LF-00")
    assert result["campaign_id"] == "repair-loop"
    assert result["generation"] == 2


def test_factory_recursion_inherits_parent_and_produces_child_verdict(
    tmp_path: Path,
) -> None:
    project = _write_factory_project(tmp_path)
    parent = LearningFactory(project, repo_root=tmp_path)
    assert parent.run_range("LF-00", "LF-13")["final_status"] == "passed"
    result = parent.fork_generation(route_targets=["LF-08"], through="LF-11")
    assert result["parent_generation"] == 0
    assert result["generation"] == 1
    assert result["first_stage"] == "LF-08"
    assert len(result["inherited"]) == 8
    assert result["run"]["final_status"] == "passed"
    child = LearningFactory(
        project, repo_root=tmp_path, generation=1, parent_generation=0
    )
    assert child.explain("LF-07")["latest_result"]["proof_class"] == (
        "inherited_parent_generation_evidence"
    )
    assert child.explain("LF-11")["latest_result"]["generation"] == 1


def test_factory_receipt_binds_declared_adapter_and_component_identity(
    tmp_path: Path,
) -> None:
    project = _write_factory_project(tmp_path)
    result = LearningFactory(project, repo_root=tmp_path).run_stage("LF-00")
    assert result["adapter"]["stage_id"] == "LF-00"
    assert result["adapter"]["verdict_owner"] == "project_contract_validator"
    modules = {
        row["module"]: row for row in result["implementation"]["modules"]
    }
    assert modules["sim2claw.project_bundle"]["present"] is True
    assert len(modules["sim2claw.project_bundle"]["sha256"]) == 64
    assert result["implementation"]["git"]["available"] is False


def test_factory_rejects_tampered_authority_receipt(tmp_path: Path) -> None:
    project = _write_factory_project(tmp_path)
    factory = LearningFactory(project, repo_root=tmp_path)
    factory.run_stage("LF-00")
    latest = factory.root / "stages/LF-00/latest.json"
    result = json.loads(latest.read_text())
    result["authority"]["training_can_promote_itself"] = True
    _write_json(latest, result)
    with pytest.raises(LearningFactoryError, match="authority mismatch"):
        factory.status()


def test_calibration_admits_fidelity_even_when_sim_success_drops() -> None:
    experiment, baseline, candidate = _calibration_inputs()
    result = compare_calibration_candidates(experiment, baseline, candidate)
    assert result["verdict"] == "admitted"
    assert result["policy_probe"]["candidate_sim_success_rate"] < result["policy_probe"]["baseline_sim_success_rate"]
    assert result["policy_probe"]["used_for_admission"] is False


def test_calibration_rejects_split_overlap_and_unidentifiable_parameter() -> None:
    experiment, baseline, candidate = _calibration_inputs()
    experiment["held_out_episode_ids"] = ["v1"]
    with pytest.raises(FactoryArtifactError, match="overlap"):
        compare_calibration_candidates(experiment, baseline, candidate)
    experiment, baseline, candidate = _calibration_inputs()
    experiment["parameters"][0]["normalized_sensitivity"] = 0.001
    assert compare_calibration_candidates(experiment, baseline, candidate)["verdict"] == "rejected"


def test_cousin_compiler_bounds_variations_and_roles() -> None:
    spec = {
        "schema_version": "sim2claw.cousin_experiment.v1",
        "experiment_id": "cousins",
        "parent_twin_id": "twin",
        "max_candidates": 1,
        "variation_envelope": {
            "maximum_planar_offset_m": 0.01,
            "allowed_distractors": ["none"],
        },
        "proposals": [
            {
                "source_cell": "b1",
                "target_offset_xy_m": [0.005, 0.0],
                "distractor": "none",
                "role": "held_out",
            }
        ],
    }
    result = compile_cousin_batch(spec)
    assert result["roles"]["held_out"] == 1
    spec["proposals"][0]["target_offset_xy_m"] = [0.02, 0.0]
    with pytest.raises(FactoryArtifactError, match="escapes"):
        compile_cousin_batch(spec)


def test_dataset_admission_never_trains_on_heldout_or_rejected() -> None:
    result = admit_dataset_candidates(
        [
            {
                "candidate_id": "train-good",
                "role": "train",
                "source_sha256": "1" * 64,
                "replay_passed": True,
                "evaluator_passed": True,
            },
            {
                "candidate_id": "train-bad",
                "role": "train",
                "source_sha256": "2" * 64,
                "replay_passed": False,
                "evaluator_passed": True,
            },
            {
                "candidate_id": "sealed",
                "role": "held_out",
                "source_sha256": "3" * 64,
                "replay_passed": True,
                "evaluator_passed": True,
            },
        ]
    )
    assert result["training_episode_ids"] == ["train-good"]
    assert result["held_out_training_rows"] == 0
    assert result["rejected_training_rows"] == 0


def test_training_candidate_has_no_evaluation_or_promotion_authority(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"fixture")
    dataset = {
        "dataset_sha256": "1" * 64,
        "held_out_training_rows": 0,
        "rejected_training_rows": 0,
    }
    result = capture_training_candidate(
        checkpoint,
        dataset_receipt=dataset,
        task_id="narrow-act-fixture",
        recipe_id="recipe-v1",
        architecture="ACT",
    )
    assert result["trainer_has_evaluation_authority"] is False
    assert result["trainer_has_promotion_authority"] is False
    dataset["held_out_training_rows"] = 1
    with pytest.raises(FactoryArtifactError, match="held-out"):
        capture_training_candidate(
            checkpoint,
            dataset_receipt=dataset,
            task_id="narrow-act-fixture",
            recipe_id="recipe-v1",
            architecture="ACT",
        )


def test_counterexamples_dedupe_and_guard_heldout_corrections() -> None:
    source = {
        "source_id": "episode-1",
        "candidate_id": "candidate-1",
        "evaluator_id": "evaluator-1",
        "failure_code": "missed_contact",
        "source_role": "debug",
        "trace_sha256": "1" * 64,
        "disposition": "cousin_coverage",
    }
    registry = normalize_counterexamples([source, source])
    assert registry["record_count"] == 1
    assert registry["automatically_admitted_training_rows"] == 0
    heldout = {**registry["records"][0], "source_role": "held_out"}
    with pytest.raises(FactoryArtifactError, match="held-out"):
        admit_correction_candidate(
            heldout,
            intervention_step=10,
            branch_state_sha256="2" * 64,
            corrective_suffix_sha256="3" * 64,
            replay_passed=True,
            evaluator_passed=True,
        )


def test_counterexample_registry_merges_atomically(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    first = {
        "source_id": "source-1",
        "candidate_id": "candidate-1",
        "evaluator_id": "evaluator",
        "failure_code": "missed_contact",
        "source_role": "debug",
        "trace_sha256": "1" * 64,
        "disposition": "cousin_coverage",
    }
    assert update_counterexample_registry(path, [first])["record_count"] == 1
    assert update_counterexample_registry(path, [first])["record_count"] == 1
    conflicting = {**first, "disposition": "calibration"}
    with pytest.raises(FactoryArtifactError, match="conflicting evidence"):
        update_counterexample_registry(path, [conflicting])


def test_narrow_act_evidence_cannot_be_relabelled_as_bg_policy(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"narrow-act")
    digest = _sha256(checkpoint)
    training_path = tmp_path / "training.json"
    evaluation_path = tmp_path / "evaluation.json"
    _write_json(
        training_path,
        {
            "schema_version": "sim2claw.act_training_receipt.v1",
            "task_id": "chess_rook_lift_v1",
            "task_contract_sha256": "1" * 64,
            "dataset": {"held_out_seed_rows": 0},
            "model": {
                "checkpoint": str(tmp_path / "stale-main-checkpoint.pt"),
                "checkpoint_sha256": digest,
            },
        },
    )
    _write_json(
        evaluation_path,
        {
            "schema_version": "sim2claw.act_evaluation_receipt.v1",
            "task_id": "chess_rook_lift_v1",
            "task_contract_sha256": "1" * 64,
            "policy": {"checkpoint_sha256": digest},
            "runtime": {
                "device": "cpu",
                "dtype": "float32",
                "evaluator_owner": "separate_cpu_fp32_process",
            },
            "physical_authority": False,
            "success": False,
        },
    )
    result = bind_narrow_act_evidence(training_path, evaluation_path)
    assert result["verdict"] == "terminal_negative"
    assert result["bg_policy_claim_allowed"] is False
    assert result["physical_authority"] is False


def test_factory_cli_navigation_contract() -> None:
    parser = build_parser()
    assert parser.parse_args(["factory-inspect", "--project", "p.json"]).command == "factory-inspect"
    args = parser.parse_args(
        [
            "factory-run",
            "--project",
            "p.json",
            "--from",
            "LF-03",
            "--through",
            "LF-07",
        ]
    )
    assert args.from_stage == "LF-03"
    assert args.through_stage == "LF-07"


def test_studio_exposes_read_only_factory_stage_rail(tmp_path: Path) -> None:
    project = _write_factory_project(
        tmp_path, project_id="pawn_rank12_reachable_bg_hackathon_v1"
    )
    factory = LearningFactory(project, repo_root=tmp_path)
    factory.run_stage("LF-00")
    server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base}/api/learning-factory") as response:
            payload = json.load(response)
        assert payload["read_only"] is True
        assert payload["execution_endpoint"] is None
        assert payload["promotion_authority"] is False
        assert len(payload["factory"]["stages"]) == 14
        assert payload["campaign_history"][0]["generation"] == 0
        assert payload["campaign_history"][0]["completed_stage_count"] == 1
        evidence = payload["factory"]["stages"][0]["evidence"]
        assert evidence["proof_class"] == "contract_inspection"
        artifact_path = evidence["output_ref"]["path"]
        with urlopen(
            f"{base}/api/learning-factory/artifact?path={quote(artifact_path)}"
        ) as response:
            artifact = json.load(response)
        assert artifact["read_only"] is True
        assert artifact["path"] == artifact_path
        assert artifact["artifact"]["schema_version"] == (
            "sim2claw.factory_project_inspection.v1"
        )
        with urlopen(f"{base}/learning-factory.html") as response:
            page = response.read().decode()
        assert "Learning factory" in page
        assert "Copy resume command" in page
        assert "Campaign history" in page
        assert "Artifact drilldown" in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
