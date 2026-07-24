from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.hil_trace_decomposition import (
    HILTraceDecompositionError,
    _best_profile_row,
    _lag_profile,
    _segments,
    derive_hil_trace_decomposition,
    load_hil_trace_decomposition_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_AVAILABLE = (
    REPO_ROOT
    / "runs/current-100mm-hil-identifiability-20260724/campaign_state.json"
).is_file()


def test_contract_discloses_post_v1_design_and_keeps_authority_closed() -> None:
    contract = load_hil_trace_decomposition_contract()
    assert contract["evidence_context"][
        "v1_results_were_visible_before_this_v2_contract"
    ] is True
    assert contract["evidence_context"][
        "external_advisory_is_evaluator_evidence"
    ] is False
    assert all(value is False for value in contract["authority"].values())


def test_lag_profile_reports_every_native_candidate_without_self_scoring() -> None:
    requested = np.asarray([0, 1, 2, 3, 4, 5], dtype=np.float64)
    actual = np.asarray([0, 0, 1, 2, 3, 4], dtype=np.float64)
    profile = _lag_profile(
        requested,
        actual,
        lag_candidates=[0, 1, 2],
        edge_trim=0,
    )
    assert [row["lag_samples"] for row in profile] == [0, 1, 2]
    assert _best_profile_row(profile) == {
        "lag_samples": 1,
        "sample_count": 5,
        "rmse_degrees": 0.0,
    }


def test_segments_do_not_merge_separate_motion_windows() -> None:
    mask = np.asarray([False, True, True, False, True, False])
    assert _segments(mask) == [(1, 3), (4, 5)]


def test_output_overwrite_is_refused_before_source_analysis(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep").write_text("keep", encoding="utf-8")
    with pytest.raises(HILTraceDecompositionError, match="overwrite is refused"):
        derive_hil_trace_decomposition(output)


@pytest.mark.skipif(
    not CAMPAIGN_AVAILABLE,
    reason="local HIL campaign evidence unavailable",
)
def test_current_decomposition_is_deterministic_and_promotes_nothing(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    derive_hil_trace_decomposition(first)
    derive_hil_trace_decomposition(second)
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "receipt.json").read_bytes() == (
        second / "receipt.json"
    ).read_bytes()
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    assert report["cross_packet_findings"]["simulator_change_warranted"] is False
    assert report["cross_packet_findings"]["task_score_change_warranted"] is False
    assert report["budget"] == {
        "additional_physical_attempts": 0,
        "additional_simulator_replays": 0,
        "evaluator_provider_calls": 0,
        "owner_requested_external_advisory_calls_observed": 1,
    }
    assert all(value is False for value in report["authority"].values())
