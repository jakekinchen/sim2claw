from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest, load_json_object
from sim2claw.paths import REPO_ROOT
from sim2claw.retrospective_publication import (
    DEFAULT_GATE_PATH,
    RetrospectivePublicationError,
    _normal_inverse_gamma_fit,
    _read_samples,
    build_provider_campaign_manifest,
    build_publication_receipt,
)


CAMPAIGN_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_corrective_provider_campaign_v1.json"
)


def _sample(index: int, timestamp: float) -> dict:
    return {
        "schema_version": "sim2claw.physical_teleoperation_sample.v1",
        "recording_id": "episode-1",
        "sample_index": index,
        "timestamp_monotonic_seconds": timestamp,
        "follower_actual_position_degrees": [0.0] * 6,
        "follower_command_degrees": [0.0] * 6,
        "follower_requested_degrees": [0.0] * 6,
    }


def test_sample_anchor_parser_fails_closed_on_time_or_index_repair(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in (_sample(0, 0.05), _sample(1, 0.05))) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RetrospectivePublicationError, match="strictly increasing"):
        _read_samples(
            path,
            episode_id="episode-1",
            required_schema="sim2claw.physical_teleoperation_sample.v1",
            vector_length=6,
        )

    path.write_text(
        "\n".join(json.dumps(row) for row in (_sample(0, 0.05), _sample(2, 0.10))) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RetrospectivePublicationError, match="not contiguous"):
        _read_samples(
            path,
            episode_id="episode-1",
            required_schema="sim2claw.physical_teleoperation_sample.v1",
            vector_length=6,
        )


def test_episode_level_posterior_is_deterministic_and_declares_its_unit() -> None:
    prior = {"mean": 0.0, "mean_strength": 0.001, "shape": 2.0, "scale": 1.0}
    first = _normal_inverse_gamma_fit([0.1, 0.2, -0.1, 0.0], prior, 0.95, unit="degree")
    second = _normal_inverse_gamma_fit([0.1, 0.2, -0.1, 0.0], prior, 0.95, unit="degree")
    assert first == second
    assert first["unit"] == "degree"
    assert first["independent_unit_count"] == 4
    assert first["mean_distribution"]["quantiles"]["0.5"] == pytest.approx(
        first["posterior"]["mean"]
    )


def test_provider_campaign_is_frozen_dry_run_without_secret_values() -> None:
    manifest = build_provider_campaign_manifest(
        campaign_path=CAMPAIGN_PATH,
        repo_root=REPO_ROOT,
    )
    assert manifest["dry_run"] is True
    assert manifest["job_count"] == 20
    assert manifest["case_attempt_count"] == 240
    assert manifest["readiness"]["execution_ready"] is False
    assert all(job["authorized"] is False for job in manifest["jobs"])
    assert all("api_key" not in " ".join(job["argv"]).lower() for job in manifest["jobs"])
    assert {job["credential_source_env"] for job in manifest["jobs"]} == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MOONSHOT_API_KEY",
        "DASHSCOPE_API_KEY",
    }
    openai_job = next(job for job in manifest["jobs"] if job["treatment_id"] == "openai-gpt-5.6-sol-max")
    fable_job = next(job for job in manifest["jobs"] if job["treatment_id"] == "anthropic-claude-fable-5-max")
    qwen_job = next(job for job in manifest["jobs"] if job["provider"] == "alibaba_model_studio")
    assert openai_job["generate_config"] == {"temperature": 0.0, "reasoning_effort": "max"}
    assert fable_job["generate_config"] == {"effort": "max"}
    assert qwen_job["generate_config"] == {"temperature": 0.0, "extra_body": {"enable_thinking": True}}
    assert "--generate-config" in qwen_job["argv"]


def test_provider_campaign_rejects_authority_widening(tmp_path: Path) -> None:
    campaign = load_json_object(CAMPAIGN_PATH)
    campaign["authority"]["execution_authorized"] = True
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(campaign), encoding="utf-8")
    with pytest.raises(RetrospectivePublicationError, match="became authorized"):
        build_provider_campaign_manifest(campaign_path=path, repo_root=REPO_ROOT)


def test_retrospective_corpus_receipt_is_deterministic_and_terminal_negative() -> None:
    corpus = REPO_ROOT / "datasets" / "manipulation_source_recordings"
    capability_path = REPO_ROOT / "runs" / "sysid" / "physical_pawn_input_capability_post_cherry_pick.json"
    if not corpus.is_dir() or not capability_path.is_file():
        pytest.skip("ignored retrospective physical corpus is not present")
    capability = load_json_object(capability_path)
    first = build_publication_receipt(
        gate_path=DEFAULT_GATE_PATH,
        repo_root=REPO_ROOT,
        capability_report=capability,
    )
    second = build_publication_receipt(
        gate_path=DEFAULT_GATE_PATH,
        repo_root=REPO_ROOT,
        capability_report=capability,
    )
    assert canonical_digest(first) == canonical_digest(second)
    assert first["inventory"]["episode_count"] == 18
    assert first["inventory"]["sample_count"] == 7741
    assert first["inventory"]["catalog_bound_asset_count"] == 54
    assert first["gates"]["real_replay_anchors"]["status"] == "pass"
    assert first["gates"]["exact_simulator_replay"]["status"] == "blocked"
    assert first["tracking_posterior"]["authority"]["diagnostic_physical_observation"] is True
    assert first["tracking_posterior"]["authority"]["domain_randomization_admission"] is False
    assert first["publication_verdict"]["sim_to_real_claim_ready"] is False
    gripper = first["tracking_posterior"]["joints"][-1]
    assert gripper["joint_name"] == "gripper"
    assert gripper["episode_mean_bias_posterior"]["unit"] == "percent"
