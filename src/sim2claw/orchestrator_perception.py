"""Deterministic square-level occupancy for the frozen B--G base case."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np


BASE_STATE_SCHEMA = "sim2claw.orchestrator_base_state.v1"


@dataclass(frozen=True)
class BaseCaseContract:
    contract_id: str
    managed_files: tuple[str, ...]
    managed_ranks: tuple[int, ...]
    required_occupied: frozenset[str]
    required_empty: frozenset[str]
    payload: dict[str, Any]

    @property
    def managed_squares(self) -> tuple[str, ...]:
        return tuple(
            f"{file_name}{rank}"
            for file_name in self.managed_files
            for rank in self.managed_ranks
        )


def load_base_case_contract(path: Path) -> BaseCaseContract:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "sim2claw.orchestrator_base_case.v1":
        raise ValueError("unexpected orchestrator base-case schema")
    managed = payload["managed_region"]
    files = tuple(str(value).casefold() for value in managed["files"])
    ranks = tuple(int(value) for value in managed["ranks"])
    required_occupied = frozenset(
        str(value).casefold() for value in payload["required_occupied"]
    )
    required_empty = frozenset(
        str(value).casefold() for value in payload["required_empty"]
    )
    expected = {f"{file_name}{rank}" for file_name in files for rank in ranks}
    if files != ("b", "c", "d", "e", "f", "g") or ranks != (1, 2):
        raise ValueError("base-case managed region is not the frozen B--G rank-1/rank-2 set")
    if required_occupied != {"b1", "c2", "d1", "e2", "f1", "g2"}:
        raise ValueError("base-case required occupancy changed")
    if required_occupied | required_empty != expected or required_occupied & required_empty:
        raise ValueError("base-case occupied/empty partition is incomplete")
    return BaseCaseContract(
        contract_id=str(payload["contract_id"]),
        managed_files=files,
        managed_ranks=ranks,
        required_occupied=required_occupied,
        required_empty=required_empty,
        payload=payload,
    )


class RegisteredSquareOccupancyClassifier:
    """Classify each managed square independently from a rectified RGB board."""

    def __init__(
        self,
        contract: BaseCaseContract,
        perception_config: Mapping[str, Any],
    ) -> None:
        self.contract = contract
        self.config = dict(perception_config)
        self.occupied_minimum = float(self.config["occupied_ratio_minimum"])
        self.empty_maximum = float(self.config["empty_ratio_maximum"])
        self.minimum_confidence = float(self.config["minimum_square_confidence"])
        if not 0 <= self.empty_maximum < self.occupied_minimum <= 1:
            raise ValueError("invalid occupancy ratio thresholds")

    @staticmethod
    def _square_bounds(
        square: str, width: int, height: int, margin_fraction: float
    ) -> tuple[int, int, int, int]:
        file_index = ord(square[0]) - ord("a")
        rank = int(square[1])
        x0 = file_index * width / 8.0
        x1 = (file_index + 1) * width / 8.0
        y0 = (8 - rank) * height / 8.0
        y1 = (9 - rank) * height / 8.0
        margin_x = (x1 - x0) * margin_fraction
        margin_y = (y1 - y0) * margin_fraction
        return (
            int(round(x0 + margin_x)),
            int(round(y0 + margin_y)),
            int(round(x1 - margin_x)),
            int(round(y1 - margin_y)),
        )

    def classify(self, image_bgr: np.ndarray, *, evidence_frame_sha256: str) -> dict[str, Any]:
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("base-case classifier requires a BGR image")
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        lower = np.asarray(self.config["brown_hsv_lower"], dtype=np.uint8)
        upper = np.asarray(self.config["brown_hsv_upper"], dtype=np.uint8)
        brown_mask = cv2.inRange(hsv, lower, upper) > 0
        saturation = hsv[:, :, 1]
        margin = float(self.config["square_inner_margin_fraction"])
        height, width = image_bgr.shape[:2]
        squares: dict[str, dict[str, Any]] = {}
        observed_occupied: list[str] = []
        observed_empty: list[str] = []
        blockers: list[dict[str, Any]] = []

        for square in self.contract.managed_squares:
            x0, y0, x1, y1 = self._square_bounds(square, width, height, margin)
            crop_mask = brown_mask[y0:y1, x0:x1]
            crop_saturation = saturation[y0:y1, x0:x1]
            if crop_mask.size == 0:
                raise ValueError(f"managed-square crop is empty: {square}")
            brown_ratio = float(crop_mask.mean())
            colored_non_brown_ratio = float(
                np.logical_and(crop_saturation > 85, np.logical_not(crop_mask)).mean()
            )
            if colored_non_brown_ratio >= 0.30:
                status = "obstructed"
                confidence = 1.0
                blockers.append({"kind": "obstruction", "square": square})
            elif brown_ratio >= self.occupied_minimum:
                status = "occupied"
                confidence = min(1.0, brown_ratio / self.occupied_minimum)
                observed_occupied.append(square)
            elif brown_ratio <= self.empty_maximum:
                status = "empty"
                confidence = min(
                    1.0,
                    max(0.0, (self.occupied_minimum - brown_ratio) / self.occupied_minimum),
                )
                observed_empty.append(square)
            else:
                status = "uncertain"
                midpoint = (self.occupied_minimum + self.empty_maximum) / 2.0
                half_gap = (self.occupied_minimum - self.empty_maximum) / 2.0
                confidence = max(0.0, abs(brown_ratio - midpoint) / max(half_gap, 1e-9))
                blockers.append({"kind": "uncertain_occupancy", "square": square})
            confidence = round(float(confidence), 6)
            if confidence < self.minimum_confidence and status in {"empty", "occupied"}:
                blockers.append(
                    {"kind": "low_confidence", "square": square, "confidence": confidence}
                )
            squares[square] = {
                "status": status,
                "brown_ratio": round(brown_ratio, 6),
                "colored_non_brown_ratio": round(colored_non_brown_ratio, 6),
                "confidence": confidence,
            }

        mismatched_files: list[str] = []
        suggested_moves: list[dict[str, Any]] = []
        for file_name in self.contract.managed_files:
            pair = [f"{file_name}1", f"{file_name}2"]
            if any(squares[square]["status"] in {"uncertain", "obstructed"} for square in pair):
                continue
            occupied = [square for square in pair if squares[square]["status"] == "occupied"]
            if len(occupied) == 0:
                blockers.append({"kind": "missing_pawn", "file": file_name})
                continue
            if len(occupied) == 2:
                blockers.append({"kind": "two_pawns_in_file", "file": file_name})
                continue
            current = occupied[0]
            required = next(
                square for square in pair if square in self.contract.required_occupied
            )
            if current != required:
                mismatched_files.append(file_name)
                suggested_moves.append(
                    {
                        "skill_id": f"pawn_{current}_to_{required}",
                        "source_square": current,
                        "destination_square": required,
                        "expected_postcondition": {
                            "occupied": [required],
                            "empty": [current],
                        },
                    }
                )

        confidences = [float(row["confidence"]) for row in squares.values()]
        confidence = round(min(confidences) if confidences else 0.0, 6)
        observed_set = set(observed_occupied)
        deterministic_match = (
            not blockers
            and observed_set == set(self.contract.required_occupied)
            and set(observed_empty) == set(self.contract.required_empty)
            and confidence >= self.minimum_confidence
        )
        if deterministic_match:
            state = "base_case"
        elif blockers:
            state = "blocked"
        else:
            state = "restorable"
        return {
            "schema_version": BASE_STATE_SCHEMA,
            "contract_id": self.contract.contract_id,
            "state": state,
            "deterministic_complete": deterministic_match,
            "required_occupied": sorted(self.contract.required_occupied),
            "required_empty": sorted(self.contract.required_empty),
            "observed_occupied": sorted(observed_occupied),
            "observed_empty": sorted(observed_empty),
            "mismatched_files": mismatched_files,
            "confidence": confidence,
            "minimum_confidence": self.minimum_confidence,
            "evidence_frame_sha256": evidence_frame_sha256,
            "squares": squares,
            "blockers": blockers,
            "suggested_moves": suggested_moves,
            "comparison_authority": "square_level_occupancy_not_frame_similarity",
            "physical_authority": False,
        }


def verify_expected_postcondition(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    expected_occupied = {str(value) for value in expected.get("occupied", [])}
    expected_empty = {str(value) for value in expected.get("empty", [])}
    after_occupied = set(after.get("observed_occupied", []))
    after_empty = set(after.get("observed_empty", []))
    changed = {
        square
        for square in set(before.get("squares", {})) | set(after.get("squares", {}))
        if (before.get("squares", {}).get(square) or {}).get("status")
        != (after.get("squares", {}).get(square) or {}).get("status")
    }
    allowed_changed = expected_occupied | expected_empty
    passed = (
        expected_occupied <= after_occupied
        and expected_empty <= after_empty
        and changed <= allowed_changed
        and not after.get("blockers")
    )
    return {
        "passed": passed,
        "expected_occupied": sorted(expected_occupied),
        "expected_empty": sorted(expected_empty),
        "observed_changed_squares": sorted(changed),
        "unexpected_changed_squares": sorted(changed - allowed_changed),
        "evidence_frame_sha256": after.get("evidence_frame_sha256"),
        "physical_authority": False,
    }
