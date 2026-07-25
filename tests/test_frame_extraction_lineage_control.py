from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.frame_extraction_lineage import FrameExtractionLineageError
from sim2claw.frame_extraction_lineage_control import (
    EXPECTED_GUARD,
    GUARD_PATH,
    load_exhaustion_guard,
    run_authorized_derivation,
)


def test_guard_matches_exact_verified_result() -> None:
    assert load_exhaustion_guard() == EXPECTED_GUARD
    assert EXPECTED_GUARD["verdict"] == "frame_extraction_lineage_verified"
    assert EXPECTED_GUARD["metadata_probes_used"] == 1
    assert EXPECTED_GUARD["frame_derivations_used"] == 1
    assert EXPECTED_GUARD["retries_used"] == 0
    assert EXPECTED_GUARD["retry_authorized"] is False


def test_control_refuses_before_derivation_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("sim2claw.frame_extraction_lineage.materialize", forbidden)
    with pytest.raises(FrameExtractionLineageError, match="exhausted"):
        run_authorized_derivation(output_root=Path("/tmp/arbitrary"))
    assert called is False


@pytest.mark.parametrize("field", ["retry_authorized", "receipt_sha256", "verdict"])
def test_guard_mutation_fails_closed(tmp_path: Path, field: str) -> None:
    value = dict(EXPECTED_GUARD)
    value[field] = True if field == "retry_authorized" else "0" * 64
    path = tmp_path / GUARD_PATH.name
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(FrameExtractionLineageError, match="changed"):
        load_exhaustion_guard(path)
