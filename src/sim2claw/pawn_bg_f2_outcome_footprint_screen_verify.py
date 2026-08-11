"""Independently adjudicate OR144 from its frozen receipt without new replay."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "pawn_bg_f2_outcome_footprint_screen_adjudication_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "pawn_bg_f2_outcome_footprint_screen_adjudication_v1"
    / "receipt.json"
)
SCHEMA = "sim2claw.pawn_bg_f2_outcome_footprint_screen_adjudication.v1"


class FootprintAdjudicationError(RuntimeError):
    """The frozen OR144 inputs or adjudication rules drifted."""


def _validate_binding(binding: Mapping[str, Any]) -> Path:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or sha256_file(path) != str(binding["sha256"]):
        raise FootprintAdjudicationError(f"source binding drifted: {binding['path']}")
    return path


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise FootprintAdjudicationError("unexpected adjudication schema")
    _validate_binding(contract["authorization"])
    for binding in contract["source_bindings"].values():
        _validate_binding(binding)
    if any(contract.get("authority", {}).values()):
        raise FootprintAdjudicationError("adjudication authority widened")
    if contract["rules"] != {
        "maximum_tilt_degrees": 10.0,
        "minimum_rise_m": 0.04,
        "warning_count": 0,
        "piece_lifted_required": True,
        "wrong_piece_contact_count": 0,
        "maximum_other_piece_displacement_m": 0.001,
    }:
        raise FootprintAdjudicationError("adjudication rules drifted")
    return contract


def _wrong_piece_names(row: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            str(contact["piece_name"])
            for contact in row["episode"]["wrong_piece_robot_contacts"]
        }
    )


def adjudicate(*, contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = load_contract(contract_path)
    receipt_path = REPO_ROOT / contract["source_bindings"]["or144_receipt"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_for_digest = copy.deepcopy(receipt)
    observed_digest = str(receipt_for_digest.pop("receipt_digest"))
    if canonical_digest(receipt_for_digest) != observed_digest:
        raise FootprintAdjudicationError("OR144 receipt digest mismatch")
    if receipt.get("candidate_count") != 16 or len(receipt.get("rows", [])) != 16:
        raise FootprintAdjudicationError("OR144 candidate count drifted")

    rules = contract["rules"]
    rows = []
    for source_row in receipt["rows"]:
        screen = source_row["screen_metrics"]
        episode = source_row["episode"]
        recomputed = {
            "continuous_upright": (
                float(screen["maximum_tilt_degrees_full_step"])
                <= float(rules["maximum_tilt_degrees"])
            ),
            "rise": (
                float(screen["maximum_rise_m_full_step"])
                >= float(rules["minimum_rise_m"])
            ),
            "warning_free": (
                int(screen["warning_count_sum"]) == int(rules["warning_count"])
            ),
        }
        if recomputed != source_row["screen_gates"]:
            raise FootprintAdjudicationError(
                f"stored screen gates drifted: {source_row['candidate_id']}"
            )
        wrong_names = _wrong_piece_names(source_row)
        eligible = bool(
            all(recomputed.values())
            and episode["piece_lifted"]
            and not wrong_names
            and float(episode["maximum_other_piece_displacement_m"])
            <= float(rules["maximum_other_piece_displacement_m"])
        )
        rows.append(
            {
                "candidate_id": source_row["candidate_id"],
                "parameter_digest": source_row["parameter_digest"],
                "screen_gates": recomputed,
                "piece_lifted": bool(episode["piece_lifted"]),
                "transported_after_lift": bool(episode["transported_after_lift"]),
                "whole_base_inside_destination": bool(
                    episode["whole_base_inside_destination"]
                ),
                "wrong_piece_names": wrong_names,
                "maximum_other_piece_displacement_m": float(
                    episode["maximum_other_piece_displacement_m"]
                ),
                "eligible_for_strict_successor": eligible,
            }
        )

    isolated = next(
        row
        for row in receipt["rows"]
        if row["candidate_id"] == "coverage_0.040_width_0.0200"
    )
    admitted = [
        row["candidate_id"]
        for row in rows
        if row["eligible_for_strict_successor"]
    ]
    producer_selected = [
        str(row["candidate_id"])
        for row in receipt["selected_for_full_strict_evaluation"]
    ]
    result = {
        "schema_version": SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "source_receipt": {
            "path": str(receipt_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(receipt_path),
            "receipt_digest_verified": True,
        },
        "candidate_count": len(rows),
        "recomputed_continuous_upright_pass_count": sum(
            int(row["screen_gates"]["continuous_upright"]) for row in rows
        ),
        "eligible_for_strict_successor": admitted,
        "producer_selected_field": producer_selected,
        "producer_selected_field_authoritative": False,
        "producer_selection_bug_confirmed": bool(producer_selected and not admitted),
        "isolated_40mm_x_20mm_cell": {
            "parameter_digest": isolated["parameter_digest"],
            "maximum_tilt_degrees": isolated["screen_metrics"][
                "maximum_tilt_degrees_full_step"
            ],
            "maximum_rise_m": isolated["screen_metrics"][
                "maximum_rise_m_full_step"
            ],
            "piece_lifted": isolated["episode"]["piece_lifted"],
            "transported_after_lift": isolated["episode"][
                "transported_after_lift"
            ],
            "wrong_piece_names": _wrong_piece_names(isolated),
            "local_basin_supported": False,
        },
        "rows": rows,
        "verdict": "FOOTPRINT_LANE_TERMINAL_NO_STRICT_SUCCESSOR_ADMITTED",
        "simulator_replays_used": 0,
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    result["receipt_digest"] = canonical_digest(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    receipt = adjudicate(contract_path=args.contract.resolve())
    atomic_write_json(args.output.resolve(), receipt)
    print(
        json.dumps(
            {
                "verdict": receipt["verdict"],
                "admitted": receipt["eligible_for_strict_successor"],
                "receipt_digest": receipt["receipt_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["FootprintAdjudicationError", "adjudicate", "load_contract"]
