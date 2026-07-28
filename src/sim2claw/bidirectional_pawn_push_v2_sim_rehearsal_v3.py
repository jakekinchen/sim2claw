"""V05-v3 orchestration adapter for the frozen arm-margin/jaw-stop gates."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, Sequence

from . import bidirectional_pawn_push_v2_sim_rehearsal_v2 as _v2
from .paths import REPO_ROOT


PushRehearsalError = _v2.PushRehearsalError


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_binding(binding: dict[str, Any]) -> None:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise PushRehearsalError(
            f"bound rehearsal implementation changed: {path}"
        )


def _load_binding(binding: dict[str, Any]) -> dict[str, Any]:
    _verify_binding(binding)
    return json.loads(
        (REPO_ROOT / str(binding["path"])).read_text(encoding="utf-8")
    )


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal.v3"
    ):
        raise PushRehearsalError("unexpected rehearsal-v3 contract schema")
    for field in (
        "implementation",
        "v2_implementation",
        "base_implementation",
    ):
        _verify_binding(contract[field])

    compatibility = copy.deepcopy(
        _load_binding(contract["frozen_v2_contract"])
    )
    compatibility["gates"]["minimum_joint_limit_margin_rad"] = (
        compatibility["gates"]["minimum_arm_joint_limit_margin_rad"]
    )

    temporary_parent = REPO_ROOT / "runs" / "orchestration-fixtures"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="v05-v3-compat-",
        dir=temporary_parent,
        delete=False,
        encoding="utf-8",
    ) as handle:
        compatibility_path = Path(handle.name)
        json.dump(compatibility, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        receipt = _v2.evaluate(compatibility_path, output_path)
    finally:
        compatibility_path.unlink(missing_ok=True)

    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_sim_rehearsal_receipt.v3"
            ),
            "proof_class": (
                "cpu_fp64_sim_only_straight_closed_jaw_push_"
                "rehearsal_arm_margin_jaw_stop_v3"
            ),
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(contract_path),
            "orchestration_compatibility": {
                "legacy_key_supplied_in_temporary_internal_contract": (
                    "minimum_joint_limit_margin_rad"
                ),
                "legacy_key_value_source": (
                    "gates.minimum_arm_joint_limit_margin_rad"
                ),
                "temporary_contract_retained": False,
                "grid_or_action_changed": False,
                "dynamic_rule_changed": False,
            },
            "claim_boundary": (
                "Versioned simulation-only rehearsal correcting only the "
                "legacy orchestration key path for already-frozen arm-margin "
                "and jaw-stop semantics; no physical task, transfer, "
                "promotion, or success claim."
            ),
        }
    )
    output_path.write_text(
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
