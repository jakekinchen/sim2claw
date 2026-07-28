"""Post-terminal control for the exhausted C922 frame-lineage proof."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

from sim2claw.frame_extraction_lineage import FrameExtractionLineageError


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = (
    REPO_ROOT / "configs/evaluations/current_100mm_frame_lineage_v1_exhausted.json"
)
EXPECTED_GUARD = {
    "schema_version": "sim2claw.frame_extraction_lineage_exhaustion.v1",
    "contract_id": "current_100mm_c922_frame_lineage_v1",
    "status": "terminal_lineage_verified_budget_exhausted",
    "contract_sha256": "331bf9226cd17248b3cf80c503e47d7e01c913755b4077c25aa94896b0396a3f",
    "execution_commit": "cc303045d2ee5fd3e24356b506af34655faa14f5",
    "runner_evaluator_sha256": "2dc87159cbec9b26f6aae4dee8ceede20ed2fb23921a3169bbaebeca57963955",
    "decoder_wrapper_sha256": "dec55ed7dfbb5f12e79c5564ec7605c661ed4242f64c43587d00e4867dfda1a2",
    "prelaunch_sha256": "ddb1abce84fed82fb2c70601e5412d76dae9c826b7c37a33d6f315bc7ba6da02",
    "probe_stdout_sha256": "0f8ea74f04c3a2be9871a86a0b168a5656836b2a53867a5dd303dc53d30d492e",
    "derived_frame_sha256": "2543230b795c8a61ab6f7ddb1e9c672588ea88958cddbbb84397d689034b5dfc",
    "derived_frame_rgb24_sha256": "7046a08b731c736471c73abba80bbcc366b650569bee5bbf6d4db97366cecaa8",
    "evaluation_sha256": "4788a827c10514164e4ca457a57e322285e12e0df2d282e09b27769fc8f4b496",
    "evaluation_digest": "a2cf32e045c5234ecec940b1d2bea507771dfe6c6e57992fee65de25e89b5b4e",
    "receipt_sha256": "3b44795c161c9f19025a64b244aadea9d03c93ca2635449d90781f6a1a957ed7",
    "receipt_digest": "15d90882157bf6ad91e497a33a15e2ade3098876d8ad09029b692db85c28f246",
    "verdict": "frame_extraction_lineage_verified",
    "metadata_probes_used": 1,
    "frame_derivations_used": 1,
    "retries_used": 0,
    "retry_authorized": False,
}


def load_exhaustion_guard(path: Path = GUARD_PATH) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FrameExtractionLineageError(
            f"Frame-lineage exhaustion guard is unavailable: {error}"
        ) from error
    if value != EXPECTED_GUARD:
        raise FrameExtractionLineageError("Frame-lineage exhaustion guard changed.")
    return value


def run_authorized_derivation(*_: object, **__: object) -> NoReturn:
    load_exhaustion_guard()
    raise FrameExtractionLineageError(
        "Current C922 frame-lineage v1 is exhausted; no retry is authorized."
    )
