from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_contact_sensitivity import (
    load_contact_sensitivity_contract,
    run_contact_sensitivity,
)


SOURCE_SENTINEL = REPO_ROOT / "datasets" / "manipulation_source_recordings"


def test_contact_contract_forbids_selection_and_authority() -> None:
    contract = load_contact_sensitivity_contract()
    assert contract["selection"]["allowed"] is False
    assert all(contract["action_invariance"].values())
    assert not any(contract["authority"].values())


@pytest.mark.skipif(not SOURCE_SENTINEL.is_dir(), reason="physical source assets unavailable")
def test_live_contact_sensitivity_retains_actions_and_selects_nothing(tmp_path: Path) -> None:
    receipt = run_contact_sensitivity(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["action_arrays_byte_identical_across_variants"] is True
    assert receipt["decision"]["selected_variant"] is None
    assert receipt["decision"]["simulator_composite_promoted"] is False
    assert (tmp_path / "contact_sensitivity_receipt.json").is_file()
