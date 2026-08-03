from __future__ import annotations

import json

from sim2claw.observable_registration_frozen_workcell_se2_full_development_timeline import (
    DEFAULT_CONTRACT,
)
from sim2claw.observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
)


def test_or85_reuses_or80_timeline_metric_and_acceptance() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    predecessor = json.loads(
        (REPO_ROOT / contract["sources"]["or80_contract"]["path"]).read_text()
    )
    assert contract["timeline"] == predecessor["timeline"]
    assert contract["metric"] == predecessor["metric"]
    assert contract["acceptance"] == predecessor["acceptance"]
    assert contract["gates"]["expected_total_frame_count"] == 423


def test_or85_freezes_camera_transform_and_all_external_boundaries() -> None:
    contract = json.loads(DEFAULT_CONTRACT.read_text())
    assert contract["selected_camera"]["refit_allowed"] is False
    assert contract["selected_workcell_transform"]["refit_allowed"] is False
    assert len(contract["selected_workcell_transform"]["vector"]) == 3
    boundary = contract["resource_boundary"]
    assert boundary["camera_fits_allowed"] == 0
    assert boundary["workcell_transform_fits_allowed"] == 0
    assert boundary["appearance_fits_allowed"] == 0
    assert boundary["validation_reads_allowed"] == 0
    assert boundary["evaluator_heldout_reads_allowed"] == 0
