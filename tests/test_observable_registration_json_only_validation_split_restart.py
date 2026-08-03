from __future__ import annotations

import json

from sim2claw.observable_registration_json_only_validation_split_restart import (
    load_json_only_validation_split_restart_contract,
    run_json_only_validation_split_restart_once,
)


def test_contract_freezes_non_retroactive_json_only_split_restart() -> None:
    contract = load_json_only_validation_split_restart_contract()

    assert contract["split"]["expanded_development_positions"] == list(range(1, 8))
    assert contract["split"]["fresh_validation_positions"] == [8, 9]
    assert contract["split"]["final_evaluator_heldout_positions"] == [10, 11]
    assert contract["split"]["retroactive_validation_claim_allowed"] is False
    assert contract["physical_access"]["video_decode_allowed"] is False
    assert contract["execution"]["physical_frames_decoded_allowed"] == 0
    assert not any(contract["authority"].values())


def test_split_restart_emits_json_without_opening_fresh_roles(tmp_path) -> None:
    output = tmp_path / "or88"
    receipt = run_json_only_validation_split_restart_once(output_directory=output)

    assert receipt["status"] == "PASS_JSON_ONLY_VALIDATION_SPLIT_RESTART_FROZEN"
    assert all(receipt["gates"].values())
    assert receipt["result"]["role_counts"] == {
        "expanded_development": 7,
        "fresh_validation": 2,
        "final_evaluator_heldout": 2,
    }
    assert receipt["result"]["fresh_validation_reads"] == 0
    assert receipt["result"]["final_evaluator_heldout_reads"] == 0
    assert not any(
        value
        for name, value in receipt["execution"].items()
        if name != "paid_compute"
    )
    assert receipt["execution"]["paid_compute"] is False

    manifest = json.loads((output / "split_manifest.json").read_text())
    assert manifest["fresh_validation_unread_recording_ids"] == [
        "20260719T031813Z-b147b429",
        "20260719T032440Z-f728a18c",
    ]
    assert manifest["final_evaluator_heldout_unread_recording_ids"] == [
        "20260719T031324Z-bf91502b",
        "20260719T031715Z-61ebb199",
    ]
    assert manifest["or88_physical_video_decodes"] == 0
