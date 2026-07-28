from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import sim2claw.system_identification as sysid
from sim2claw.paths import REPO_ROOT
from sim2claw.physical_gateway import GATEWAY_SCHEMA, SO101_FOLLOWER_ID
from sim2claw.recorded_replay import (
    RecordedEpisode,
    ReplayContractError,
    float64_tensor_sha256,
    load_sysid_config,
    nominal_parameter_values,
    sha256_file,
    simulate_and_align,
)
from sim2claw.replay_eligibility import (
    PHYSICAL_SAMPLE_SCHEMA,
    materialize_physical_recording_exact_replay,
)


CONFIG_PATH = REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json"
TIMING_IDENTITY = {
    "robot": {
        "robot_id": "fixture-so101-follower",
        "follower_port": "/dev/fixture-follower",
        "follower_calibration_sha256": "9" * 64,
        "gateway_schema": "sim2claw.so101_physical_gateway.v2",
    },
    "workspace_pose_id": "fixture-workspace",
}


def _base_episode(
    root: Path,
    config: dict[str, object],
    index: int,
    *,
    hold: bool = False,
) -> RecordedEpisode:
    timestamps = np.linspace(0.0, 1.05, 22, dtype=np.float64)
    commands = np.zeros((timestamps.size, 6), dtype=np.float64)
    if not hold:
        for joint in range(3):
            commands[:, joint] = 0.22 * np.sin(
                (2.0 + 0.2 * index + joint * 0.15) * np.pi * timestamps
                + index * 0.17
            )
    source = root / f"episode-{index}.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    return RecordedEpisode(
        episode_id=f"synthetic-excitation-{index}",
        proof_class="synthetic_timing_actuation_regression",
        proof_class_category="synthetic",
        column=None,
        joint_names=tuple(config["bindings"]["joint_names"]),
        initial_joint_position=np.zeros(6, dtype=np.float64),
        initial_joint_position_units=("radian",) * 6,
        initial_joint_velocity=np.zeros(6, dtype=np.float64),
        initial_joint_velocity_units=("radian_per_second",) * 6,
        timestamps=timestamps,
        original_timestamps=timestamps.copy(),
        commands=commands,
        measured=tuple({"joint_position": [0.0] * 6} for _ in timestamps),
        initial_object_state={"status": "unavailable"},
        unavailable_observables={},
        source_path=source,
        source_sha256="0" * 64,
        source_schema_version="synthetic.v1",
        source_provenance={"chain_complete": True},
        joint_transform=None,
    )


def _known_timing_cohort(
    root: Path,
) -> tuple[list[RecordedEpisode], dict[str, object]]:
    config = copy.deepcopy(load_sysid_config(CONFIG_PATH))
    timing = next(
        stage
        for stage in config["parameter_stages"]
        if stage["name"] == "timing_control"
    )
    timing["parameters"] = [
        parameter
        for parameter in timing["parameters"]
        if parameter["name"] in {"command_latency_seconds", "actuator_gain_scale"}
    ]
    config["optimizer"]["multi_start_count"] = 1
    config["optimizer"]["maximum_iterations"] = 12
    config["optimizer"]["finite_difference_relative_step"] = 0.05
    known = {
        **nominal_parameter_values(config),
        "command_latency_seconds": 0.05,
        "actuator_gain_scale": 1.2,
    }
    episodes: list[RecordedEpisode] = []
    for index in range(5):
        base = _base_episode(root, config, index)
        replay = simulate_and_align(
            base,
            config,
            parameter_values=known,
            model_base_directory=CONFIG_PATH.parent,
        )
        measured = tuple(
            {"joint_position": row.tolist()}
            for row in replay["simulated"]["joint_position"]
        )
        episodes.append(replace(base, measured=measured))
    return episodes, config


def test_known_command_latency_recovery_is_grouped_and_action_frozen(
    tmp_path: Path,
) -> None:
    episodes, config = _known_timing_cohort(tmp_path)
    original_hashes = {
        episode.episode_id: float64_tensor_sha256(episode.commands)
        for episode in episodes
    }

    result = sysid.fit_timing_actuation_cohort(
        episodes,
        config,
        output_directory=tmp_path / "fit",
        backend="local",
        model_base_directory=CONFIG_PATH.parent,
    )

    assert result["status"] == "diagnostic_fit_complete"
    assert result["evaluator_owned"] is False
    assert result["self_scored"] is True
    assert result["evaluator_admission"] is False
    assert result["parameters_promoted"] is False
    assert result["candidate_selection"]["selected_parameters"][
        "command_latency_seconds"
    ] == pytest.approx(0.05, abs=0.006)
    assert set(result["candidate_selection"]["selected_parameters"]) == {
        "command_latency_seconds",
        "actuator_gain_scale",
    }
    assert result["frozen_split"]["counts"] == {
        "train": 3,
        "validation": 1,
        "held_out": 1,
    }
    assert result["held_out"]["open_count"] == 1
    assert result["held_out"]["opened_after_candidate_family_frozen"] is True
    assert result["candidate_selection"]["held_out_used_for_selection"] is False
    assert result["action_identity"]["sha256_by_episode"] == original_hashes
    for candidate in result["candidate_selection"]["candidates"]:
        for split in ("train", "validation"):
            for episode_id, metrics in candidate[split]["by_episode"].items():
                assert metrics["replay_input_action_sha256"] == original_hashes[
                    episode_id
                ]
    held_out_ids = {
        episode_id
        for episode_id, split in result["frozen_split"]["assignments"].items()
        if split == "held_out"
    }
    action_splits = result["action_identity"]["evaluated_splits"]
    assert set(action_splits["held_out_baseline"]) == held_out_ids
    assert set(action_splits["held_out_selected_candidate"]) == held_out_ids
    for key in ("held_out_baseline", "held_out_selected_candidate"):
        for episode_id, digest in action_splits[key].items():
            assert digest == original_hashes[episode_id]


def test_zero_displacement_cohort_is_rejected_before_fit(tmp_path: Path) -> None:
    config = load_sysid_config(CONFIG_PATH)
    episodes = [_base_episode(tmp_path, config, index, hold=True) for index in range(5)]

    result = sysid.fit_timing_actuation_cohort(
        episodes,
        config,
        output_directory=tmp_path / "fit",
        backend="local",
    )

    assert result["status"] == "rejected_low_excitation"
    assert any(
        "hold or lacks variation" in reason
        for reason in result["excitation"]["rejection_reasons"]
    )


def test_empty_optimizer_candidate_list_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_sysid_config(CONFIG_PATH)
    episodes = []
    for index in range(5):
        base = _base_episode(tmp_path, config, index)
        episodes.append(
            replace(
                base,
                measured=tuple(
                    {"joint_position": row.tolist()} for row in base.commands
                ),
            )
        )
    monkeypatch.setattr(
        sysid,
        "fit_parameter_stage",
        lambda *args, **kwargs: {"status": "optimized", "attempts": []},
    )

    with pytest.raises(sysid.SystemIdentificationError, match="no evaluable candidate"):
        sysid.fit_timing_actuation_cohort(
            episodes,
            config,
            output_directory=tmp_path / "fit",
            backend="local",
        )


def test_physical_cohort_reuses_p5_fail_closed_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = {
        "schema_version": sysid.TIMING_COHORT_SCHEMA,
        "identity": TIMING_IDENTITY,
        "episodes": [
            {
                "recording": "recording",
                "exact_replay_manifest": "manifest.json",
            }
        ],
    }
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")

    def reject(*args: object, **kwargs: object) -> None:
        raise ReplayContractError("manifest is ineligible")

    monkeypatch.setattr(sysid, "replay_exact_eligible_physical_recording", reject)
    with pytest.raises(ReplayContractError, match="manifest is ineligible"):
        sysid.run_physical_timing_actuation_cohort(
            cohort_path,
            config_path=CONFIG_PATH,
            output_directory=tmp_path / "fit",
            backend="local",
        )


def test_timing_identity_derives_from_hash_bound_receipt_and_rejects_drift(
    tmp_path: Path,
) -> None:
    recording = tmp_path / "recording"
    recording.mkdir()
    samples = recording / "samples.jsonl"
    samples.write_bytes(b"sealed-sample\n")
    receipt = {
        "backend": {
            "schema_version": GATEWAY_SCHEMA,
            "follower_port": "/dev/fixture-follower",
            "follower_calibration_sha256": "9" * 64,
        },
        "workcell_registration": {"workspace_pose_id": "fixture-workspace"},
        "samples_sha256": sha256_file(samples),
    }
    receipt_path = recording / "recording_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "conversion_provenance": {
                    "recording_receipt_sha256": sha256_file(receipt_path),
                    "samples_sha256": sha256_file(samples),
                }
            }
        ),
        encoding="utf-8",
    )

    assert sysid._derive_timing_evidence_identity(recording, manifest) == {
        "robot": {
            "robot_id": SO101_FOLLOWER_ID,
            "follower_port": "/dev/fixture-follower",
            "follower_calibration_sha256": "9" * 64,
            "gateway_schema": GATEWAY_SCHEMA,
        },
        "workspace_pose_id": "fixture-workspace",
    }

    samples.write_bytes(b"drifted-sample\n")
    with pytest.raises(sysid.SystemIdentificationError, match="samples hash"):
        sysid._derive_timing_evidence_identity(recording, manifest)


def test_valid_p4_recording_loads_as_p9_episode(tmp_path: Path) -> None:
    recording = tmp_path / "recording"
    recording.mkdir()
    rows = [
        {
            "schema_version": PHYSICAL_SAMPLE_SCHEMA,
            "episode_id": "p9-current-recording",
            "sample_index": index,
            "timestamp_monotonic_seconds": 10.0 + index * 0.05,
            "follower_requested_degrees": [index + joint for joint in range(6)],
            "follower_command_degrees": [index + joint for joint in range(6)],
            "follower_actual_position_degrees": [
                index + joint * 2.0 for joint in range(6)
            ],
            "follower_actual_velocity_degrees_s": [
                joint * 0.1 for joint in range(6)
            ],
            "assistance": 0,
            "intervention": 0,
            "rate_limited": False,
            "safety_clamped": False,
        }
        for index in range(3)
    ]
    samples_bytes = b"".join(
        (json.dumps(row, sort_keys=True) + "\n").encode() for row in rows
    )
    (recording / "samples.jsonl").write_bytes(samples_bytes)
    receipt = {
        "schema_version": "sim2claw.manipulation_source_recording_receipt.v1",
        "source_sample_schema": PHYSICAL_SAMPLE_SCHEMA,
        "recording_id": "p9-current-recording",
        "mode": "physical_follower",
        "proof_class": "physical_teleoperation_source_unqualified",
        "source_identity": {
            "kind": "leader_teleoperation",
            "proof_class": "physical_teleoperation_source_unqualified",
        },
        "backend": {"schema_version": "sim2claw.so101_physical_gateway.v2"},
        "sample_count": len(rows),
        "samples_path": "samples.jsonl",
        "samples_sha256": hashlib.sha256(samples_bytes).hexdigest(),
        "assistance_frames": 0,
        "intervention_frames": 0,
        "lineage": {
            "collection_kind": "original_source_episode",
            "corrective_suffix_parent_state_sha256": None,
        },
    }
    (recording / "recording_receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    manifest_path = tmp_path / "exact-replay-manifest.json"
    p4_report = materialize_physical_recording_exact_replay(
        recording,
        manifest_path,
        tmp_path / "exact-replay-report.json",
    )
    assert p4_report["exact_replay_eligible"] is True

    config = load_sysid_config(CONFIG_PATH)
    episode, binding = sysid._load_verified_physical_episode(
        recording,
        manifest_path,
        config=config,
        config_path=CONFIG_PATH,
        verification_directory=tmp_path / "p5-verification",
    )

    expected_actions = np.deg2rad(
        [[index + joint for joint in range(6)] for index in range(3)]
    )
    expected_measured = np.deg2rad(
        [[index + joint * 2.0 for joint in range(6)] for index in range(3)]
    )
    assert episode.original_timestamps == pytest.approx([10.0, 10.05, 10.1])
    assert episode.timestamps == pytest.approx([0.0, 0.05, 0.1])
    assert episode.measured_array("joint_position") == pytest.approx(
        expected_measured
    )
    assert np.array_equal(episode.commands, expected_actions)
    assert binding["p5_byte_identical"] is True
    assert binding["gateway_sent_action_sha256"] == float64_tensor_sha256(
        expected_actions
    )


def test_source_hash_drift_after_p5_verification_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = tmp_path / "recording"
    recording.mkdir()
    (recording / "recording_receipt.json").write_text(
        json.dumps(
            {
                "evidence_identity": TIMING_IDENTITY,
                "backend": {
                    "schema_version": TIMING_IDENTITY["robot"]["gateway_schema"],
                    "follower_port": TIMING_IDENTITY["robot"]["follower_port"],
                    "follower_calibration_sha256": TIMING_IDENTITY["robot"][
                        "follower_calibration_sha256"
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    samples = recording / "samples.jsonl"
    samples.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"evidence_identity": TIMING_IDENTITY}), encoding="utf-8"
    )
    original_samples_sha256 = sha256_file(samples)
    cohort = {
        "schema_version": sysid.TIMING_COHORT_SCHEMA,
        "identity": TIMING_IDENTITY,
        "episodes": [
            {
                "recording": "recording",
                "exact_replay_manifest": "manifest.json",
            }
        ],
    }
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(json.dumps(cohort), encoding="utf-8")

    def drift_after_verification(*args: object, **kwargs: object) -> dict[str, object]:
        samples.write_text("{}\n{}\n", encoding="utf-8")
        return {
            "exact_replay_binding": {
                "manifest_sha256": sha256_file(manifest),
                "replay_consumed_action_sha256": "0" * 64,
                "byte_identical": True,
            },
            "source": {
                "provenance": {
                    "samples": {"sha256": original_samples_sha256},
                }
            },
        }

    monkeypatch.setattr(
        sysid,
        "replay_exact_eligible_physical_recording",
        drift_after_verification,
    )
    with pytest.raises(ReplayContractError, match="changed after exact replay"):
        sysid.run_physical_timing_actuation_cohort(
            cohort_path,
            config_path=CONFIG_PATH,
            output_directory=tmp_path / "fit",
            backend="local",
        )
