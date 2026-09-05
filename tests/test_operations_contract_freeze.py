"""Keep the accepted cross-repository v1 metadata contract byte-identical."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("relative_path", "accepted_sha256"),
    [
        (
            "configs/operations/workspace_adapter.v1.schema.json",
            "7f6115335dac03c0493940ed9f63d1aba0c741ba55defd434b5208acedf52bf0",
        ),
        (
            "configs/operations/workspace_adapter.v1.fixtures.json",
            "7ea788e0ddce6ce77a99ae18fb1c87589ec5437806ed68ed6d2b8efde0f6eaa4",
        ),
    ],
)
def test_workspace_adapter_v1_retains_accepted_bytes(
    relative_path: str, accepted_sha256: str
) -> None:
    actual = hashlib.sha256((REPO_ROOT / relative_path).read_bytes()).hexdigest()
    assert actual == accepted_sha256, (
        f"The accepted workspace adapter v1 contract changed: {relative_path}. "
        "Preserve v1 bytes and introduce a separately reviewed versioned successor "
        "with bilateral conformance; do not update this digest to bless local drift."
    )
