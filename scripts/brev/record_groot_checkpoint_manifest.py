#!/usr/bin/env python3
"""Record a deterministic manifest for a completed GR00T checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "sim2claw.groot_checkpoint_manifest.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-step", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checkpoint = args.checkpoint.resolve()
    output = args.output.resolve()
    if not checkpoint.is_dir():
        raise FileNotFoundError(f"checkpoint directory is missing: {checkpoint}")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite checkpoint manifest: {output}")

    trainer_state_path = checkpoint / "trainer_state.json"
    trainer_state = json.loads(trainer_state_path.read_text())
    if trainer_state.get("global_step") != args.expected_step:
        raise ValueError("checkpoint global step does not match the expected step")

    inventory: list[dict[str, Any]] = []
    for path in sorted(checkpoint.rglob("*")):
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"unexpected checkpoint entry: {path}")
        inventory.append(
            {
                "path": path.relative_to(checkpoint).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not inventory:
        raise ValueError("checkpoint inventory is empty")

    weight_files = [
        row for row in inventory if str(row["path"]).endswith(".safetensors")
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "checkpoint_name": checkpoint.name,
        "global_step": trainer_state["global_step"],
        "file_count": len(inventory),
        "weight_file_count": len(weight_files),
        "total_size_bytes": sum(int(row["size_bytes"]) for row in inventory),
        "inventory": inventory,
        "inventory_sha256": canonical_sha256(inventory),
        "training_cannot_promote": True,
        "checkpoint_is_a_policy_result": False,
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
