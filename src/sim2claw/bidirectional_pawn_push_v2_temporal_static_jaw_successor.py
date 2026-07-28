"""V05-TJ static successor that changes only the frozen gripper column."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal_v2 as _rehearsal_v2
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .paths import REPO_ROOT


class TemporalJawSuccessorError(RuntimeError):
    """The exact one-column successor failed closed."""


_BASE_COMPILE = _rehearsal_v2._compile_action_v2


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise TemporalJawSuccessorError(
            "V05-TJ path escapes repository"
        ) from error
    return resolved


def _verify_binding(binding: dict[str, Any]) -> Path:
    path = _resolve(Path(str(binding["path"])))
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise TemporalJawSuccessorError(
            f"bound V05-TJ input changed: {path}"
        )
    return path


def freeze_successor(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_temporal_static_jaw_successor.v1"
    ):
        raise TemporalJawSuccessorError(
            "unexpected V05-TJ static contract"
        )
    authorization_path = _verify_binding(contract["authorization"])
    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    _verify_binding(contract["implementation"])
    _verify_binding(contract["base_implementation"])
    _verify_binding(contract["predecessor_static_contract"])
    _verify_binding(contract["predecessor_static_receipt"])

    predecessor_jaw = float(
        authorization["successor_action_identity"][
            "predecessor_closed_jaw_rad"
        ]
    )
    successor_jaw = float(
        authorization["successor_action_identity"][
            "successor_closed_jaw_rad"
        ]
    )
    if successor_jaw != -0.1727003294848389:
        raise TemporalJawSuccessorError(
            "authorized successor jaw scalar changed"
        )

    compatibility = dict(contract)
    compatibility["schema_version"] = (
        "sim2claw.bidirectional_pawn_push_v2_temporal_static.v1"
    )
    compatibility.pop("authorization", None)
    compatibility.pop("base_implementation", None)
    compatibility.pop("predecessor_static_contract", None)
    compatibility.pop("predecessor_static_receipt", None)
    temporary_parent = REPO_ROOT / "runs" / "orchestration-fixtures"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="v05-tj-static-compat-",
        dir=temporary_parent,
        delete=False,
        encoding="utf-8",
    ) as handle:
        temporary_contract = Path(handle.name)
        json.dump(compatibility, handle, indent=2, sort_keys=True)
        handle.write("\n")

    def compile_successor(**kwargs: Any) -> tuple[np.ndarray, dict[str, Any]]:
        if float(kwargs["closed_jaw_rad"]) != predecessor_jaw:
            raise TemporalJawSuccessorError(
                "predecessor compile jaw target changed"
            )
        predecessor_action, metrics = _BASE_COMPILE(**kwargs)
        predecessor_action = np.asarray(
            predecessor_action, dtype="<f8", order="C"
        )
        successor_action = predecessor_action.copy(order="C")
        successor_action[:, 5] = successor_jaw
        predecessor_arm = np.asarray(
            predecessor_action[:, :5], dtype="<f8", order="C"
        )
        successor_arm = np.asarray(
            successor_action[:, :5], dtype="<f8", order="C"
        )
        if predecessor_arm.tobytes(order="C") != successor_arm.tobytes(
            order="C"
        ):
            raise TemporalJawSuccessorError(
                "successor changed an arm command byte"
            )
        if not np.all(successor_action[:, 5] == successor_jaw):
            raise TemporalJawSuccessorError(
                "successor jaw column is not exact"
            )
        metrics.update(
            {
                "predecessor_action_raw_float64le_sha256": hashlib.sha256(
                    predecessor_action.tobytes(order="C")
                ).hexdigest(),
                "action_raw_float64le_sha256": hashlib.sha256(
                    successor_action.tobytes(order="C")
                ).hexdigest(),
                "predecessor_arm_columns_raw_float64le_sha256": (
                    hashlib.sha256(
                        predecessor_arm.tobytes(order="C")
                    ).hexdigest()
                ),
                "successor_arm_columns_raw_float64le_sha256": (
                    hashlib.sha256(
                        successor_arm.tobytes(order="C")
                    ).hexdigest()
                ),
                "arm_columns_byte_identical": True,
                "predecessor_closed_jaw_target_rad": predecessor_jaw,
                "closed_jaw_target_rad": successor_jaw,
                "maximum_closed_jaw_target_error_rad": 0.0,
                "only_gripper_column_changed": True,
            }
        )
        return successor_action, metrics

    previous = _rehearsal_v2._compile_action_v2
    _rehearsal_v2._compile_action_v2 = compile_successor
    try:
        receipt = _static.enumerate_and_freeze(
            temporary_contract,
            public_output,
        )
    finally:
        _rehearsal_v2._compile_action_v2 = previous
        temporary_contract.unlink(missing_ok=True)

    compiled_rows = [
        row for row in receipt["grid_results"] if row.get("compile")
    ]
    if not all(
        row["compile"]["arm_columns_byte_identical"]
        and row["compile"]["only_gripper_column_changed"]
        for row in compiled_rows
    ):
        raise TemporalJawSuccessorError(
            "compiled successor identity audit failed"
        )
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_temporal_static_jaw_"
                "successor_receipt.v1"
            ),
            "proof_class": (
                "cpu_fp64_static_exact_gripper_column_successor_"
                "action_freeze_only"
            ),
            "contract_path": str(
                public_contract.relative_to(REPO_ROOT.resolve())
            ),
            "contract_sha256": _sha(public_contract),
            "authorization_sha256": contract["authorization"]["sha256"],
            "predecessor_static_receipt_sha256": contract[
                "predecessor_static_receipt"
            ]["sha256"],
            "successor_identity": {
                "predecessor_closed_jaw_rad": predecessor_jaw,
                "successor_closed_jaw_rad": successor_jaw,
                "compiled_cell_count": len(compiled_rows),
                "all_arm_columns_byte_identical": True,
                "all_row_counts_and_order_preserved": True,
                "only_gripper_column_changed": True,
                "temporary_contract_retained": False,
            },
            "claim_boundary": (
                "Static exact one-column jaw-margin successor only. No "
                "dynamic task outcome, calibrated plant, physical packet, "
                "or transfer claim."
            ),
        }
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["TemporalJawSuccessorError", "freeze_successor"]
