from __future__ import annotations

import json

from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.paths import REPO_ROOT
from sim2claw.sail.grasp_retention_closeout import compile_grasp_retention_closeout


def test_closeout_preserves_terminal_negative_and_action_invariance(tmp_path) -> None:
    receipt = compile_grasp_retention_closeout(output_path=tmp_path / "receipt.json")

    assert receipt["candidate_runs"] == 98
    assert receipt["anchor_passes"] == 0
    assert receipt["all_actions_byte_identical"]
    assert not receipt["simulator_promotion"]
    assert not receipt["experimental_implementation"]["default_enabled"]
    assert receipt["causal_gains"]["fixed_rubber_alignment"]["delay_frames"] == 58


def test_static_closeout_publication_is_receipt_bound() -> None:
    publication = (
        REPO_ROOT
        / "src"
        / "sim2claw"
        / "studio_web"
        / "publication"
        / "sail_grasp_retention_resolution_v1"
    )
    receipt = json.loads((publication / "receipt.json").read_text())
    manifest = json.loads((publication / "manifest.json").read_text())

    assert manifest["result"]["candidate_runs"] == 98
    assert not manifest["authority"]["simulator_promotion"]
    assert not receipt["physical_authority"]
    for relative, expected in receipt["files"].items():
        assert sha256_file(REPO_ROOT / relative) == expected

    script = (REPO_ROOT / "src/sim2claw/studio_web/project-application.js").read_text()
    assert "/publication/sail_grasp_retention_resolution_v1/manifest.json" in script
