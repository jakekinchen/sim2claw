from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.interaction_events import (
    ANNOTATION_SCHEMA,
    CLAIM_BOUNDARY,
    DEFAULT_CONTRACT_PATH,
    SIM_TRACE_SCHEMA,
    InteractionEventError,
    InteractionEventSession,
    compare_event_conditioned_real_sim,
    compile_annotation_consensus,
    load_event_contract,
    materialize_interaction_event_pipeline,
)
from sim2claw.learning_factory_artifacts import load_json_object


def test_event_contract_and_train_materialization_are_deterministic(
    tmp_path: Path,
) -> None:
    contract = load_event_contract()
    assert contract["authority"]["physical_authority"] is False
    first = materialize_interaction_event_pipeline(
        tmp_path / "first", render_visuals=False
    )
    second = materialize_interaction_event_pipeline(
        tmp_path / "second", render_visuals=False
    )
    assert first["corpus_sha256"] == second["corpus_sha256"]
    assert first["partition"] == "train"
    assert first["episode_count"] == first["independent_episode_count"] == 15
    assert first["sample_count"] == 6486
    assert first["event_candidate_count"] == 90
    assert first["phase_interval_count"] == 75
    assert sum(first["phase_counts"].values()) == 6486
    sampler = load_json_object(
        tmp_path / "first" / "phase_balanced_sampler_manifest.json"
    )
    assert sampler["source_episode_count"] == 15
    assert sampler["unique_source_row_count"] == 6486
    assert sampler["independent_episode_count"] == 15
    assert sampler["training_admission_granted"] is False
    assert len(
        {(row["recording_id"], row["sample_index"]) for row in sampler["rows"]}
    ) == 6486
    assert sum(row["normalized_probability"] for row in sampler["rows"]) == pytest.approx(1.0)


def test_held_out_requires_evaluator_and_phases_cover_every_row(
    tmp_path: Path,
) -> None:
    with pytest.raises(InteractionEventError, match="evaluator-owned"):
        materialize_interaction_event_pipeline(
            tmp_path / "forbidden",
            partition="held_out",
            render_visuals=False,
        )
    corpus = materialize_interaction_event_pipeline(
        tmp_path / "held-out",
        partition="held_out",
        evaluator_owned=True,
        render_visuals=False,
    )
    assert corpus["episode_count"] == 3
    assert corpus["sample_count"] == 1255
    assert {row["move_id"] for row in corpus["episodes"]} == {
        "c2_to_c1",
        "e1_to_f1",
        "g1_to_g2",
    }
    for episode in corpus["episodes"]:
        event = load_json_object(tmp_path / "held-out" / episode["events_path"])
        phases = event["phase_intervals"]
        assert [row["phase"] for row in phases] == [
            "approach_open",
            "closure_transition",
            "closed_transport_candidate",
            "release_transition",
            "retraction_open",
        ]
        assert sum(row["sample_count"] for row in phases) == event["sample_count"]
        assert event["mechanical_load_proxy"]["physical_contact_observed"] is False
        assert event["receipt_outcome"]["available_to_visual_annotator"] is False


def test_visual_strip_session_annotation_and_consensus(tmp_path: Path) -> None:
    root = tmp_path / "visual"
    corpus = materialize_interaction_event_pipeline(root, render_visuals=True)
    episode = corpus["episodes"][0]
    strip = root / str(episode["strip_path"])
    assert strip.is_file()
    event = load_json_object(root / episode["events_path"])
    assert event["visual_evidence"]["status"] == "materialized"
    assert len(event["visual_evidence"]["slots"]) == 9
    assert max(
        abs(row["decode_time_error_seconds"])
        for row in event["visual_evidence"]["slots"]
    ) <= 1.0 / event["visual_evidence"]["source_fps"]

    session = InteractionEventSession(
        episode,
        root,
        root / "state",
        reset=True,
    )
    recording_id = episode["recording_id"]
    status = session.event_status(recording_id)
    assert status["receipt_outcome_available_to_annotator"] is False
    metadata, returned_strip = session.read_interaction_strip(recording_id)
    assert returned_strip == strip.resolve()
    assert metadata["receipt_outcome_shown"] is False
    fields = {
        field: "ambiguous"
        for field in load_event_contract()["visual_annotation"]["fields"]
    }
    accepted = session.submit_visual_annotation(
        recording_id,
        {
            "fields": fields,
            "occlusion": "partial",
            "confidence": "low",
            "rationale": "The gripper occludes the candidate contact region.",
            "annotator_system": "codex_cli",
            "model_identifier": "fixture-codex",
            "prompt_sha256": status["visual_annotation_prompt_sha256"],
        },
    )
    receipt = session.submit_event_audit(
        recording_id,
        status["event_episode_sha256"],
        accepted["annotation_sha256"],
        CLAIM_BOUNDARY,
    )
    assert receipt["audit_complete"] is True
    assert receipt["annotation_correctness_scored"] is False

    first_annotation = session.state["annotation"]
    second_annotation = copy.deepcopy(first_annotation)
    second_annotation.pop("annotation_sha256")
    second_annotation["annotator_system"] = "claude_code"
    second_annotation["model_identifier"] = "fixture-claude"
    second_annotation["fields"]["release_visible"] = "visible_yes"
    consensus = compile_annotation_consensus([first_annotation, second_annotation])
    assert consensus["annotation_count"] == 2
    assert consensus["fields"]["release_visible"]["consensus"] == "disagreement"
    assert consensus["model_judge_used"] is False
    assert consensus["ground_truth_claimed"] is False


def test_event_conditioned_real_sim_comparison_requires_exact_replay(
    tmp_path: Path,
) -> None:
    root = tmp_path / "events"
    corpus = materialize_interaction_event_pipeline(root, render_visuals=False)
    manifest = corpus["episodes"][0]
    event = load_json_object(root / manifest["events_path"])
    phase_rows = load_json_object(root / manifest["phase_rows_path"])
    sim_trace = {
        "schema_version": SIM_TRACE_SCHEMA,
        "recording_id": event["recording_id"],
        "rows": [
            {
                "sample_index": row["sample_index"],
                "simulated_joint_position_source_units": row[
                    "measured_joint_position"
                ],
                "simulated_joint_velocity_source_units": row[
                    "measured_joint_velocity"
                ],
            }
            for row in phase_rows["rows"]
        ],
    }
    attestation = {
        "exact_replay_eligible": True,
        "transform_status": "approved",
        "approved_transform_sha256": "a" * 64,
        "clipping_count": 0,
        "repaired_row_count": 0,
        "canonical_velocity": True,
        "source_samples_sha256": event["source_samples_sha256"],
    }
    result = compare_event_conditioned_real_sim(
        event, phase_rows, sim_trace, attestation
    )
    assert result["exact_row_alignment"] is True
    assert result["comparison_scope"] == "event_conditioned_joint_tracking_only"
    assert result["phase_metrics"][0]["joint_metrics"][0][
        "simulated_minus_real_position"
    ]["rmse"] == 0.0
    clipped = {**attestation, "clipping_count": 1}
    with pytest.raises(InteractionEventError, match="clipping"):
        compare_event_conditioned_real_sim(event, phase_rows, sim_trace, clipped)


def test_event_contract_rejects_authority_widening(tmp_path: Path) -> None:
    contract = load_json_object(DEFAULT_CONTRACT_PATH)
    contract["authority"]["infer_measured_contact"] = True
    path = tmp_path / "widened.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(InteractionEventError, match="authority widened"):
        load_event_contract(path)


def test_annotation_schema_rejects_outcome_leak(tmp_path: Path) -> None:
    root = tmp_path / "events"
    corpus = materialize_interaction_event_pipeline(root, render_visuals=False)
    episode = corpus["episodes"][0]
    session = InteractionEventSession(
        episode,
        root,
        root / "state",
        reset=True,
    )
    status = session.event_status(episode["recording_id"])
    config = load_event_contract()["visual_annotation"]
    leaked = {
        "schema_version": ANNOTATION_SCHEMA,
        "recording_id": episode["recording_id"],
        "event_episode_sha256": status["event_episode_sha256"],
        "fields": {field: "ambiguous" for field in config["fields"]},
        "occlusion": "unknown",
        "confidence": "low",
        "rationale": "",
        "annotator_system": "fixture",
        "model_identifier": "fixture",
        "prompt_sha256": status["visual_annotation_prompt_sha256"],
        "receipt_outcome_shown": True,
    }
    from sim2claw.interaction_events import validate_visual_annotation

    with pytest.raises(InteractionEventError, match="outcome leaked"):
        validate_visual_annotation(leaked)
