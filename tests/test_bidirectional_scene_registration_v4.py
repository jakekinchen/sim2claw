import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim2claw.bidirectional_scene_registration_v4 import (
    CANDIDATE_PATH,
    BidirectionalSceneRegistrationError,
    build_registered_scene,
    load_candidate,
    physical_square_center,
    reproduce_fit,
)
from sim2claw.scene import BOARD_D4_TRANSFORMS, transform_board_square


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_all_d4_square_maps_are_bijective() -> None:
    squares = [f"{file}{rank}" for file in "abcdefgh" for rank in "12345678"]
    for transform in BOARD_D4_TRANSFORMS:
        mapped = [transform_board_square(square, transform) for square in squares]
        assert len(set(mapped)) == 64
    assert transform_board_square("c2", "reflect_ranks") == "c7"


def test_candidate_exactly_reproduces_fit_without_heldout() -> None:
    candidate = load_candidate(historical_fit_only=True)
    reproduced = reproduce_fit(historical_fit_only=True)
    for key, value in reproduced.items():
        expected = candidate[key]
        if isinstance(value, list):
            np.testing.assert_allclose(value, expected, rtol=0.0, atol=1e-12)
        elif isinstance(value, float):
            assert abs(value - expected) <= 1e-12
        else:
            assert value == expected
    assert candidate["authority"]["heldout_opened"] is False
    assert candidate["fit_residual_mm"] <= 25.0


def test_registered_scene_loads_in_cpu_fp64_and_moves_named_c2() -> None:
    candidate = load_candidate(historical_fit_only=True)
    model, data = build_registered_scene(
        candidate,
        historical_fit_only=True,
    )
    assert model.nq > 0
    assert data.qpos.dtype == np.float64
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "brown_pawn_c2"
    )
    assert body_id >= 0
    np.testing.assert_allclose(
        model.body_pos[body_id],
        physical_square_center(
            "c2",
            candidate,
            historical_fit_only=True,
        ),
        rtol=0.0,
        atol=1e-9,
    )


def test_candidate_preserves_canonical_action_hashes() -> None:
    candidate = json.loads(CANDIDATE_PATH.read_bytes())
    dataset = json.loads(
        (
            REPO_ROOT
            / "configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json"
        ).read_bytes()
    )
    action = next(
        entry for entry in dataset["inputs"] if entry["id"] == "fit_c2_counted_action"
    )
    assert candidate["canonical_action_npy_sha256"] == action["sha256"]
    assert (
        candidate["canonical_action_raw_float64le_sha256"]
        == "0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da"
    )


def test_v04_reflect_ranks_requires_explicit_historical_fit_opt_in() -> None:
    with pytest.raises(BidirectionalSceneRegistrationError, match="fit-only"):
        load_candidate()
    with pytest.raises(BidirectionalSceneRegistrationError, match="fit-only"):
        reproduce_fit()
    with pytest.raises(BidirectionalSceneRegistrationError, match="fit-only"):
        build_registered_scene()
