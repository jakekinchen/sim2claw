from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_reset_reference import (
    load_reset_reference_contract,
    run_reset_reference_audit,
)


SOURCE_SENTINEL = REPO_ROOT / "datasets" / "manipulation_source_recordings"


def test_reset_contract_is_action_frozen_and_non_authoritative() -> None:
    contract = load_reset_reference_contract()
    assert all(contract["action_invariance"].values())
    assert not any(contract["authority"].values())


@pytest.mark.skipif(not SOURCE_SENTINEL.is_dir(), reason="physical source assets unavailable")
def test_live_reset_audit_retains_action_bytes_and_rejects_primary_gap(tmp_path: Path) -> None:
    receipt = run_reset_reference_audit(
        source_repository_root=REPO_ROOT, output_root=tmp_path
    )
    assert receipt["action_arrays_byte_identical_across_variants"] is True
    assert receipt["decision"]["reset_reference_is_primary_remaining_gap"] is False
    assert (tmp_path / "reset_reference_receipt.json").is_file()
