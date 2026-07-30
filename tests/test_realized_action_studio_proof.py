from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.realized_action_studio_proof import (
    CONTRACT_PATH,
    compile_realized_action_studio_proof,
    load_realized_action_studio_proof,
)
from sim2claw.studio_server import create_server


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RECEIPT = (
    REPO_ROOT / "outputs" / "realized_action_outcome_mission_v1" / "receipt.json"
)


def test_proof_compiler_is_deterministic_and_keeps_missingness_explicit(
    tmp_path: Path,
) -> None:
    if not REQUIRED_RECEIPT.is_file():
        pytest.skip("owner-local realized-action receipts are unavailable")
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_receipt = compile_realized_action_studio_proof(
        CONTRACT_PATH,
        first,
        root=REPO_ROOT,
    )
    second_receipt = compile_realized_action_studio_proof(
        CONTRACT_PATH,
        second,
        root=REPO_ROOT,
    )
    first_bundle = json.loads((first / "bundle.json").read_text())
    second_bundle = json.loads((second / "bundle.json").read_text())
    assert first_bundle == second_bundle
    assert (
        first_receipt["bundle"]["artifact_sha256"]
        == second_receipt["bundle"]["artifact_sha256"]
    )
    assert first_bundle["proof_status"]["action_to_outcome"] == (
        "TERMINAL_NEGATIVE_0_OF_1"
    )
    assert first_bundle["proof_status"]["plant_identification"] == (
        "PASS_VALIDATED_EFFECTIVE_JOINT_PLANT"
    )
    assert first_bundle["timeline"]["sample_count"] == 531
    assert len(first_bundle["timeline"]["requested_degrees"]) == 531
    assert len(first_bundle["timeline"]["identified_applied_degrees"]) == 531
    assert [row["sample_index"] for row in first_bundle["failure_markers"]] == [
        386,
        388,
    ]
    availability = {
        row["id"]: row["status"] for row in first_bundle["availability"]
    }
    assert availability["physical_contact_state"] == "missing"
    assert availability["global_robot_mapping"] == "unapproved"
    assert availability["probabilistic_uncertainty"] == "unavailable"
    assert first_bundle["authority"]["physical_motion"] is False
    assert first_bundle["authority"]["write"] is False


def test_proof_loader_rejects_bundle_tampering(tmp_path: Path) -> None:
    if not REQUIRED_RECEIPT.is_file():
        pytest.skip("owner-local realized-action receipts are unavailable")
    compile_realized_action_studio_proof(
        CONTRACT_PATH,
        tmp_path,
        root=REPO_ROOT,
    )
    bundle_path = tmp_path / "bundle.json"
    bundle = json.loads(bundle_path.read_text())
    bundle["proof_status"]["action_to_outcome"] = "PASS"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(FactoryArtifactError, match="bundle changed"):
        load_realized_action_studio_proof(
            root=REPO_ROOT,
            contract_path=CONTRACT_PATH,
            output_directory=tmp_path,
        )


def test_studio_serves_read_only_realized_action_proof(tmp_path: Path) -> None:
    payload = {
        "available": True,
        "schema_version": "sim2claw.realized_action_studio_proof.v1",
        "read_only": True,
        "physical_authority": False,
    }
    with patch(
        "sim2claw.studio_server.load_observable_registration_studio_proof",
        return_value=payload,
    ):
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/api/realized-action-proof") as response:
                observed = json.load(response)
            assert observed == payload
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_frontend_has_dedicated_desktop_and_phone_proof_surface() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text()
    css = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text()
    js = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text()
    assert 'data-route="proof"' in html
    assert 'data-view-panel="proof"' in html
    assert 'id="proof-video"' in html
    assert 'id="proof-scrubber"' in html
    assert 'id="proof-plot"' in html
    assert 'id="proof-availability-grid"' in html
    assert 'id="proof-registration-list"' in html
    assert 'id="proof-spatial-list"' in html
    assert 'fetch("/api/realized-action-proof"' in js
    assert '["replay", "sail", "proof", "library"' in js
    assert ".proof-view" in css
    assert "@media (max-width: 620px)" in css
    assert ".proof-scrub-head" in css


def test_current_graph_preserves_campaign_results_and_authority() -> None:
    graph = json.loads(
        (
            REPO_ROOT
            / "configs"
            / "sail"
            / "realized_action_outcome_current_graph_v1.json"
        ).read_text()
    )
    assert graph["status"] == "complete_safe_scope_external_service_boundary"
    assert not any(graph["authority"].values())
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["mechanism:c4-effective-plant"]["status"] == (
        "validated_effective_joint_plant"
    )
    assert nodes["counterexample:c6-action-outcome"]["status"] == (
        "terminal_negative_0_of_1"
    )
    assert nodes["boundary:c9-elbow-service"]["data"]["policy_ranking"] == (
        "insufficient_physical_sample"
    )


def test_post_service_successor_is_ordered_and_not_executable() -> None:
    successor = json.loads(
        (
            REPO_ROOT
            / "configs"
            / "evaluations"
            / "realized_action_post_service_successor_v1.json"
        ).read_text()
    )
    assert successor["status"] == (
        "deferred_preconditions_only_not_an_executable_packet"
    )
    assert [
        item["id"] for item in successor["restart_preconditions_in_order"]
    ] == [f"PS{index}" for index in range(9)]
    assert successor["packet_state"]["action_tensor_frozen"] is False
    assert successor["packet_state"]["hardware_execution_allowed"] is False
    assert not any(successor["authority"].values())
