from sim2claw.observable_registration_visible_divergence_video import (
    first_sustained_threshold_crossing,
    load_visible_divergence_video_contract,
)


def test_contract_is_trace_playback_only() -> None:
    contract = load_visible_divergence_video_contract()
    assert contract["timeline"]["source_row_count"] == 531
    assert contract["trace_playback"]["physics_rerun_allowed"] is False
    assert contract["trace_playback"]["action_change_allowed"] is False
    assert (
        contract["camera_and_display_registration"][
            "display_homography_is_metric_camera_calibration"
        ]
        is False
    )
    assert not any(contract["authority"].values())


def test_first_sustained_threshold_crossing_requires_full_run() -> None:
    values = [0.0, 0.3, 0.4, 0.0, 0.5, 0.6, 0.7, 0.8, None, 0.9]
    assert (
        first_sustained_threshold_crossing(
            values, threshold=0.2, start=0, minimum_rows=4
        )
        == 4
    )
    assert (
        first_sustained_threshold_crossing(
            values, threshold=0.2, start=8, minimum_rows=2
        )
        is None
    )
