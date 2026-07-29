from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pytest

from sim2claw.observable_episode import (
    ObservableEpisodeError,
    SCHEMA_VERSION,
    build_physical_source_episode,
    build_simulator_episode,
    first_divergence,
    validate_episode,
    write_episode,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/observable_episode_v2_min_v1.json"
)


def _arrays() -> dict[str, object]:
    requested = np.array(
        [
            [0.0, 0.1, 0.2, 0.3, 0.4, -0.1],
            [0.01, 0.11, 0.21, 0.31, 0.41, -0.1],
            [0.02, 0.12, 0.22, 0.32, 0.42, -0.1],
        ],
        dtype="<f8",
    )
    applied = requested.copy()
    return {
        "requested": requested,
        "applied": applied,
        "joints": requested.copy(),
        "links": [
            {"left_gripper": [0.1 + 0.001 * index, 0.2, 0.3, 1, 0, 0, 0]}
            for index in range(3)
        ],
        "objects": np.array(
            [[0.35, 0.30, 0.0], [0.35, 0.30, 0.0], [0.39, 0.30, 0.0]]
        ),
        "covariances": np.repeat(
            np.diag([1e-6, 1e-6, 1e-5])[None, :, :],
            3,
            axis=0,
        ),
        "contacts": [False, True, True],
    }


def _simulator_episode(
    *,
    episode_id: str = "synthetic-direct",
    applied: np.ndarray | None = None,
    joints: np.ndarray | None = None,
) -> dict[str, object]:
    arrays = _arrays()
    return build_simulator_episode(
        episode_id=episode_id,
        requested=arrays["requested"],
        applied=arrays["applied"] if applied is None else applied,
        sample_hz=40.0,
        joint_states=arrays["joints"] if joints is None else joints,
        link_poses=arrays["links"],
        object_states_board_se2=arrays["objects"],
        object_covariances=arrays["covariances"],
        contact_states=arrays["contacts"],
        task_outcome="pass",
        first_object_motion_sample=2,
        provenance={
            "fixture": "deterministic_synthetic_simulator",
            "source_hash": "0" * 64,
        },
    )


def test_contract_declares_exact_channels_and_no_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["episode_schema_version"] == SCHEMA_VERSION
    assert "command_applied_or_missing" in (
        contract["sample_contract"]["required_channels"]
    )
    assert all(value is False for value in contract["authority"].values())
    assert contract["channel_ownership"]["wrist_depth_required"] is False


def test_simulator_fixture_serializes_exact_applied_trace(tmp_path) -> None:
    episode = _simulator_episode()
    assert validate_episode(episode) == episode
    requested = np.asarray(
        [sample["command_requested"] for sample in episode["samples"]],
        dtype="<f8",
    )
    applied = np.asarray(
        [
            sample["command_applied_or_missing"]
            for sample in episode["samples"]
        ],
        dtype="<f8",
    )
    assert episode["action"]["requested_sha256"] == hashlib.sha256(
        requested.tobytes(order="C")
    ).hexdigest()
    assert episode["action"]["applied_sha256_or_missing"] == hashlib.sha256(
        applied.tobytes(order="C")
    ).hexdigest()
    target = tmp_path / "episode.json"
    receipt = write_episode(episode, target)
    assert receipt["sample_count"] == 3
    assert json.loads(target.read_text(encoding="utf-8")) == episode
    with pytest.raises(
        ObservableEpisodeError,
        match="immutable observable episode already exists",
    ):
        write_episode(episode, target)


def test_physical_source_fixture_keeps_missing_channels_explicit() -> None:
    rows = [
        {
            "host": 12.0 + index * 0.025,
            "requested": [0.1 * index] * 6,
            "sent": [0.1 * index] * 6,
            "joints": [0.1 * index] * 6,
            "c922_device_timestamp": (
                100.0 + index / 30.0 if index < 2 else None
            ),
            "c922_clock_mapping_status": (
                "device_only" if index < 2 else "host_only"
            ),
        }
        for index in range(3)
    ]
    episode = build_physical_source_episode(
        episode_id="synthetic-physical-source",
        source_rows=rows,
        requested_field="requested",
        mapped_field=None,
        sent_field="sent",
        applied_field=None,
        joint_field="joints",
        host_time_field="host",
        sample_hz=40.0,
        camera_ids=["c922"],
        object_observations=[
            {
                "state_se2": [0.1, 0.2, 0.0],
                "covariance": np.diag([1e-5, 1e-5, 1e-4]).tolist(),
                "first_motion_event": False,
            },
            None,
            None,
        ],
        contact_observations=None,
        task_outcome=None,
        provenance={
            "fixture": "synthetic_physical_source_with_missingness"
        },
    )
    assert episode["action"]["mapped_sha256_or_missing"] is None
    assert episode["action"]["applied_sha256_or_missing"] is None
    assert episode["samples"][1]["object_observation_available"] is False
    assert episode["samples"][1]["object_state_board_se2"] is None
    assert (
        episode["samples"][2]["contact_state_or_probability"]["state"]
        == "unavailable"
    )
    assert (
        episode["samples"][2]["clock_mapping_status"]["c922"]
        == "host_only"
    )
    validate_episode(episode)


def test_first_divergence_prefers_applied_action_before_joint_response() -> None:
    reference = _simulator_episode()
    arrays = _arrays()
    delayed = np.asarray(arrays["applied"]).copy()
    delayed[1] = delayed[0]
    challenger = _simulator_episode(
        episode_id="synthetic-zoh",
        applied=delayed,
    )
    result = first_divergence(
        reference,
        challenger,
        joint_threshold=0.001,
        link_position_threshold_m=0.001,
        object_position_threshold_m=0.001,
        object_yaw_threshold_rad=0.01,
    )
    assert result["channel"] == "applied_action"
    assert result["sample_index"] == 1


def test_first_divergence_localizes_joint_when_actions_match() -> None:
    arrays = _arrays()
    changed_joints = np.asarray(arrays["joints"]).copy()
    changed_joints[2, 3] += 0.02
    result = first_divergence(
        _simulator_episode(),
        _simulator_episode(
            episode_id="synthetic-joint-challenger",
            joints=changed_joints,
        ),
        joint_threshold=0.001,
        link_position_threshold_m=0.001,
        object_position_threshold_m=0.001,
        object_yaw_threshold_rad=0.01,
    )
    assert result["channel"] == "joint_state"
    assert result["sample_index"] == 2
    assert result["residual"] == pytest.approx(0.02)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda episode: episode["samples"][1].update(
                {"host_monotonic_time": 0.0}
            ),
            "host monotonic timestamps",
        ),
        (
            lambda episode: episode["samples"][0][
                "contact_state_or_probability"
            ].update({"state": "unavailable", "probability": 0.5}),
            "unavailable contact",
        ),
        (
            lambda episode: episode["samples"][0].update(
                {
                    "object_state_covariance": [
                        [-1.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0],
                        [0.0, 0.0, 0.0],
                    ]
                }
            ),
            "positive semidefinite",
        ),
        (
            lambda episode: episode["action"].update(
                {"requested_sha256": "0" * 64}
            ),
            "requested action hash",
        ),
    ],
)
def test_validator_rejects_fabricated_or_inconsistent_evidence(
    mutator,
    message: str,
) -> None:
    episode = copy.deepcopy(_simulator_episode())
    mutator(episode)
    with pytest.raises(ObservableEpisodeError, match=message):
        validate_episode(episode)
