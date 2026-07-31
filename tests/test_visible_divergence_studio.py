from pathlib import Path

import pytest

from sim2claw.visible_divergence_studio import (
    VisibleDivergenceStudioError,
    load_visible_divergence_studio,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_visible_divergence_projection_is_hash_verified_and_read_only() -> None:
    projection = load_visible_divergence_studio(repo_root=REPO_ROOT)
    assert projection["available"] is True
    assert projection["read_only"] is True
    assert projection["physical_authority"] is False
    assert projection["global_mapping_approved"] is False
    assert projection["physics_success_claim"] is False
    assert projection["task_success_claim"] is False
    assert projection["transfer_claim"] is False
    assert projection["timeline"]["frame_count"] == 531
    assert projection["timeline"]["fps"] == 20
    assert projection["divergence_boundary"]["sample_interval"] == [248, 260]
    assert projection["registered_planar_endpoints"]["initial"]["pixel_error"] < 11
    assert projection["registered_planar_endpoints"]["terminal"]["pixel_error"] < 13
    assert all(row["url"].startswith("/media/") for row in projection["media"].values())


def test_visible_divergence_projection_fails_closed_without_receipts(
    tmp_path: Path,
) -> None:
    with pytest.raises((OSError, VisibleDivergenceStudioError)):
        load_visible_divergence_studio(repo_root=tmp_path)


def test_visible_divergence_surface_has_shared_controls_and_mobile_layout() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/visible-divergence.html").read_text()
    css = (REPO_ROOT / "src/sim2claw/studio_web/visible-divergence.css").read_text()
    script = (REPO_ROOT / "src/sim2claw/studio_web/visible-divergence.js").read_text()
    assert 'id="physical-video"' in html
    assert 'id="simulator-video"' in html
    assert 'id="scrubber"' in html
    assert 'id="jump-divergence"' in html
    assert "@media (max-width: 760px)" in css
    assert 'fetch("/api/visible-divergence"' in script
    assert "synchronize(true)" in script
