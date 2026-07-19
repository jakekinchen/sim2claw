#!/usr/bin/env python3
"""Record exact offline model snapshots for the bounded pawn GR00T run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


BASE_MODEL_REPO = "nvidia/GR00T-N1.7-3B"
BASE_MODEL_REVISION = "2fc962b973bccdd5d8ce4f67cc63b264d6886495"
PROCESSOR_REPO = "nvidia/Cosmos-Reason2-2B"
PROCESSOR_REVISION = "9ce19a195e423419c349abfc86fd07178b230561"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def snapshot_inventory(path: Path, expected_revision: str) -> dict[str, Any]:
    if not path.is_dir():
        raise SystemExit(f"snapshot is missing: {path}")
    if path.name != expected_revision:
        raise SystemExit(f"snapshot revision drifted: {path.name} != {expected_revision}")

    rows: list[dict[str, Any]] = []
    for entry in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        if entry.is_dir():
            continue
        if entry.is_symlink() and not entry.exists():
            raise SystemExit(f"broken model-snapshot symlink: {entry}")
        if not entry.is_file():
            raise SystemExit(f"unexpected snapshot entry: {entry}")
        rows.append(
            {
                "path": entry.relative_to(path).as_posix(),
                "size_bytes": entry.stat().st_size,
                "sha256": sha256_file(entry),
                "is_symlink": entry.is_symlink(),
                "symlink_target": entry.readlink().as_posix() if entry.is_symlink() else None,
            }
        )
    if not rows:
        raise SystemExit(f"snapshot is empty: {path}")
    return {
        "path": str(path.resolve()),
        "revision": expected_revision,
        "file_count": len(rows),
        "inventory": rows,
        "inventory_sha256": canonical_sha256(rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model-path", type=Path, required=True)
    parser.add_argument("--processor-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    self_path = Path(__file__).resolve()
    payload = {
        "schema_version": "sim2claw.groot_n17_pawn_model_snapshots.v1",
        "base_model": {
            "repo_id": BASE_MODEL_REPO,
            **snapshot_inventory(args.base_model_path, BASE_MODEL_REVISION),
        },
        "processor": {
            "repo_id": PROCESSOR_REPO,
            **snapshot_inventory(args.processor_path, PROCESSOR_REVISION),
        },
        "recorder_sha256": sha256_file(self_path),
        "network_required_for_training": False,
        "model_queries": 0,
        "training_started": False,
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
