"""V05-v4 path-safe finalizer for the frozen rehearsal-v3 pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from . import bidirectional_pawn_push_v2_sim_rehearsal_v3 as _v3
from .paths import REPO_ROOT


PushRehearsalError = _v3.PushRehearsalError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_public(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise PushRehearsalError("public rehearsal path escapes repository") from error
    return resolved


def _verify_binding(binding: dict[str, Any]) -> Path:
    path = _resolve_public(Path(str(binding["path"])))
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise PushRehearsalError(f"bound rehearsal input changed: {path}")
    return path


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    public_contract_path = _resolve_public(contract_path)
    public_output_path = _resolve_public(output_path)
    contract = json.loads(public_contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal.v4"
    ):
        raise PushRehearsalError("unexpected rehearsal-v4 contract schema")
    for field in ("implementation", "v3_implementation"):
        _verify_binding(contract[field])
    frozen_v3_path = _verify_binding(contract["frozen_v3_contract"])

    receipt = _v3.evaluate(frozen_v3_path.resolve(), public_output_path)
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_sim_rehearsal_receipt.v4"
            ),
            "proof_class": (
                "cpu_fp64_sim_only_straight_closed_jaw_push_"
                "rehearsal_path_safe_finalization_v4"
            ),
            "contract_path": str(
                public_contract_path.relative_to(REPO_ROOT.resolve())
            ),
            "contract_sha256": _sha(public_contract_path),
            "public_path_resolution": {
                "contract_resolved_before_repo_binding": True,
                "output_resolved_before_write": True,
                "retained_contract_resolves": public_contract_path.is_file(),
                "temporary_contract_retained": False,
                "grid_or_action_changed": False,
            },
            "claim_boundary": (
                "Versioned simulation-only rehearsal correcting only public "
                "contract/output path resolution after the frozen v3 "
                "pipeline; no physical task, transfer, promotion, or success "
                "claim."
            ),
        }
    )
    public_output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    receipt = evaluate(args.contract, args.output)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "passing_case_ids": receipt["passing_case_ids"],
                "direction_gate": receipt["direction_gate"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["PushRehearsalError", "evaluate", "main"]
