from __future__ import annotations

from pathlib import Path

import numpy as np

from tools.fit_pi_four_tag_bundle import (
    FIXED_BODY_MAP,
    HELDOUT,
    TAG3_BODY_CANDIDATES,
    TRAINING,
    body_map,
    error_metrics,
)


def test_only_tag3_body_varies_and_pose_d_is_not_training() -> None:
    assert TAG3_BODY_CANDIDATES == (
        "left_base",
        "left_shoulder",
        "left_upper_arm",
    )
    for candidate in TAG3_BODY_CANDIDATES:
        mapping = body_map(candidate)
        assert {tag_id: mapping[tag_id] for tag_id in (0, 1, 2)} == (
            FIXED_BODY_MAP
        )
        assert mapping[3] == candidate
    assert HELDOUT not in TRAINING.values()
    assert {Path(path).name for path in TRAINING.values()} == {"stage-1"}
    assert set(TRAINING) == {
        "old_pose_f",
        "old_pose_h",
        "old_pose_i",
        "new_pose_h",
        "new_pose_i",
    }


def test_error_metrics_reports_exact_per_tag_and_overall_values() -> None:
    class FixtureBundle:
        def project(self, parameters, row, mapping):
            del parameters, mapping
            return np.asarray(row["projection"], dtype=np.float64)

    rows = [
        {
            "tag_id": 0,
            "corners": np.zeros((4, 2), dtype=np.float64),
            "projection": np.asarray([[3.0, 4.0]] * 4),
        },
        {
            "tag_id": 3,
            "corners": np.zeros((4, 2), dtype=np.float64),
            "projection": np.asarray([[0.0, 2.0]] * 4),
        },
    ]

    metrics = error_metrics(
        FixtureBundle(),  # type: ignore[arg-type]
        np.zeros(1),
        rows,
        body_map("left_base"),
    )

    assert metrics["by_tag"]["0"] == {
        "corner_count": 4,
        "corner_rmse_px": 5.0,
        "corner_max_px": 5.0,
    }
    assert metrics["by_tag"]["3"] == {
        "corner_count": 4,
        "corner_rmse_px": 2.0,
        "corner_max_px": 2.0,
    }
    assert metrics["corner_count"] == 8
    assert metrics["corner_rmse_px"] == np.sqrt(14.5)
    assert metrics["corner_max_px"] == 5.0
