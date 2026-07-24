from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from sim2claw.sail.studio import (
    DEFAULT_CONFIG,
    StudioObservatoryError,
    _phase_labels,
    _trace_channels,
    compile_studio_observatory,
    load_studio_observatory,
)
from sim2claw.studio_server import create_server


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / DEFAULT_CONFIG
REQUIRED_LOCAL_SOURCE = REPO_ROOT / "outputs/sail/retired-bg-v1/evidence/catalog.json"


def test_phase_labels_cover_every_sample_and_reject_gaps() -> None:
    intervals = [
        {
            "phase": "approach_open",
            "start_sample_index_inclusive": 0,
            "end_sample_index_exclusive": 2,
        },
        {
            "phase": "closure_transition",
            "start_sample_index_inclusive": 2,
            "end_sample_index_exclusive": 4,
        },
    ]
    assert _phase_labels(4, intervals) == [
        "approach_open",
        "approach_open",
        "closure_transition",
        "closure_transition",
    ]
    with pytest.raises(StudioObservatoryError, match="coverage"):
        _phase_labels(5, intervals)


def test_trace_channels_keep_simulation_contact_and_consequence_separate() -> None:
    body_names = ["world", "brown_pawn_c2", "left_gripper"]
    trace = {
        "body_names": body_names,
        "fps": 10.0,
        "frames": [
            {
                "t": 0.0,
                "phase": "approach",
                "p": [0.0, 0.0, 0.0, 0.1, 0.2, 0.8, 0.0, 0.0, 0.0],
                "c": [],
            },
            {
                "t": 1.0,
                "phase": "grasp",
                "p": [0.0, 0.0, 0.0, 0.1, 0.2, 0.83, 0.0, 0.0, 0.0],
                "c": [[1, 2, 0.1, 0.2, 0.83]],
            },
        ],
    }
    channels = _trace_channels(
        trace,
        times=[0.0, 1.0],
        source_square="c1",
        destination_square="c2",
    )
    assert channels["simulated_pawn_contact_count"] == [0, 1]
    assert channels["simulated_pawn_rise_m"] == pytest.approx([0.0, 0.03])
    assert len(channels["simulated_target_xyz_m"]) == 3


def test_full_observatory_retains_all_partial_episodes_and_binds_figures(
    tmp_path: Path,
) -> None:
    if not REQUIRED_LOCAL_SOURCE.is_file():
        pytest.skip("owner-local Phase 1 SAIL artifacts are unavailable")
    result = compile_studio_observatory(
        CONFIG_PATH,
        tmp_path,
        repo_root=REPO_ROOT,
    )
    manifest = load_studio_observatory(output_root=tmp_path, repo_root=REPO_ROOT)
    assert result["counts"]["displayed_episode_count"] == 11
    assert manifest["ranking"]["selected_episode_count"] == 7
    assert manifest["ranking"]["lower_signal_retained_count"] == 4
    assert manifest["ranking"]["omitted_episode_count"] == 0
    assert sum(row["ranking_status"] == "ranked_strongest_partial" for row in manifest["episodes"]) == 7
    assert sum(row["ranking_status"] == "retained_lower_signal_partial" for row in manifest["episodes"]) == 4
    assert manifest["twin_worthiness"]["level"] == "TW-REPLAY"
    assert manifest["twin_worthiness"]["training_admitted"] is False
    assert manifest["authority"]["read_only"] is True
    assert manifest["authority"]["physical_authority"] is False
    assert set(manifest["figures"]) == {
        "belief_after",
        "belief_before",
        "intervention_signatures",
        "residual_heatmap",
    }
    for figure in manifest["figures"].values():
        payload = (tmp_path / figure["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == figure["sha256"]
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert "configs/studio/project_map_v1.json" in receipt["compiler_sha256"]
    assert "src/sim2claw/studio_project_map.py" in receipt["compiler_sha256"]
    assert "src/sim2claw/studio_twin_fidelity.py" in receipt["compiler_sha256"]
    first = manifest["episodes"][0]
    assert len(first["channels"]["action"]) == first["sample_count"]
    assert len(first["channels"]["mapped_measured_joint"]) == first["sample_count"]
    assert len(first["channels"]["selected_simulated_joint"]) == first["sample_count"]
    assert len(first["channels"]["simulated_pawn_xyz_m"]) == first["sample_count"]
    availability = {row["id"]: row["status"] for row in first["availability"]}
    assert availability["contact"] == "simulation_only"
    assert availability["consequence"] == "simulation_only"


def test_observatory_receipt_rejects_figure_tampering(tmp_path: Path) -> None:
    if not REQUIRED_LOCAL_SOURCE.is_file():
        pytest.skip("owner-local Phase 1 SAIL artifacts are unavailable")
    compile_studio_observatory(CONFIG_PATH, tmp_path, repo_root=REPO_ROOT)
    figure = tmp_path / "figures/intervention-signatures.svg"
    figure.write_text("<svg>tampered</svg>\n", encoding="utf-8")
    with pytest.raises(StudioObservatoryError, match="output changed"):
        load_studio_observatory(output_root=tmp_path, repo_root=REPO_ROOT)


def test_studio_serves_read_only_observatory_and_verified_svg(tmp_path: Path) -> None:
    payload = {
        "available": True,
        "schema_version": "sim2claw.sail_studio_observatory.v1",
        "authority": {"read_only": True, "physical_authority": False},
    }
    figure = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>\n'
    digest = hashlib.sha256(figure).hexdigest()
    with (
        patch("sim2claw.studio_server.load_studio_observatory", return_value=payload),
        patch(
            "sim2claw.studio_server.open_studio_figure",
            return_value=(tmp_path / "figure.svg", figure, digest),
        ),
    ):
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/api/sail-observatory") as response:
                observed = json.load(response)
            assert observed == payload
            with urlopen(f"{base}/api/sail-observatory/figures/figure.svg") as response:
                assert response.headers["ETag"] == f'"{digest}"'
                assert response.read() == figure
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_frontend_keeps_sail_inside_existing_mobile_read_only_studio() -> None:
    html_text = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text()
    css_text = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text()
    js_text = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text()
    assert 'data-route="sail"' in html_text
    assert 'data-view-panel="sail"' in html_text
    assert 'id="sail-scrubber"' in html_text
    assert 'id="sail-availability-grid"' in html_text
    assert 'id="sail-gate-matrix"' in html_text
    assert 'id="sail-figure-list"' in html_text
    assert "@media (max-width: 620px)" in css_text
    assert 'fetch("/api/sail-observatory"' in js_text
    assert '["replay", "sail", "library"' in js_text
