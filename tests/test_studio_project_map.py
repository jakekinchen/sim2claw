from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.sail.studio import StudioObservatoryError
from sim2claw.studio_project_map import (
    API_SCHEMA,
    DEFAULT_CONFIG,
    StudioProjectMapError,
    build_project_map,
)
from sim2claw.studio_server import create_server


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture_root(tmp_path: Path, *, stale_factory_binding: bool = False) -> Path:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    _write_json(tmp_path / "configs/studio/project_map_v1.json", config)
    state_path = tmp_path / "docs/autonomous-workflow/project_state.json"
    _write_json(state_path, {"schema_version": "sim2claw.project_state.v1"})
    observed = hashlib.sha256(state_path.read_bytes()).hexdigest()
    _write_json(
        tmp_path / "configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json",
        {
            "project_id": "fixture",
            "source_of_truth": {
                "project_state": "docs/autonomous-workflow/project_state.json",
                "project_state_sha256": "0" * 64 if stale_factory_binding else observed,
            },
        },
    )
    return tmp_path


def _catalog() -> dict[str, object]:
    return {
        "summary": {"episodes": 3, "passed_episodes": 1},
        "project": {"training_lock": "closed_pending_admitted_evidence"},
        "calibrations": [{"id": "visual"}],
        "robots": [{"id": "follower"}, {"id": "leader"}],
        "episodes": [
            {
                "id": "physical-dual",
                "proof_class": "physical_teleoperation_source_unqualified",
                "recording_feeds": [{"id": "overhead"}, {"id": "wrist"}],
                "comparison": {"physics_replay": {"available": True}},
            },
            {
                "id": "physical-single",
                "proof_class": "physical_teleoperation_source_unqualified",
                "recording_feeds": [{"id": "overhead"}],
                "comparison": {"physics_replay": {"available": False}},
            },
            {
                "id": "retained",
                "proof_class": "retained_action_frozen_simulation_replay",
            },
        ],
    }


def _sail() -> dict[str, object]:
    return {
        "available": True,
        "episodes": [{"id": "receipt-bound"}],
        "missingness": {"global": ["physical reference"]},
    }


def _build(tmp_path: Path, **kwargs: object) -> dict[str, object]:
    root = _fixture_root(
        tmp_path,
        stale_factory_binding=bool(kwargs.pop("stale_factory_binding", False)),
    )
    with (
        patch("sim2claw.studio_project_map.build_catalog", return_value=_catalog()),
        patch(
            "sim2claw.studio_project_map.load_studio_observatory",
            return_value=_sail(),
        ),
    ):
        return build_project_map(
            repo_root=root,
            read_only=True,
            recorder_control_enabled=False,
            orchestrator_available=True,
        )


def test_project_map_is_deterministic_and_shares_one_evidence_contract(
    tmp_path: Path,
) -> None:
    first = _build(tmp_path)
    second = _build(tmp_path)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["schema_version"] == API_SCHEMA
    assert first["available"] is True
    assert first["read_only"] is True
    assert first["physical_authority"] is False
    assert first["interface"]["agent_entrypoint"] == "GET /api/project-map"
    assert "same receipts" in first["interface"]["shared_truth"].lower()
    assert [row["id"] for row in first["stages"]] == [
        "capture",
        "scene",
        "simulate",
        "replay",
        "evaluate",
        "diagnose",
        "improve",
        "learn_transfer",
    ]
    assert not any(
        first["authority"][key]
        for key in (
            "agent_is_evaluator",
            "agent_can_promote",
            "training_authority",
            "physical_authority",
            "robot_motion",
        )
    )


def test_project_map_preserves_proof_lanes_and_missing_physics(
    tmp_path: Path,
) -> None:
    payload = _build(tmp_path)
    stages = {row["id"]: row for row in payload["stages"]}
    assert stages["capture"]["measure"] == "2 physical sources · 1 dual-camera"
    assert stages["capture"]["proof"] == "recorded source evidence · not training-admitted"
    assert "1/2 physical sources physics-paired" in stages["replay"]["measure"]
    assert stages["replay"]["missing"] == ["1 physical physics pairings"]
    assert "visual-only" in stages["replay"]["proof"]
    assert "action-frozen" in stages["replay"]["proof"]
    assert stages["learn_transfer"]["status"] == "closed"
    assert stages["learn_transfer"]["agent"]["commands"] == []


def test_project_map_fails_closed_on_sail_or_factory_binding(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path, stale_factory_binding=True)
    with (
        patch("sim2claw.studio_project_map.build_catalog", return_value=_catalog()),
        patch(
            "sim2claw.studio_project_map.load_studio_observatory",
            side_effect=StudioObservatoryError("receipt mismatch"),
        ),
    ):
        payload = build_project_map(
            repo_root=root,
            read_only=True,
            recorder_control_enabled=False,
            orchestrator_available=False,
        )
    stages = {row["id"]: row for row in payload["stages"]}
    assert stages["diagnose"]["status"] == "unavailable"
    assert stages["diagnose"]["measure"] == "SAIL observatory unavailable"
    assert stages["improve"]["status"] == "unavailable"
    assert "stale" in stages["improve"]["missing"][0].lower()


def test_project_map_rejects_route_substitution(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    config_path = root / "configs/studio/project_map_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["stages"][0]["human_views"][0]["route"] = "hidden-promoter"
    _write_json(config_path, config)
    with pytest.raises(StudioProjectMapError, match="unknown Studio route"):
        build_project_map(
            repo_root=root,
            read_only=True,
            recorder_control_enabled=False,
            orchestrator_available=False,
        )


def test_project_map_rejects_malformed_view_without_partial_projection(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    config_path = root / "configs/studio/project_map_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["stages"][0]["human_views"] = [None]
    _write_json(config_path, config)
    with pytest.raises(StudioProjectMapError, match="invalid researcher view"):
        build_project_map(
            repo_root=root,
            read_only=True,
            recorder_control_enabled=False,
            orchestrator_available=False,
        )


def test_server_exposes_project_map_as_read_only_json(tmp_path: Path) -> None:
    expected = {
        "schema_version": API_SCHEMA,
        "title": "Fixture map",
        "authority": {"physical_authority": False},
        "stages": [],
    }
    with patch(
        "sim2claw.studio_server.build_project_map",
        return_value=expected,
    ) as builder:
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/api/project-map") as response:
                observed = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    assert observed == expected
    assert builder.call_args.kwargs["read_only"] is True
    assert builder.call_args.kwargs["recorder_control_enabled"] is False


def test_project_map_is_contextual_read_only_and_responsive() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text()
    css = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text()
    js = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text()
    nav = html.split('<nav class="view-switch"', 1)[1].split("</nav>", 1)[0]
    drawer = html.split('id="project-map-drawer"', 1)[1].split("</aside>", 1)[0]

    assert "Project map" not in nav
    assert "Learning Factory" not in nav
    assert 'aria-controls="project-map-drawer"' in html
    assert 'id="project-map-content"' in html
    assert "<form" not in drawer
    assert "<input" not in drawer
    assert 'fetch("/api/project-map"' in js
    assert "projectMapNode(\"code\", \"is-command\"" in js
    assert ".project-map-rails" in css
    assert "@media (max-width: 480px)" in css
    assert 'event.key === "Escape" && state.drawer' in js
    assert "trigger?.focus({ preventScroll: true })" in js
