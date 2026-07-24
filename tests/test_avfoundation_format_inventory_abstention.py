from __future__ import annotations

from pathlib import Path

import pytest

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
)
from sim2claw.avfoundation_format_inventory_abstention import (
    FAILURE_SIGNATURE,
    seal_format_inventory_prerequisite_abstention,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/avfoundation_format_inventory_v1.json"
)


def _failed_observation(root: Path) -> Path:
    observation_root = root / "observed"
    binary = observation_root / "runtime/avfoundation-format-inventory"
    stderr = observation_root / "raw/inventory.stderr.log"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic failed binary\n")
    stderr.parent.mkdir(parents=True)
    stderr.write_text(
        f"uncaught exception: {FAILURE_SIGNATURE}\n",
        encoding="utf-8",
    )
    return observation_root


def test_sealer_materializes_terminal_prerequisite_abstention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _failed_observation(tmp_path)
    evaluation, receipt = seal_format_inventory_prerequisite_abstention(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["inventory_observation_attempt_count"] == 1
    assert evaluation["usable_inventory_observation_count"] == 0
    assert evaluation["raw_inventory_available"] is False
    assert evaluation["format_count"] is None
    assert evaluation["selected_candidate"] is None
    assert evaluation["budget"]["capture_sessions_used"] == 0
    assert evaluation["claim_limits"]["native_format_surface_observed"] is False
    assert receipt["verdict"] == "prerequisite_abstention"


def test_sealer_is_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _failed_observation(tmp_path)
    first_evaluation, first_receipt = seal_format_inventory_prerequisite_abstention(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "eval-1",
    )
    second_evaluation, second_receipt = (
        seal_format_inventory_prerequisite_abstention(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "eval-2",
        )
    )
    assert first_evaluation == second_evaluation
    assert first_receipt == second_receipt
    assert (tmp_path / "eval-1/evaluation.json").read_bytes() == (
        tmp_path / "eval-2/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "eval-1/receipt.json").read_bytes() == (
        tmp_path / "eval-2/receipt.json"
    ).read_bytes()


def test_sealer_refuses_to_discard_raw_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _failed_observation(tmp_path)
    raw = observation_root / "raw/inventory.json"
    raw.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AVFoundationFormatInventoryError, match="cannot discard"):
        seal_format_inventory_prerequisite_abstention(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "evaluated",
        )


def test_sealer_rejects_failure_signature_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _failed_observation(tmp_path)
    (observation_root / "raw/inventory.stderr.log").write_text(
        "different failure\n",
        encoding="utf-8",
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="signature"):
        seal_format_inventory_prerequisite_abstention(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "evaluated",
        )
