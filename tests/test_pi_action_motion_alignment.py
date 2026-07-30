import numpy as np

from sim2claw.pi_action_motion_alignment import (
    _best_lag,
    load_pi_action_motion_alignment_contract,
)


def test_contract_is_same_run_and_fail_closed() -> None:
    contract = load_pi_action_motion_alignment_contract()
    method = contract["method"]
    assert method["fit_model"] == "one_constant_offset_per_run"
    assert not method["drift_fit_allowed"]
    assert not method["scale_fit_allowed"]
    assert not method["task_contact_or_outcome_fit_allowed"]
    assert not method["cross_episode_merge_allowed"]
    assert not contract["reporting"]["transfer_claim_allowed"]


def test_motion_derivative_lag_search_recovers_constant_offset() -> None:
    reference_t = np.arange(0.0, 8.0, 0.01)
    reference = (
        np.exp(-((reference_t - 1.2) / 0.08) ** 2)
        - 0.7 * np.exp(-((reference_t - 3.7) / 0.12) ** 2)
        + 0.9 * np.exp(-((reference_t - 6.1) / 0.07) ** 2)
    )
    pi_t = np.arange(0.0, 7.0, 1.0 / 30.0)
    expected_lag = 0.82
    pi_signal = np.interp(pi_t + expected_lag, reference_t, reference)
    result = _best_lag(
        pi_t=pi_t,
        pi_signal=pi_signal,
        reference_t=reference_t,
        reference_signal=reference,
        lag_values=np.arange(0.0, 1.5 + 0.005, 0.005),
        fit_minimum=reference_t[0],
        fit_maximum=reference_t[-1],
    )
    assert abs(result["lag_seconds"] - expected_lag) <= 0.005
