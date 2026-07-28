"""Prospective current-task wiring for exact V05 static implementations.

Frozen V05-T and paused V05-UG implementation bytes remain reproducible.
Only new contracts that explicitly bind the current-task scene/label contract
may enter these adapters.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import mujoco

from . import bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1 as _ug
from . import bidirectional_pawn_push_v2_orientation_funnel_static_v1 as _ug_terminal
from . import bidirectional_pawn_push_v2_temporal_static as _temporal
from .bidirectional_pawn_push_v2_scene_labels import (
    CONTRACT_PATH,
    RAW_GRID_TRANSFORM,
    assert_compiled_reset_layout_alignment,
    current_task_square_center,
    load_scene_label_contract,
)
from .paths import REPO_ROOT


class CurrentTaskStaticV1Error(RuntimeError):
    """A prospective static contract did not bind the current task."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_scene_label_binding(contract_path: Path) -> None:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    binding = contract.get("current_task_scene_labels")
    if not isinstance(binding, Mapping):
        raise CurrentTaskStaticV1Error(
            "prospective static contract lacks current_task_scene_labels"
        )
    path = (REPO_ROOT / str(binding.get("path", ""))).resolve()
    if path != CONTRACT_PATH.resolve():
        raise CurrentTaskStaticV1Error("unexpected current-task scene-label path")
    if not path.is_file() or _sha(path) != binding.get("sha256"):
        raise CurrentTaskStaticV1Error("current-task scene-label binding changed")
    load_scene_label_contract(path)


def _piece_layout(model: mujoco.MjModel) -> dict[str, str]:
    pieces: dict[str, str] = {}
    for body_id in range(model.nbody):
        name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            or ""
        )
        if "_pawn_" not in name:
            continue
        square = name.rsplit("_", 1)[-1]
        if square in pieces:
            raise CurrentTaskStaticV1Error(f"duplicate pawn square: {square}")
        pieces[square] = name
    return pieces


def _execute_with_current_task_wiring(
    *,
    contract_path: Path,
    output_directory: Path,
    enumerator: Callable[[Path, Path], dict[str, Any]],
    target_module: Any,
) -> dict[str, Any]:
    public_contract = (
        contract_path.resolve()
        if contract_path.is_absolute()
        else (REPO_ROOT / contract_path).resolve()
    )
    _verify_scene_label_binding(public_contract)

    original_registered_model = target_module._rehearsal._registered_model
    original_square_center = target_module.board_square_center

    def registered_current_task_model(
        wrapper: Mapping[str, Any],
        rigid: Mapping[str, Any],
        timestep: float,
    ) -> tuple[mujoco.MjModel, list[int], list[int], set[int]]:
        model, qpos, actuators, jaw_bodies = original_registered_model(
            wrapper,
            rigid,
            timestep,
            piece_square_transform=RAW_GRID_TRANSFORM,
        )
        initial = mujoco.MjData(model)
        mujoco.mj_forward(model, initial)
        assert_compiled_reset_layout_alignment(
            model,
            initial,
            _piece_layout(model),
        )
        return model, qpos, actuators, jaw_bodies

    def canonical_center(square: str, **_: object) -> tuple[float, float, float]:
        return tuple(float(value) for value in current_task_square_center(square))

    target_module._rehearsal._registered_model = registered_current_task_model
    target_module.board_square_center = canonical_center
    try:
        receipt = enumerator(public_contract, output_directory)
    finally:
        target_module._rehearsal._registered_model = original_registered_model
        target_module.board_square_center = original_square_center
    receipt["current_task_scene_labels"] = {
        "path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "sha256": _sha(CONTRACT_PATH),
        "raw_grid_transform": RAW_GRID_TRANSFORM,
        "canonical_target_resolver": (
            "sim2claw.board_orientation.canonical_square_center"
        ),
        "compiled_reset_layout_invariant_checked": True,
    }
    return receipt


def enumerate_temporal_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run a new V05 temporal-static contract in the canonical task frame."""

    return _execute_with_current_task_wiring(
        contract_path=contract_path,
        output_directory=output_directory,
        enumerator=_temporal.enumerate_and_freeze,
        target_module=_temporal,
    )


def enumerate_low_planar_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run a new successor of paused V05-UG through its terminal static path."""

    return _execute_with_current_task_wiring(
        contract_path=contract_path,
        output_directory=output_directory,
        enumerator=_ug.enumerate_and_freeze,
        target_module=_ug_terminal,
    )
