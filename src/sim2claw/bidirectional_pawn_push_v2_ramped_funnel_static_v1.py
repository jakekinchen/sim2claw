"""V05-UE ramped-fingertip guiding-contact static wrapper."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import bidirectional_pawn_push_v2_multistart_approach_static as _multi
from . import bidirectional_pawn_push_v2_seeded_funnel_static_v1 as _base
from .paths import REPO_ROOT


RampedFunnelStaticV1Error = _base.SeededFunnelStaticV1Error


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise RampedFunnelStaticV1Error(
            "V05-UE path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise RampedFunnelStaticV1Error(
            f"bound V05-UE input changed: {path}"
        )
    return path


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_ramped_funnel_static.v1"
    ):
        raise RampedFunnelStaticV1Error(
            "unexpected V05-UE static contract"
        )
    authorization_path = _verify(contract["authorization"])
    base_contract_path = _verify(contract["base_static_contract"])
    _verify(contract["v05_ud_static_receipt"])
    _verify(contract["base_implementation"])
    _verify(contract["multistart_implementation"])
    _verify(contract["implementation"])
    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    base = json.loads(base_contract_path.read_text(encoding="utf-8"))
    overrides = contract["frozen_overrides"]
    if (
        authorization["quarantine"]["case_ids"]
        != base["frozen_overrides"]["quarantine_case_ids"]
    ):
        raise RampedFunnelStaticV1Error(
            "V05-UE quarantine binding changed"
        )
    if int(overrides["maximum_total_cells"]) != 576:
        raise RampedFunnelStaticV1Error("V05-UE cell budget changed")

    derived = copy.deepcopy(base)
    derived.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-ramped-funnel-static-derived-v1"
            ),
            "status": (
                "prospectively_derived_from_frozen_v05_ud_before_model_loading"
            ),
            "authorization": contract["authorization"],
        }
    )
    derived["frozen_overrides"]["path_shape"] = overrides["path_shape"]
    derived["implementation"] = contract["base_implementation"]

    public_output.mkdir(parents=True, exist_ok=True)
    derived_path = public_output / "derived_contract.json"
    derived_path.write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    original_compile = _multi._compile_action

    def ramped_compile(
        *,
        cartesian_waypoints: list[np.ndarray],
        **kwargs: Any,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if len(cartesian_waypoints) != 4:
            raise RampedFunnelStaticV1Error(
                "V05-UE expected four guiding waypoints"
            )
        overhead, guide, contact, terminal = [
            np.asarray(row, dtype=np.float64).copy()
            for row in cartesian_waypoints
        ]
        planar = terminal - contact
        planar[2] = 0.0
        stroke = float(np.linalg.norm(planar))
        if stroke <= 0.0:
            raise RampedFunnelStaticV1Error("V05-UE planar stroke changed")
        direction = planar / stroke
        engagement = contact + direction * float(
            overrides["level_engagement_m"]
        )
        ramp_end = contact + direction * float(
            overrides["ramp_end_planar_progress_m"]
        )
        ramp_end[2] += float(overrides["ramp_rise_m"])
        lifted_terminal = terminal.copy()
        lifted_terminal[2] += float(overrides["ramp_rise_m"])
        action, metrics = original_compile(
            cartesian_waypoints=[
                overhead,
                guide,
                contact,
                engagement,
                ramp_end,
                lifted_terminal,
            ],
            **kwargs,
        )
        metrics["ramped_fingertip_path"] = {
            "level_engagement_m": overrides["level_engagement_m"],
            "ramp_end_planar_progress_m": overrides[
                "ramp_end_planar_progress_m"
            ],
            "ramp_rise_m": overrides["ramp_rise_m"],
            "planar_endpoint_m": stroke,
        }
        return action, metrics

    _multi._compile_action = ramped_compile
    try:
        receipt = _base.enumerate_and_freeze(derived_path, public_output)
    finally:
        _multi._compile_action = original_compile
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_ramped_funnel_static_receipt.v1"
            ),
            "proof_class": (
                "cpu_fp64_static_ramped_fingertip_open_loop_guiding_contact_"
                "collision_camera_gateway_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "derived_contract_path": str(derived_path.relative_to(REPO_ROOT)),
            "derived_contract_sha256": _sha(derived_path),
            "base_static_contract_sha256": contract[
                "base_static_contract"
            ]["sha256"],
            "v05_ud_static_receipt_sha256": contract[
                "v05_ud_static_receipt"
            ]["sha256"],
            "ramped_fingertip_path": copy.deepcopy(overrides),
            "frozen_override_only": True,
        }
    )
    receipt["claim_boundary"] = (
        "Static-only deterministic ramped-fingertip guiding-contact search "
        "with setup included in exact action bytes. No dynamic task outcome, "
        "calibrated plant, physical packet, promotion, or transfer claim."
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["RampedFunnelStaticV1Error", "enumerate_and_freeze"]
