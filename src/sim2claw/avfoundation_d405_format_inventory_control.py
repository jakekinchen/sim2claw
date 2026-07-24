"""Post-terminal control plane for the exhausted D405 format inventory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
)


GUARD_PATH = Path(
    "configs/evaluations/"
    "avfoundation_d405_format_inventory_v1_exhausted.json"
)
EXPECTED_GUARD = {
    "schema_version": "sim2claw.avfoundation_d405_format_inventory_exhaustion.v1",
    "contract_id": "current-100mm-d405-avfoundation-format-inventory-20260724-v1",
    "status": "terminal_observation_budget_exhausted",
    "contract_sha256": (
        "fac08af1fab964ccc1f367d1ab97a5495fe6c535cea79b837a327b1de51cecef"
    ),
    "execution_commit": "2e3a94f3f716a8bb098e752e74c762f34e8d3727",
    "sealing_commit": "7f2bbbb978518c5e321c0735c1ebcefe972092d5",
    "inventory_observations_used": 1,
    "inventory_observations_maximum": 1,
    "retry_authorized": False,
    "verdict": "supported_d405_common_session_candidate",
    "raw_inventory_sha256": (
        "ca2bef8b552fee3c55ae9cffd6bd2da0f5286449dd7c76f5922ef65dadd7917a"
    ),
    "evaluation_sha256": (
        "68ad34b9e004b5781f73a38e2c7df88536f0e5291b3845d90856a0e69d9edb8b"
    ),
    "receipt_sha256": (
        "fb4e76d990b44bd5633fa3ec955c1480c044430bd8e32427b9386269f4553ed3"
    ),
    "receipt_digest": (
        "674d5825732ad72f0ea2513519307098f3c7dc27e7a26926fe5fcceadeee22b8"
    ),
}


def load_exhaustion_guard(path: Path = GUARD_PATH) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationFormatInventoryError(
            f"D405 inventory exhaustion guard is unavailable: {error}"
        ) from error
    if payload != EXPECTED_GUARD:
        raise AVFoundationFormatInventoryError(
            "D405 inventory exhaustion guard changed."
        )
    return payload


def run_authorized_observation(*_: object, **__: object) -> NoReturn:
    """Refuse every post-terminal observation before runner/device delegation."""

    load_exhaustion_guard()
    raise AVFoundationFormatInventoryError(
        "D405 format-inventory family is exhausted; no retry is authorized."
    )
