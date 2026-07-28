"""Control-plane entrypoint for the one-shot dual-camera lifecycle family.

The observed runner/evaluator bytes remain frozen in ``dual_camera_lifecycle``.
This separate wrapper owns canonical output routing and the durable terminal
attempt guard, so closeout hardening does not change the executed evaluator
identity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from . import dual_camera_lifecycle


GUARD_SCHEMA = "sim2claw.dual_camera_lifecycle_exhaustion_guard.v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GUARD_PATH = (
    REPO_ROOT
    / "configs/evaluations/dual_camera_lifecycle_qualification_v1_exhausted.json"
)
DEFAULT_CANONICAL_RAW_ROOT = (
    REPO_ROOT / "outputs/dual-camera-lifecycle-qualification-v1/raw"
)
EXPECTED_GUARD = {
    "schema_version": GUARD_SCHEMA,
    "status": "terminal_attempt_exhausted_no_retry",
    "contract_id": "current-100mm-dual-camera-lifecycle-qualification-20260724-v1",
    "contract_sha256": "5e97a27deaf6b874dee070ae1e6db3b81d68e4c8f9a9681ced9484e4b77fa363",
    "campaign_sha256": "093dd71de8cf79db6e84fa8b1cb1a444552cd7ffc4c849b21b2f98afbd01a8f3",
    "event_sha256": "f873b8698cb7a0ac71b548daedb9cde7a6f146e6c2d0b0662dc16b99550b3995",
    "evaluation_sha256": "bfad64080564a446f6c93b1e7c1b17fc1256a3a6b265aff11e6d72a95ba78f8b",
    "receipt_sha256": "d066fa146f4a19042686b932c7d0397f1aa2e7bfe2e163bc43b6b0353b5e17f0",
    "receipt_digest": "4e37b6b1783bc3382bf461928520e3fc0622ce0cd10c3299b39e283737b6df23",
    "attempts_used": 1,
    "attempts_maximum": 1,
    "retries_used": 0,
    "retry_authorized": False,
}


class DualCameraLifecycleControlError(RuntimeError):
    """The canonical route or durable attempt guard failed closed."""


def load_exhaustion_guard(path: Path = DEFAULT_GUARD_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        guard = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DualCameraLifecycleControlError(
            f"Lifecycle exhaustion guard is unreadable: {error}"
        ) from error
    if guard != EXPECTED_GUARD:
        raise DualCameraLifecycleControlError(
            "Lifecycle exhaustion guard identity or budget changed."
        )
    return guard


def run_once(
    *,
    contract_path: Path,
    output_root: Path,
    guard_path: Path = DEFAULT_GUARD_PATH,
    canonical_raw_root: Path = DEFAULT_CANONICAL_RAW_ROOT,
    runner: Callable[..., dict[str, Any]] = dual_camera_lifecycle.run_qualification,
) -> dict[str, Any]:
    """Route the sole family execution or fail closed before device access."""

    if load_exhaustion_guard(guard_path) is not None:
        raise DualCameraLifecycleControlError(
            "Dual-camera lifecycle family is exhausted; retry is forbidden."
        )
    if output_root.resolve() != canonical_raw_root.resolve():
        raise DualCameraLifecycleControlError(
            "Dual-camera lifecycle execution requires the canonical raw output root."
        )
    return runner(contract_path=contract_path, output_root=output_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = run_once(
        contract_path=args.contract,
        output_root=args.output_root,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
