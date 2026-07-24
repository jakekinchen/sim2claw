from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sim2claw.hil_publication import (
    HILPublicationError,
    load_hil_publication_binding,
    verify_hil_publication,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLICATION = Path(
    "configs/evaluations/current_100mm_hil_publication_v1.json"
)
EVIDENCE_AVAILABLE = (
    REPO_ROOT / "runs/current-100mm-hil-identifiability-20260724/campaign_state.json"
).is_file()


def test_binding_rejects_widened_status(tmp_path: Path) -> None:
    path = tmp_path / PUBLICATION
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "sim2claw.hil_identifiability_publication.v1",
                "status": "mutable",
                "packet_ids": [
                    "HIL-GRIPPER-05",
                    "HIL-SHOULDER-LIFT-22",
                    "HIL-ELBOW-FLEX-22",
                    "HIL-WRIST-FLEX-30",
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HILPublicationError, match="not frozen"):
        load_hil_publication_binding(repo_root=tmp_path)


@pytest.mark.skipif(not EVIDENCE_AVAILABLE, reason="local HIL evidence unavailable")
def test_current_publication_rederives_packet_and_simulator_evaluations() -> None:
    bundle = verify_hil_publication(repo_root=REPO_ROOT)
    assert [
        (row["packet_id"], row["summary"]["admitted"])
        for row in bundle["packets"]
    ] == [
        ("HIL-GRIPPER-05", True),
        ("HIL-SHOULDER-LIFT-22", True),
        ("HIL-ELBOW-FLEX-22", False),
        ("HIL-WRIST-FLEX-30", False),
    ]
    assert bundle["campaign"]["budget"]["used_physical_packet_attempts"] == 4
    assert (
        bundle["simulator"]["evaluation"]["verdict"]
        == "diagnostic_shoulder_range_external_tie_or_loss_no_promotion"
    )
    assert bundle["simulator"]["evaluation"]["simulator_parameter_promoted"] is False


@pytest.mark.skipif(not EVIDENCE_AVAILABLE, reason="local HIL evidence unavailable")
def test_publication_hash_tamper_fails_closed() -> None:
    publication = json.loads((REPO_ROOT / PUBLICATION).read_text(encoding="utf-8"))
    tampered = copy.deepcopy(publication)
    tampered["physical"]["summary_sha256"] = "0" * 64
    with patch(
        "sim2claw.hil_publication.load_hil_publication_binding",
        return_value=tampered,
    ):
        with pytest.raises(HILPublicationError, match="summary hash changed"):
            verify_hil_publication(repo_root=REPO_ROOT)


@pytest.mark.skipif(not EVIDENCE_AVAILABLE, reason="local HIL evidence unavailable")
def test_publication_authority_widening_fails_closed() -> None:
    publication = json.loads((REPO_ROOT / PUBLICATION).read_text(encoding="utf-8"))
    tampered = copy.deepcopy(publication)
    tampered["authority"]["training"] = True
    with patch(
        "sim2claw.hil_publication.load_hil_publication_binding",
        return_value=tampered,
    ):
        with pytest.raises(HILPublicationError, match="widened authority"):
            verify_hil_publication(repo_root=REPO_ROOT)
