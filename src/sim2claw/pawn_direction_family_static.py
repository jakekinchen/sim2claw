"""Finite low-contact pawn-by-direction static successor for RP04J."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_elbow_locked_low_path_static as _low
from . import canonical_elbow_locked_wrist_path_static as _elbow
from . import canonical_seeded_action_static as _static
from . import canonical_wrist_path_static as _wrist
from .current_workcell import current_square_center
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class PawnDirectionFamilyStaticError(RuntimeError):
    """The frozen pawn-by-direction successor failed closed."""


NEAR_SIDE_SQUARES = ("a2", "b1", "c2", "d1", "e2", "f1", "g2", "h1")
BEARINGS_DEGREES = tuple(range(0, 360, 45))
CARRY_SOURCE_SQUARE = "f1"
CARRY_BEARING_DEGREES = 90
DESTINATION_PREFIX = "bearing__"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise PawnDirectionFamilyStaticError(
            "pawn-direction input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise PawnDirectionFamilyStaticError(
            f"bound pawn-direction input changed: {path}"
        )
    return path


def _destination_name(source_square: str, bearing_degrees: int) -> str:
    return f"{DESTINATION_PREFIX}{source_square}__{bearing_degrees:03d}"


def _parse_destination(name: str) -> tuple[str, int]:
    if not name.startswith(DESTINATION_PREFIX):
        raise PawnDirectionFamilyStaticError(
            f"unexpected synthetic destination: {name}"
        )
    payload = name[len(DESTINATION_PREFIX) :]
    source, bearing = payload.split("__", maxsplit=1)
    degrees = int(bearing)
    if source not in NEAR_SIDE_SQUARES or degrees not in BEARINGS_DEGREES:
        raise PawnDirectionFamilyStaticError(
            f"invalid synthetic destination: {name}"
        )
    return source, degrees


def _bearing_world_unit(bearing_degrees: int) -> np.ndarray:
    origin = np.asarray(current_square_center("a1"), dtype=np.float64)
    file_axis = np.asarray(
        current_square_center("b1"), dtype=np.float64
    ) - origin
    rank_axis = np.asarray(
        current_square_center("a2"), dtype=np.float64
    ) - origin
    file_axis /= np.linalg.norm(file_axis)
    rank_axis /= np.linalg.norm(rank_axis)
    angle = math.radians(bearing_degrees)
    return (math.cos(angle) * file_axis) + (
        math.sin(angle) * rank_axis
    )


def _synthetic_square_center(square: str) -> tuple[float, float, float]:
    if not square.startswith(DESTINATION_PREFIX):
        return current_square_center(square)
    source, bearing = _parse_destination(square)
    origin = np.asarray(current_square_center(source), dtype=np.float64)
    destination = origin + _bearing_world_unit(bearing)
    return tuple(float(value) for value in destination)


def _direction_families(model: mujoco.MjModel) -> list[dict[str, str]]:
    occupied: dict[str, str] = {}
    for body_id in range(model.nbody):
        name = _static._body_name(model, body_id)
        if "_pawn_" in name:
            occupied[name.rsplit("_", 1)[-1]] = name
    if any(square not in occupied for square in NEAR_SIDE_SQUARES):
        raise PawnDirectionFamilyStaticError(
            "near-side pawn inventory changed"
        )
    families: list[dict[str, str]] = []
    for source in NEAR_SIDE_SQUARES:
        piece_id = occupied[source]
        for bearing in BEARINGS_DEGREES:
            if (
                source == CARRY_SOURCE_SQUARE
                and bearing == CARRY_BEARING_DEGREES
            ):
                continue
            destination = _destination_name(source, bearing)
            families.append(
                {
                    "case_id": f"{piece_id}__{source}_bearing_{bearing:03d}",
                    "selected_piece_id": piece_id,
                    "source_square": source,
                    "destination_square": destination,
                }
            )
    if len(families) != 63:
        raise PawnDirectionFamilyStaticError(
            "pawn-direction family count changed"
        )
    return families


def _point_segment_distance(
    point: np.ndarray, first: np.ndarray, second: np.ndarray
) -> float:
    delta = second - first
    denominator = float(delta @ delta)
    if denominator <= 0.0:
        return float(np.linalg.norm(point - first))
    blend = float(np.clip(((point - first) @ delta) / denominator, 0.0, 1.0))
    return float(np.linalg.norm(point - (first + blend * delta)))


def _segment_distance(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> float:
    return min(
        _point_segment_distance(first_start, second_start, second_end),
        _point_segment_distance(first_end, second_start, second_end),
        _point_segment_distance(second_start, first_start, first_end),
        _point_segment_distance(second_end, first_start, first_end),
    )


def _canonical_xy(square: str, square_side_m: float) -> np.ndarray:
    file_index = ord(square[0]) - ord("a")
    rank_index = int(square[1]) - 1
    return np.asarray(
        [
            (file_index - 3.5) * square_side_m,
            (rank_index - 3.5) * square_side_m,
        ],
        dtype=np.float64,
    )


def _corridor_gate(
    *,
    source_square: str,
    bearing_degrees: int,
    stroke_m: float,
    square_side_m: float,
    pawn_radius_m: float,
    minimum_corridor_separation_m: float,
) -> dict[str, Any]:
    source = _canonical_xy(source_square, square_side_m)
    angle = math.radians(bearing_degrees)
    endpoint = source + stroke_m * np.asarray(
        [math.cos(angle), math.sin(angle)], dtype=np.float64
    )
    board_half = 4.0 * square_side_m
    endpoint_inside_board = bool(
        np.all(np.abs(endpoint) + pawn_radius_m <= board_half + 1e-12)
    )
    carry_start = _canonical_xy(CARRY_SOURCE_SQUARE, square_side_m)
    carry_end = carry_start + stroke_m * np.asarray(
        [0.0, 1.0], dtype=np.float64
    )
    separation = _segment_distance(source, endpoint, carry_start, carry_end)
    disjoint_from_carry = bool(
        source_square != CARRY_SOURCE_SQUARE
        and separation >= minimum_corridor_separation_m
    )
    return {
        "source_xy_m": source.tolist(),
        "endpoint_xy_m": endpoint.tolist(),
        "endpoint_inside_board": endpoint_inside_board,
        "carry_corridor_separation_m": separation,
        "minimum_corridor_separation_m": minimum_corridor_separation_m,
        "disjoint_pawn": source_square != CARRY_SOURCE_SQUARE,
        "disjoint_from_carry": disjoint_from_carry,
        "passed": endpoint_inside_board and disjoint_from_carry,
    }


def enumerate_and_freeze(
    contract_path: Path, output_directory: Path
) -> dict[str, Any]:
    """Run the prospectively frozen pawn-by-direction grid exactly once."""

    if output_directory.exists():
        raise PawnDirectionFamilyStaticError(
            "immutable pawn-direction output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "predecessor_closeout",
        "carry_static_receipt",
        "implementation",
        "grid",
        "geometry_gates",
        "live_seed",
        "unchanged",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.pawn_direction_family_static.v1"
        or contract.get("status")
        != "frozen_before_pawn_direction_static_enumeration"
        or not all(contract["unchanged"].values())
        or contract["authority"]
        != {
            "model_loading": True,
            "static_simulation": True,
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
    ):
        raise PawnDirectionFamilyStaticError(
            "pawn-direction successor widened its contract"
        )
    for key in (
        "base_contract",
        "predecessor_closeout",
        "carry_static_receipt",
        "implementation",
    ):
        _bound(contract[key])
    if (
        tuple(contract["grid"]["near_side_squares"]) != NEAR_SIDE_SQUARES
        or tuple(contract["grid"]["bearings_degrees"])
        != BEARINGS_DEGREES
        or contract["grid"]["contact_heights_m"]
        != [0.0225, 0.025, 0.0275, 0.03]
        or int(contract["grid"]["new_family_count"]) != 63
        or int(contract["grid"]["new_cell_count"]) != 756
    ):
        raise PawnDirectionFamilyStaticError(
            "pawn-direction finite grid changed"
        )

    base = json.loads(
        _bound(contract["base_contract"]).read_text(encoding="utf-8")
    )
    carry_receipt = json.loads(
        _bound(contract["carry_static_receipt"]).read_text(encoding="utf-8")
    )
    carry_candidates = [
        copy.deepcopy(row)
        for row in carry_receipt["selected"]
        if row["case_id"] == contract["grid"]["carry_case_id"]
        and row["action_sha256"] == contract["grid"]["carry_action_sha256"]
    ]
    if len(carry_candidates) != 1:
        raise PawnDirectionFamilyStaticError(
            "exact carried survivor is unavailable"
        )
    carry = carry_candidates[0]
    carry_action = REPO_ROOT / carry["action_path"]
    if _sha(carry_action) != contract["grid"]["carry_action_sha256"]:
        raise PawnDirectionFamilyStaticError(
            "carried survivor action bytes changed"
        )

    resolved = copy.deepcopy(base)
    manifest_path = _bound(resolved["inputs"]["candidate_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    follower = np.asarray(
        [contract["live_seed"]["follower_position_degrees"]],
        dtype=np.float64,
    )
    model_seed = _physical_to_model_position(
        follower, manifest["candidate_config"]
    )[0]
    resolved["live_seed"]["follower_position_degrees"] = follower[0].tolist()
    resolved["live_seed"]["model_radians"] = model_seed.tolist()
    resolved["quarantine"] = {
        "case_ids": [],
        "exact_count": 0,
        "reason": "the exact carried f1-to-f2 family is omitted by the prospective direction-family generator; historical quarantines remain bound in the public contract",
    }
    resolved["family_universe"] = {
        "source": "eight near-side pawns by eight 45-degree displacement bearings, excluding the exact carried f1-to-f2 survivor",
        "prequarantine_count": 63,
        "expected_postquarantine_count": 63,
        "reset_layout_changed": False,
        "grid_expansion_after_result": False,
    }
    resolved["grid"]["contact_heights_m"] = list(
        contract["grid"]["contact_heights_m"]
    )
    resolved["grid"]["cells_per_family"] = 12
    resolved["grid"]["maximum_total_cells"] = 756
    resolved["selection"]["selected_count"] = 63
    resolved["selection"]["minimum_per_direction"] = 1
    resolved["output_directory"] = str(
        (output_directory / "enumeration").relative_to(REPO_ROOT)
    )
    resolved["claim_boundary"] = contract["claim_boundary"]

    minimum_contact_height = float(
        resolved["gates"]["minimum_first_contact_height_m"]
    )
    original_compile = _wrist._compile
    original_witness = _wrist._first_contact_witness
    original_solver = _static._solve_fixed_roll
    original_families = _static._families
    original_square_center = _wrist.current_square_center

    def witness_with_minimum(**kwargs: Any) -> dict[str, Any]:
        witness = original_witness(**kwargs)
        observed_height = witness.get(
            "contact_height_relative_initial_pawn_root_m"
        )
        witness["minimum_required_contact_height_m"] = minimum_contact_height
        witness["above_minimum_contact_height"] = bool(
            witness.get("observed")
            and observed_height is not None
            and float(observed_height) >= minimum_contact_height
        )
        if witness.get("observed") and not witness[
            "above_minimum_contact_height"
        ]:
            witness["observed"] = False
        return witness

    temporary_path: Path | None = None
    enumeration_directory = output_directory / "enumeration"
    try:
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="pawn-direction-resolved-",
            dir=output_directory.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(resolved, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_path = Path(handle.name)
        _wrist._compile = _low._compile_low_direct
        _wrist._first_contact_witness = witness_with_minimum
        _static._solve_fixed_roll = _elbow._locked_elbow_solver
        _static._families = _direction_families
        _wrist.current_square_center = _synthetic_square_center
        enumeration = _wrist.enumerate_and_freeze(
            temporary_path.resolve(), enumeration_directory.resolve()
        )
    finally:
        _wrist._compile = original_compile
        _wrist._first_contact_witness = original_witness
        _static._solve_fixed_roll = original_solver
        _static._families = original_families
        _wrist.current_square_center = original_square_center
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    square_side = float(contract["geometry_gates"]["square_side_m"])
    pawn_radius = float(contract["geometry_gates"]["pawn_base_radius_m"])
    separation = float(
        contract["geometry_gates"]["minimum_corridor_separation_m"]
    )
    new_candidates: list[dict[str, Any]] = []
    for row in enumeration["selected"]:
        _, bearing = _parse_destination(row["destination_square"])
        corridor = _corridor_gate(
            source_square=row["source_square"],
            bearing_degrees=bearing,
            stroke_m=float(contract["grid"]["stroke_m"]),
            square_side_m=square_side,
            pawn_radius_m=pawn_radius,
            minimum_corridor_separation_m=separation,
        )
        candidate = copy.deepcopy(row)
        candidate["bearing_degrees"] = bearing
        candidate["corridor"] = corridor
        if corridor["passed"]:
            new_candidates.append(candidate)
    new_selected = new_candidates[:1]
    selected: list[dict[str, Any]] = []
    carry["direction"] = "REAL_TO_SIM"
    carry["carried_byte_identical"] = True
    selected.append(carry)
    if new_selected:
        new_selected[0]["direction"] = "SIM_TO_REAL"
        new_selected[0]["carried_byte_identical"] = False
        selected.append(new_selected[0])
    counts = {
        direction: sum(row["direction"] == direction for row in selected)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = bool(
        len(selected) == 2
        and selected[0]["selected_piece_id"]
        != selected[1]["selected_piece_id"]
        and counts == {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
    )
    receipt = {
        "schema_version": "sim2claw.pawn_direction_family_static_receipt.v1",
        "status": (
            "pawn_direction_family_static_pass"
            if passed
            else "pawn_direction_family_static_reject"
        ),
        "proof_class": (
            "cpu_fp64_reachable_80deg_low_contact_pawn_direction_static"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "grid_result_count": enumeration["grid_result_count"],
        "new_statically_eligible_family_count": (
            enumeration["statically_eligible_family_count"]
        ),
        "new_corridor_eligible_family_count": len(new_candidates),
        "selected": selected,
        "direction_counts": counts,
        "passed": passed,
        "enumeration_receipt": {
            "path": str(
                (enumeration_directory / "receipt.json").relative_to(REPO_ROOT)
            ),
            "sha256": _sha(enumeration_directory / "receipt.json"),
        },
        "dynamic_replay_executed": False,
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
    "BEARINGS_DEGREES",
    "NEAR_SIDE_SQUARES",
    "PawnDirectionFamilyStaticError",
    "_corridor_gate",
    "_destination_name",
    "_parse_destination",
    "enumerate_and_freeze",
]
