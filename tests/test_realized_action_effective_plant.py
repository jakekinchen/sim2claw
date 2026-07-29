from __future__ import annotations

import numpy as np

from sim2claw.realized_action_effective_plant import (
    _branches,
    _first_order,
    _sample_hold,
    _timestamp_zoh,
    load_contract,
)


def test_contract_preserves_sources_and_authority() -> None:
    contract = load_contract()
    assert contract["plant_paths"][2]["sample_hold"] == 3
    assert all(contract["rules"].values())
    assert not any(contract["authority"].values())


def test_sample_hold_and_timestamp_zoh_are_explicit() -> None:
    values = np.arange(30, dtype=np.float64).reshape(5, 6)
    held, indices = _sample_hold(values, 2)
    assert indices.tolist() == [0, 0, 0, 1, 2]
    np.testing.assert_array_equal(held, values[indices])
    timestamps = np.arange(5, dtype=np.float64) * 0.05
    delayed, delayed_indices = _timestamp_zoh(values, timestamps, 0.11)
    assert delayed_indices.tolist() == [0, 0, 0, 0, 1]
    np.testing.assert_array_equal(delayed, values[delayed_indices])


def test_first_order_is_seeded_only_from_initial_state() -> None:
    target = np.full((4, 2), 4.0)
    output = _first_order(target, np.asarray([0.0, 2.0]), np.asarray([0.5, 1.0]))
    np.testing.assert_allclose(output[0], [0.0, 2.0])
    np.testing.assert_allclose(output[1], [2.0, 4.0])
    np.testing.assert_allclose(output[-1], [3.5, 4.0])


def test_direction_branches_are_bounded_symbols() -> None:
    target = np.asarray([[0.0], [1.0], [1.0], [-1.0]])
    assert _branches(target, 0.05).ravel().tolist() == [0, 1, 0, -1]
