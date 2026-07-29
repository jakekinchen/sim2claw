from __future__ import annotations

from sim2claw.realized_action_robustness import load_contract


def test_contract_preserves_c6_and_unknowns() -> None:
    contract = load_contract()
    assert contract["rules"]["c6_identified_path_not_rerun"] is True
    assert contract["uncertainty"]["geometry_distribution"] is None
    assert contract["uncertainty"]["contact_distribution"] is None
    assert contract["uncertainty"]["unknown_dimensions_randomized"] is False


def test_only_declared_challengers_are_present() -> None:
    contract = load_contract()
    assert [row["path_id"] for row in contract["challenger_paths"]] == [
        "direct_target",
        "diagnostic_zoh_0p11s",
    ]
    assert contract["challenger_paths"][1]["calibrated_plant"] is False


def test_physical_authority_remains_false() -> None:
    contract = load_contract()
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key != "simulator_replay"
    )
