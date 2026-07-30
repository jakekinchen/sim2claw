"""Exact named jaw-pad to pawn geometry measurements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import mujoco
import numpy as np


class NamedJawContactError(ValueError):
    """The requested named collision geometry is missing or ambiguous."""


def _name(model: mujoco.MjModel, object_type: mujoco.mjtObj, index: int) -> str:
    return (
        mujoco.mj_id2name(model, object_type, index)
        or f"unnamed_{object_type}_{index}"
    )


def _ids_by_prefix(model: mujoco.MjModel, prefix: str) -> tuple[int, ...]:
    return tuple(
        geom_id
        for geom_id in range(model.ngeom)
        if _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id).startswith(prefix)
        and int(model.geom_contype[geom_id]) != 0
    )


def _ids_by_name(
    model: mujoco.MjModel,
    names: Iterable[str],
) -> tuple[int, ...]:
    ids = tuple(
        int(
            mujoco.mj_name2id(
                model,
                mujoco.mjtObj.mjOBJ_GEOM,
                name,
            )
        )
        for name in names
    )
    if not ids or min(ids) < 0:
        raise NamedJawContactError(f"named jaw tip geoms are missing: {list(names)}")
    return ids


@dataclass(frozen=True)
class NamedContactGeometry:
    selected_body_id: int
    pawn_geom_ids: tuple[int, ...]
    fixed_jaw_geom_ids: tuple[int, ...]
    moving_jaw_geom_ids: tuple[int, ...]
    fixed_tip_geom_ids: tuple[int, ...]
    moving_tip_geom_ids: tuple[int, ...]


def resolve_named_contact_geometry(
    model: mujoco.MjModel,
    *,
    selected_body_name: str,
    fixed_jaw_prefix: str,
    moving_jaw_prefix: str,
    fixed_tip_names: Iterable[str],
    moving_tip_names: Iterable[str],
) -> NamedContactGeometry:
    selected_body = int(
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            selected_body_name,
        )
    )
    if selected_body < 0:
        raise NamedJawContactError("selected pawn body is missing")
    pawn_geoms = tuple(
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) == selected_body
        and int(model.geom_contype[geom_id]) != 0
    )
    if not pawn_geoms:
        raise NamedJawContactError("selected pawn collision geoms are missing")
    fixed = _ids_by_prefix(model, fixed_jaw_prefix)
    moving = _ids_by_prefix(model, moving_jaw_prefix)
    if not fixed:
        raise NamedJawContactError("fixed jaw collision geoms are missing")
    if not moving:
        raise NamedJawContactError("moving jaw collision geoms are missing")
    return NamedContactGeometry(
        selected_body_id=selected_body,
        pawn_geom_ids=pawn_geoms,
        fixed_jaw_geom_ids=fixed,
        moving_jaw_geom_ids=moving,
        fixed_tip_geom_ids=_ids_by_name(model, fixed_tip_names),
        moving_tip_geom_ids=_ids_by_name(model, moving_tip_names),
    )


def _minimum_group_distance(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    jaw_ids: Iterable[int],
    pawn_ids: Iterable[int],
    *,
    distance_maximum_m: float,
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for jaw_id in jaw_ids:
        for pawn_id in pawn_ids:
            fromto = np.zeros(6, dtype=np.float64)
            distance = float(
                mujoco.mj_geomDistance(
                    model,
                    data,
                    jaw_id,
                    pawn_id,
                    distance_maximum_m,
                    fromto,
                )
            )
            if best is None or distance < best["signed_distance_m"]:
                best = {
                    "signed_distance_m": distance,
                    "jaw_geom": _name(
                        model, mujoco.mjtObj.mjOBJ_GEOM, jaw_id
                    ),
                    "pawn_geom": _name(
                        model, mujoco.mjtObj.mjOBJ_GEOM, pawn_id
                    ),
                    "nearest_point_on_jaw_m": fromto[:3].astype(float).tolist(),
                    "nearest_point_on_pawn_m": fromto[3:].astype(float).tolist(),
                }
    if best is None:
        raise NamedJawContactError("no named jaw-pawn pair was evaluated")
    return best


def measure_named_jaw_contact(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    geometry: NamedContactGeometry,
    *,
    distance_maximum_m: float,
    other_pad_tolerance_m: float,
) -> dict[str, Any]:
    fixed = _minimum_group_distance(
        model,
        data,
        geometry.fixed_jaw_geom_ids,
        geometry.pawn_geom_ids,
        distance_maximum_m=distance_maximum_m,
    )
    moving = _minimum_group_distance(
        model,
        data,
        geometry.moving_jaw_geom_ids,
        geometry.pawn_geom_ids,
        distance_maximum_m=distance_maximum_m,
    )
    fixed_center = np.mean(data.geom_xpos[list(geometry.fixed_tip_geom_ids)], axis=0)
    moving_center = np.mean(
        data.geom_xpos[list(geometry.moving_tip_geom_ids)], axis=0
    )
    pawn_center = np.asarray(
        data.xpos[geometry.selected_body_id],
        dtype=np.float64,
    )
    closing_axis = moving_center - fixed_center
    squared_span = float(closing_axis @ closing_axis)
    fraction = (
        float((pawn_center - fixed_center) @ closing_axis / squared_span)
        if squared_span > 0.0
        else float("nan")
    )
    bracketed = bool(np.isfinite(fraction) and 0.0 <= fraction <= 1.0)
    bilateral = bool(
        (
            fixed["signed_distance_m"] <= 0.0
            and moving["signed_distance_m"] <= other_pad_tolerance_m
        )
        or (
            moving["signed_distance_m"] <= 0.0
            and fixed["signed_distance_m"] <= other_pad_tolerance_m
        )
    )
    intended_ids = set(geometry.fixed_jaw_geom_ids) | set(
        geometry.moving_jaw_geom_ids
    )
    pawn_ids = set(geometry.pawn_geom_ids)
    unrelated: set[tuple[str, str]] = set()
    exact_pairs: set[tuple[str, str]] = set()
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        geom1 = int(contact.geom1)
        geom2 = int(contact.geom2)
        if geom1 not in pawn_ids and geom2 not in pawn_ids:
            continue
        pair = tuple(
            sorted(
                (
                    _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom1),
                    _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom2),
                )
            )
        )
        other = geom2 if geom1 in pawn_ids else geom1
        if other in intended_ids:
            exact_pairs.add(pair)
        else:
            unrelated.add(pair)
    return {
        "fixed": fixed,
        "moving": moving,
        "fixed_tip_center_m": fixed_center.astype(float).tolist(),
        "moving_tip_center_m": moving_center.astype(float).tolist(),
        "pawn_center_m": pawn_center.astype(float).tolist(),
        "pawn_center_closing_axis_fraction": fraction,
        "pawn_center_bracketed": bracketed,
        "bilateral_contact_tolerance_pass": bilateral,
        "phase_contact_geometry_pass": bool(bilateral and bracketed),
        "exact_named_contact_pairs": [list(pair) for pair in sorted(exact_pairs)],
        "unrelated_pawn_contact_pairs": [
            list(pair) for pair in sorted(unrelated)
        ],
    }


__all__ = [
    "NamedContactGeometry",
    "NamedJawContactError",
    "measure_named_jaw_contact",
    "resolve_named_contact_geometry",
]
