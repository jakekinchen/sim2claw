from __future__ import annotations

import numpy as np

from sim2claw.realized_action_first_divergence import (
    ORDER,
    _event,
    _first_index,
    load_contract,
)


def test_contract_freezes_order_and_authority() -> None:
    contract = load_contract()
    assert tuple(contract["ordered_channels"]) == ORDER
    assert all(contract["rules"].values())
    assert not any(contract["authority"].values())


def test_first_index_is_deterministic_and_nullable() -> None:
    assert _first_index(np.asarray([False, True, True])) == 1
    assert _first_index(np.asarray([False, False])) is None


def test_event_preserves_unobservable_channel() -> None:
    row = _event(channel="first_contact", status="unobservable")
    assert row == {
        "channel": "first_contact",
        "status": "unobservable",
        "sample_index": None,
        "timestamp_seconds": None,
        "evidence": {},
    }
