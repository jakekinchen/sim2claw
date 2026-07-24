from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.hil_trace_analysis import (
    HILTraceAnalysisError,
    _best_lag,
    _contiguous_segments,
    derive_hil_trace_report,
    load_hil_trace_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_AVAILABLE = (
    REPO_ROOT / "runs/current-100mm-hil-identifiability-20260724/campaign_state.json"
).is_file()


def test_best_lag_is_sample_quantized_and_deterministic() -> None:
    requested = np.asarray([0, 1, 2, 3, 4, 5], dtype=np.float64)
    actual = np.asarray([0, 0, 1, 2, 3, 4], dtype=np.float64)
    result = _best_lag(requested, actual, [0, 1, 2], 20)
    assert result == {
        "samples": 1,
        "seconds": 0.05,
        "rmse_degrees": 0.0,
        "is_not_command_application_latency": True,
    }


def test_contiguous_segments_preserve_separate_traversals() -> None:
    mask = np.asarray([False, True, True, False, True, False])
    assert _contiguous_segments(mask) == [(1, 3), (4, 5)]


def test_contract_keeps_analysis_authority_closed() -> None:
    contract = load_hil_trace_contract()
    assert all(value is False for value in contract["authority"].values())
    assert contract["claim_gates"]["current_is_calibrated_force"] is False
    assert (
        contract["claim_gates"]["sample_lag_is_command_application_latency"]
        is False
    )


@pytest.mark.skipif(
    not CAMPAIGN_AVAILABLE,
    reason="local HIL campaign evidence unavailable",
)
def test_current_report_is_deterministic_and_promotes_nothing(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    derive_hil_trace_report(first)
    derive_hil_trace_report(second)
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "receipt.json").read_bytes() == (
        second / "receipt.json"
    ).read_bytes()
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["cross_packet_findings"][
        "elbow_current_and_stall_signature_is_distinct"
    ] is True
    assert report["cross_packet_findings"][
        "any_scale_offset_fit_admissible"
    ] is False
    assert report["cross_packet_findings"]["simulator_change_warranted"] is False
    assert report["budget"] == {
        "additional_physical_attempts": 0,
        "additional_simulator_replays": 0,
        "provider_calls": 0,
    }


def test_output_overwrite_is_refused(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep").write_text("keep", encoding="utf-8")
    with pytest.raises(HILTraceAnalysisError, match="overwrite is refused"):
        derive_hil_trace_report(output)
