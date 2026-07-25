from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import sim2claw.system_identification as sysid
import sim2claw.timing_admission as admission
from sim2claw.paths import REPO_ROOT
from sim2claw.recorded_replay import (
    RecordedEpisode,
    canonical_json_sha256,
    float64_tensor_sha256,
    load_sysid_config,
    simulate_and_align,
)


CONFIG_PATH = REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json"
IDENTITY = {
    "robot": {
        "robot_id": "synthetic-fixture-so101",
        "follower_port": "/dev/synthetic-fixture",
        "follower_calibration_sha256": "1" * 64,
        "gateway_schema": "sim2claw.so101_physical_gateway.v2",
    },
    "workspace_pose_id": "synthetic-fixture-workspace",
}


def _episodes(tmp_path: Path) -> tuple[list[RecordedEpisode], dict[str, object]]:
    config = copy.deepcopy(load_sysid_config(CONFIG_PATH))
    selected = {
        "command_latency_seconds": 0.05,
        "actuator_gain_scale": 1.2,
        "joint_damping_scale": 1.1,
    }
    episodes = []
    for index in range(3):
        timestamps = np.linspace(0.0, 1.05, 22, dtype=np.float64)
        commands = np.zeros((timestamps.size, 6), dtype=np.float64)
        for joint in range(3):
            commands[:, joint] = 0.2 * np.sin(
                (2.0 + 0.15 * index + 0.1 * joint) * np.pi * timestamps
                + 0.2 * index
            )
        source = tmp_path / f"episode-{index}.jsonl"
        source.write_text("{}\n", encoding="utf-8")
        episode = RecordedEpisode(
            episode_id=f"synthetic-admission-{index}",
            proof_class="synthetic_timing_admission_fixture",
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
            source_sha256="2" * 64,
            source_schema_version="synthetic.v1",
            source_provenance={"chain_complete": True},
            joint_transform=None,
        )
        replay = simulate_and_align(
            episode,
            config,
            parameter_values=selected,
            model_base_directory=CONFIG_PATH.parent,
        )
        episodes.append(
            replace(
                episode,
                measured=tuple(
                    {"joint_position": row.tolist()}
                    for row in replay["simulated"]["joint_position"]
                ),
            )
        )
    return episodes, config


def test_separate_cpu_fp32_admission_never_calls_fit_or_optimizer(
    tmp_path: Path, monkeypatch
) -> None:
    episodes, config = _episodes(tmp_path)
    split = sysid._freeze_timing_cohort_split(episodes, config)
    timing = [
        stage
        for stage in config["parameter_stages"]
        if stage["name"] == "timing_control"
    ][0]
    family = {
        "stage": "timing_control",
        "parameters": copy.deepcopy(timing["parameters"]),
        "excluded": ["geometry", "contact_object", "deadband", "friction", "load"],
    }
    family["digest"] = canonical_json_sha256(family)
    selected = {
        "command_latency_seconds": 0.05,
        "actuator_gain_scale": 1.2,
        "joint_damping_scale": 1.1,
    }
    fit = {
        "schema_version": sysid.TIMING_RESULT_SCHEMA,
        "status": "diagnostic_fit_complete",
        "identity": IDENTITY,
        "candidate_family": family,
        "candidate_selection": {
            "selected_on": ["train", "validation"],
            "held_out_used_for_selection": False,
            "selected_parameters": selected,
        },
        "frozen_split": split,
        "action_identity": {
            "sha256_by_episode": {
                episode.episode_id: float64_tensor_sha256(episode.commands)
                for episode in episodes
            },
            "unchanged_for_every_candidate": True,
        },
        "evaluator_owned": False,
        "self_scored": True,
        "evaluator_admission": False,
        "parameters_promoted": False,
    }
    fit_path = tmp_path / "fit.json"
    fit_path.write_text(json.dumps(fit, sort_keys=True), encoding="utf-8")
    cohort = {
        "schema_version": sysid.TIMING_COHORT_SCHEMA,
        "identity": IDENTITY,
        "episodes": [
            {
                "recording": f"recording-{index}",
                "exact_replay_manifest": f"manifest-{index}.json",
            }
            for index in range(len(episodes))
        ],
    }
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(json.dumps(cohort, sort_keys=True), encoding="utf-8")

    queue = iter(episodes)

    def load_fixture(*args, **kwargs):
        episode = next(queue)
        return episode, {
            "episode_id": episode.episode_id,
            "recording_receipt_sha256": "3" * 64,
            "samples_sha256": "4" * 64,
            "exact_replay_manifest_sha256": "5" * 64,
            "gateway_sent_action_sha256": float64_tensor_sha256(episode.commands),
            "p5_byte_identical": True,
        }

    monkeypatch.setattr(admission, "_load_verified_physical_episode", load_fixture)

    def fitting_is_forbidden(*args, **kwargs):
        raise AssertionError("admission called a fitting or optimizer path")

    monkeypatch.setattr(sysid, "fit_parameter_stage", fitting_is_forbidden)
    monkeypatch.setattr(sysid, "_local_least_squares", fitting_is_forbidden)
    monkeypatch.setattr(sysid, "_official_least_squares", fitting_is_forbidden)

    receipt = admission.admit_physical_timing_actuation_fit(
        fit_path,
        cohort_path,
        config_path=CONFIG_PATH,
        output_path=tmp_path / "admission.json",
        synthetic_fixture_mode=True,
    )
    assert receipt["held_out_replay"]["evaluator_numeric_runtime"] == "cpu_numpy_fp32"
    assert receipt["held_out_replay"]["simulation_runtime"] == "cpu_mujoco_fp64"
    assert receipt["held_out_replay"]["fit_or_selection_performed"] is False
    assert receipt["held_out_replay"]["improvement_gate"]["passed"] is True
    assert receipt["evaluator_owned"] is True
    assert receipt["self_scored"] is False
    assert receipt["synthetic"] is True
    assert receipt["evaluator_admission"] is False
    assert receipt["physical_authority"] is False
    with pytest.raises(
        sysid.SystemIdentificationError,
        match="refusing to overwrite existing timing admission receipt",
    ):
        admission.admit_physical_timing_actuation_fit(
            fit_path,
            cohort_path,
            config_path=CONFIG_PATH,
            output_path=tmp_path / "admission.json",
            synthetic_fixture_mode=True,
        )
