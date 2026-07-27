from __future__ import annotations

import numpy as np

from tools.evaluate_current_multiview_cad_bundle import (
    SegmentRow,
    _select_grid_clusters,
    d4_corner_orders,
    sample_distance,
    world_grid,
)


def test_d4_corner_orders_cover_eight_unique_board_symmetries() -> None:
    orders = d4_corner_orders()
    assert len(orders) == 8
    assert len(set(orders)) == 8
    assert all(set(order) == {"a1", "h1", "h8", "a8"} for order in orders)


def test_world_grid_preserves_declared_corner_order() -> None:
    corners = {
        "a1": [0.0, 0.0, 0.8],
        "h1": [1.0, 0.0, 0.8],
        "h8": [1.0, 1.0, 0.8],
        "a8": [0.0, 1.0, 0.8],
    }
    grid = world_grid(corners, ("h8", "a8", "a1", "h1"))
    np.testing.assert_allclose(grid[0, 0], corners["h8"])
    np.testing.assert_allclose(grid[0, -1], corners["a8"])
    np.testing.assert_allclose(grid[-1, -1], corners["a1"])
    np.testing.assert_allclose(grid[-1, 0], corners["h1"])
    np.testing.assert_allclose(grid[4, 4], [0.5, 0.5, 0.8])


def test_grid_cluster_selection_rejects_low_support_distractors() -> None:
    rows = []
    for index, intercept in enumerate(
        [240.0, 280.0, 320.0, 365.0, 412.0, 466.0, 527.0, 596.0, 675.0]
    ):
        for pose in ("H", "I"):
            rows.append(
                SegmentRow(
                    "row",
                    intercept + (0.4 if pose == "H" else -0.4),
                    120.0,
                    pose,
                    np.asarray([0.0, intercept, 100.0, intercept]),
                )
            )
    rows.append(
        SegmentRow(
            "row",
            255.0,
            20.0,
            "H",
            np.asarray([0.0, 255.0, 20.0, 255.0]),
        )
    )
    selected = _select_grid_clusters(rows, "row")
    centers = [
        np.average(
            [row.intercept for row in cluster],
            weights=[row.length for row in cluster],
        )
        for cluster in selected
    ]
    assert len(selected) == 9
    assert min(abs(center - 255.0) for center in centers) > 10.0


def test_distance_sampling_clips_out_of_frame_and_large_values() -> None:
    distance = np.asarray([[0.0, 2.0], [4.0, 8.0]])
    values = sample_distance(
        distance,
        np.asarray([[0.0, 0.0], [1.0, 1.0], [5.0, 5.0]]),
        6.0,
    )
    np.testing.assert_allclose(values, [0.0, 6.0, 6.0])
