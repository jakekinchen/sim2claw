from __future__ import annotations

import copy
import hashlib

import numpy as np
import pytest

from sim2claw.episode_twin_bundle import (
    compile_episode_bundle,
    load_bundle_contract,
)
from sim2claw.learning_factory_artifacts import FactoryArtifactError


def _fixture() -> tuple[dict, list[dict], dict]:
    rows = []
    for index in range(3):
        values = [float(index + joint / 10.0) for joint in range(6)]
        rows.append(
            {
                "follower_requested_degrees": values,
                "follower_command_degrees": values,
                "follower_actual_position_degrees": values,
                "timestamp_monotonic_seconds": 0.05 * (index + 1),
            }
        )
    arrays = {
        "operator_requested": np.asarray(
            [row["follower_requested_degrees"] for row in rows], dtype="<f4"
        ),
        "gateway_sent": np.asarray(
            [row["follower_command_degrees"] for row in rows], dtype="<f4"
        ),
        "measured_joints": np.asarray(
            [row["follower_actual_position_degrees"] for row in rows],
            dtype="<f8",
        ),
        "source_timestamps": np.asarray(
            [row["timestamp_monotonic_seconds"] for row in rows], dtype="<f8"
        ),
    }
    channels = {}
    for name, array in arrays.items():
        channels[name] = {
            "little_endian_sha256": hashlib.sha256(
                array.tobytes(order="C")
            ).hexdigest()
        }
    episode = {
        "recording_id": "fixture",
        "sample_count": 3,
        "sample_hz": 20,
        "role": "fit",
        "proof_class": "fixture",
        "directory": "datasets/fixture",
        "coordinate_contract": {"status": "fixture"},
        "channels": channels,
        "assets": [
            {
                "path": "datasets/fixture/recording_receipt.json",
                "bytes": 2,
                "sha256": "0" * 64,
            },
            {
                "path": "datasets/fixture/samples.jsonl",
                "bytes": 2,
                "sha256": "1" * 64,
            },
        ],
    }
    contract = load_bundle_contract()
    return episode, rows, contract


def test_live_bundle_contract_is_closed_and_terminal_free() -> None:
    contract = load_bundle_contract()
    assert contract["corpus"]["expected_bundle_count"] == 8
    assert contract["initial_mission_observation"][
        "terminal_observation_as_replay_input_allowed"
    ] is False
    assert not any(contract["authority"].values())
    assert "actuator_application_or_ack_timestamp" in (
        contract["explicitly_missing_observables"]
    )


def test_bundle_compiler_is_deterministic_and_preserves_first_rows() -> None:
    episode, rows, contract = _fixture()
    first, arrays = compile_episode_bundle(
        corpus_episode=episode,
        rows=rows,
        contract=contract,
        initial_observation=None,
    )
    second, _ = compile_episode_bundle(
        corpus_episode=episode,
        rows=rows,
        contract=contract,
        initial_observation=None,
    )
    assert first == second
    assert first["initial_object_observation"] is None
    assert first["terminal_object_observation_as_replay_input"] is None
    assert first["tensors"]["gateway_sent"]["first_row"] == (
        arrays["gateway_sent"][0].tolist()
    )
    assert first["tensors"]["measured_joints"]["first_row"] == (
        arrays["measured_joints"][0].tolist()
    )


def test_bundle_rejects_tensor_drift_from_c0() -> None:
    episode, rows, contract = _fixture()
    changed = copy.deepcopy(rows)
    changed[1]["follower_command_degrees"][2] += 0.5
    with pytest.raises(FactoryArtifactError, match="C0 tensor digest changed"):
        compile_episode_bundle(
            corpus_episode=episode,
            rows=changed,
            contract=contract,
            initial_observation=None,
        )
