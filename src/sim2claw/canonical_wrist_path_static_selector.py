"""Static-only selector over frozen single-lane and two-lane actions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .paths import REPO_ROOT


class CanonicalWristPathStaticSelectorError(RuntimeError):
    """The frozen static selector failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalWristPathStaticSelectorError(
            "selector input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalWristPathStaticSelectorError(
            f"selector input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def select_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise CanonicalWristPathStaticSelectorError(
            "immutable selector output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "canonical_static_receipt",
        "two_lane_static_receipt",
        "predecessor_closeout",
        "implementation",
        "selection_rule",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    expected_authority = {
        "model_loading": False,
        "static_selection": True,
        "dynamic_simulation": False,
        "mapping_approval": False,
        "camera": False,
        "gateway": False,
        "serial": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "simulator_promotion": False,
        "transfer_claim": False,
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.canonical_wrist_path_static_selector.v1"
        or contract["selection_rule"]
        != {
            "eligible_candidates": [
                "canonical_single_lane_stroke_v5",
                "two_lane_v6",
            ],
            "primary_key": (
                "minimum_absolute_first_contact_vertical_normal_component"
            ),
            "tie_break": "canonical_single_lane_stroke_v5",
            "dynamic_outcomes_used": False,
        }
        or contract["authority"] != expected_authority
    ):
        raise CanonicalWristPathStaticSelectorError(
            "static selector contract widened"
        )
    canonical = _json(contract["canonical_static_receipt"])
    two_lane = _json(contract["two_lane_static_receipt"])
    _bound(contract["predecessor_closeout"])
    _bound(contract["implementation"])
    if (
        canonical.get("status")
        != "canonical_wrist_path_stroke_static_pass"
        or not canonical.get("passed")
        or two_lane.get("status")
        != "canonical_wrist_path_two_lane_static_reject"
        or two_lane.get("passed")
        or canonical.get("dynamic_replay_executed")
        or two_lane.get("dynamic_replay_executed")
    ):
        raise CanonicalWristPathStaticSelectorError(
            "static selector admission changed"
        )
    canonical_by_id = {
        row["case_id"]: row for row in canonical["selected"]
    }
    two_lane_by_id = {
        row["case_id"]: row
        for row in two_lane["selected"]
        if row["static_eligible"]
    }
    if len(canonical_by_id) != 4 or len(two_lane_by_id) != 2:
        raise CanonicalWristPathStaticSelectorError(
            "static selector candidate counts changed"
        )
    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    selected: list[dict[str, Any]] = []
    for index, case_id in enumerate(canonical_by_id):
        canonical_row = canonical_by_id[case_id]
        candidates = [
            (
                float(
                    canonical_row["first_contact_witness"][
                        "absolute_vertical_normal_component"
                    ]
                ),
                0,
                "canonical_single_lane_stroke_v5",
                canonical_row,
            )
        ]
        if case_id in two_lane_by_id:
            two_lane_row = two_lane_by_id[case_id]
            candidates.append(
                (
                    float(
                        two_lane_row["first_contact_witness"][
                            "absolute_vertical_normal_component"
                        ]
                    ),
                    1,
                    "two_lane_v6",
                    two_lane_row,
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        normal, _, candidate_id, row = candidates[0]
        source_path = _bound(
            {
                "path": row["action_path"],
                "sha256": row["action_sha256"],
            }
        )
        destination = action_directory / f"{index:02d}.f64le"
        destination.write_bytes(source_path.read_bytes())
        selected.append(
            {
                "case_id": row["case_id"],
                "direction": row["direction"],
                "source_square": row["source_square"],
                "destination_square": row["destination_square"],
                "selected_piece_id": row["selected_piece_id"],
                "selected_candidate": candidate_id,
                "selection_metric": {
                    "absolute_first_contact_vertical_normal_component": normal
                },
                "candidate_metrics": {
                    candidate[2]: candidate[0] for candidate in candidates
                },
                "action_path": str(destination.relative_to(REPO_ROOT)),
                "action_sha256": _sha(destination),
                "action_shape": row["action_shape"],
            }
        )
    counts = {
        direction: sum(row["direction"] == direction for row in selected)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = len(selected) == 4 and counts == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    receipt = {
        "schema_version": (
            "sim2claw.canonical_wrist_path_static_selector_receipt.v1"
        ),
        "status": (
            "four_family_static_selector_pass"
            if passed
            else "four_family_static_selector_reject"
        ),
        "proof_class": "static_only_frozen_action_candidate_selection",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "selected": selected,
        "direction_counts": counts,
        "passed": passed,
        "dynamic_outcomes_used": False,
        "dynamic_simulation": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalWristPathStaticSelectorError",
    "select_and_freeze",
]
