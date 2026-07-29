from __future__ import annotations

import numpy as np

from sim2claw.realized_action_sage_lite import (
    _aligned_blocks,
    load_contract,
    sample_alignment,
)


def test_contract_is_fail_closed_and_source_bound() -> None:
    contract = load_contract()
    assert contract["cohorts"]["sealed_use"].startswith("report_only")
    assert all(contract["forbidden_claims"].values())
    assert not any(contract["authority"].values())


def test_alignment_positive_shift_means_measured_lags_sent() -> None:
    sent = np.arange(12, dtype=np.float64).reshape(6, 2)
    measured = np.vstack((sent[0], sent[:-1]))
    result = sample_alignment(sent, measured, [-1, 0, 1])
    assert result["best_overall"]["shift_samples"] == 1
    assert result["causal_latency_claim"] is False


def test_aligned_blocks_preserve_joint_width() -> None:
    left = np.arange(30, dtype=np.float64).reshape(5, 6)
    right = left.copy()
    for shift in (-2, 0, 2):
        sent, measured = _aligned_blocks(left, right, shift)
        assert sent.shape == measured.shape
        assert sent.shape[1] == 6
