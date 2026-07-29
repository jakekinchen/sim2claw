"""Fit and apply the RP04A elbow-only sample-domain tracking challenger."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import canonical_seeded_action_static as _static
from .paths import REPO_ROOT


class CoordinatedUnloadingTrackingError(RuntimeError):
    """A frozen tracking input, split, or evidence boundary changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinatedUnloadingTrackingError(message)


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CoordinatedUnloadingTrackingError(
            "tracking input escapes repository"
        ) from error
    _require(path.is_file(), f"tracking input is missing: {path}")
    _require(_sha(path) == entry["sha256"], f"tracking input changed: {path}")
    return path


def _write_tensor(
    directory: Path,
    name: str,
    values: np.ndarray,
) -> dict[str, Any]:
    path = directory / f"{name}.f64le"
    array = np.asarray(values, dtype="<f8", order="C")
    path.write_bytes(array.tobytes(order="C"))
    return {
        "path": _display_path(path),
        "sha256": _sha(path),
        "shape": list(array.shape),
        "dtype": "little_endian_float64",
    }


def _forward_trace(
    telemetry_path: Path,
    *,
    expected_rows: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[dict[str, Any]] = []
    with telemetry_path.open(encoding="utf-8") as handle:
        for line in handle:
            sample = json.loads(line)
            if sample.get("phase") == "forward_source":
                rows.append(sample)
    _require(len(rows) == expected_rows, "forward-source denominator changed")
    _require(
        [row["source_row_or_missing"] for row in rows]
        == list(range(expected_rows)),
        "forward-source row order changed",
    )
    _require(
        all(row["source_requested_bytes_unchanged"] for row in rows),
        "physical requested bytes were not preserved",
    )
    _require(
        all(not row["safety_clamped"] for row in rows),
        "physical trace contains a safety clamp",
    )
    requested = np.asarray(
        [row["requested_source_command_degrees"] for row in rows],
        dtype="<f8",
        order="C",
    )
    sent = np.asarray(
        [row["follower_requested_degrees"] for row in rows],
        dtype="<f8",
        order="C",
    )
    observed = np.asarray(
        [row["follower_actual_position_degrees"] for row in rows],
        dtype="<f8",
        order="C",
    )
    _require(
        np.allclose(requested, sent, rtol=0.0, atol=1e-12),
        "requested and sent physical traces differ",
    )
    return requested, sent, observed


def _fit_first_order_affine(
    requested: np.ndarray,
    observed: np.ndarray,
    *,
    train_row_count: int,
) -> tuple[float, float]:
    _require(
        2 < train_row_count < len(requested),
        "invalid chronological fit split",
    )
    prior = observed[: train_row_count - 1]
    command_error = requested[1:train_row_count] - prior
    response = observed[1:train_row_count] - prior
    design = np.column_stack((command_error, np.ones_like(command_error)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, response, rcond=None)
    _require(rank == 2, "elbow fit is rank deficient")
    return float(coefficients[0]), float(coefficients[1])


def _recursive_prediction(
    requested: np.ndarray,
    *,
    initial_actual: float,
    alpha: float,
    bias_degrees_per_sample: float,
) -> np.ndarray:
    predicted = np.empty(len(requested), dtype="<f8")
    previous = float(initial_actual)
    for index, command in enumerate(requested):
        previous = (
            previous
            + alpha * (float(command) - previous)
            + bias_degrees_per_sample
        )
        predicted[index] = previous
    return predicted


def fit_tracking_challenger(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Fit the frozen elbow-only plant and score its untouched chronological tail."""

    _require(
        not output_directory.exists(),
        "immutable tracking-fit output directory already exists",
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.coordinated_unloading_tracking_fit.v1",
        "unexpected tracking-fit contract",
    )
    expected_fields = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "inputs",
        "trace",
        "fit",
        "heldout_acceptance",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    _require(set(contract) == expected_fields, "tracking-fit contract widened")
    _require(
        contract["authority"]
        == {
            "read_physical_evidence": True,
            "fit_sample_domain_tracking": True,
            "dynamic_task_replay": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "transfer_claim": False,
        },
        "tracking-fit authority changed",
    )
    for entry in contract["inputs"].values():
        _bound(entry)
    closeout = json.loads(
        _bound(contract["inputs"]["physical_closeout"]).read_text(
            encoding="utf-8"
        )
    )
    _require(
        closeout["status"]
        == "coordinated_unloading_confirmed_exact_task_mapping_rejected"
        and closeout["result"]["physical_task_attempts"] == 0
        and closeout["result"]["camera_review_no_pawn_or_board_contact"] is True,
        "physical trace is not admitted no-contact evidence",
    )
    expected_rows = int(contract["trace"]["expected_forward_rows"])
    requested, sent, observed = _forward_trace(
        _bound(contract["inputs"]["telemetry"]),
        expected_rows=expected_rows,
    )
    prefix_entry = contract["inputs"]["physical_prefix"]
    prefix_shape = tuple(int(value) for value in prefix_entry["shape"])
    prefix = np.fromfile(_bound(prefix_entry), dtype="<f8").reshape(prefix_shape)
    _require(
        prefix_shape[1] == requested.shape[1]
        and prefix_shape[0] >= expected_rows
        and np.array_equal(prefix[:expected_rows], requested),
        "telemetry is not the exact frozen physical prefix",
    )
    joint_index = int(contract["fit"]["joint_index"])
    _require(
        joint_index == 2
        and contract["fit"]["joint_name"] == "elbow_flex"
        and contract["fit"]["model_kind"]
        == "first_order_affine_error_response_per_sample",
        "tracking challenger must remain elbow-only",
    )
    train_count = int(contract["fit"]["train_row_count"])
    requested_elbow = requested[:, joint_index]
    observed_elbow = observed[:, joint_index]
    alpha, bias = _fit_first_order_affine(
        requested_elbow,
        observed_elbow,
        train_row_count=train_count,
    )
    heldout_requested = requested_elbow[train_count:]
    heldout_observed = observed_elbow[train_count:]
    heldout_predicted = _recursive_prediction(
        heldout_requested,
        initial_actual=float(observed_elbow[train_count - 1]),
        alpha=alpha,
        bias_degrees_per_sample=bias,
    )
    residual = heldout_predicted - heldout_observed
    naive = heldout_requested - heldout_observed
    rmse = float(math.sqrt(float(np.mean(np.square(residual)))))
    maximum = float(np.max(np.abs(residual)))
    naive_rmse = float(math.sqrt(float(np.mean(np.square(naive)))))
    relative_improvement = 1.0 - rmse / naive_rmse
    checks = {
        "fit_alpha_in_range": (
            float(contract["fit"]["minimum_alpha"])
            <= alpha
            <= float(contract["fit"]["maximum_alpha"])
        ),
        "fit_bias_in_range": abs(bias)
        <= float(contract["fit"]["maximum_absolute_bias_degrees_per_sample"]),
        "heldout_rmse": rmse
        <= float(contract["heldout_acceptance"]["maximum_rmse_degrees"]),
        "heldout_maximum_error": maximum
        <= float(
            contract["heldout_acceptance"]["maximum_absolute_error_degrees"]
        ),
        "heldout_relative_improvement": relative_improvement
        >= float(
            contract["heldout_acceptance"][
                "minimum_relative_improvement_over_requested"
            ]
        ),
        "requested_sent_identity": bool(
            np.allclose(requested, sent, rtol=0.0, atol=1e-12)
        ),
        "fit_uses_no_task_outcomes": contract["fit"][
            "task_outcomes_used"
        ]
        is False,
    }
    passed = all(checks.values())
    output_directory.mkdir(parents=True)
    tensors = {
        "requested_physical": _write_tensor(
            output_directory, "requested_physical", requested
        ),
        "sent_physical": _write_tensor(
            output_directory, "sent_physical", sent
        ),
        "observed_physical": _write_tensor(
            output_directory, "observed_physical", observed
        ),
        "heldout_elbow_predicted": _write_tensor(
            output_directory, "heldout_elbow_predicted", heldout_predicted
        ),
    }
    receipt = {
        "schema_version":
        "sim2claw.coordinated_unloading_tracking_fit_receipt.v1",
        "contract_id": contract["contract_id"],
        "status": (
            "coordinated_unloading_tracking_fit_pass"
            if passed
            else "coordinated_unloading_tracking_fit_reject"
        ),
        "passed": passed,
        "source_rows": expected_rows,
        "train_rows": train_count,
        "heldout_rows": expected_rows - train_count,
        "joint": {
            "name": "elbow_flex",
            "index": joint_index,
            "model_kind": contract["fit"]["model_kind"],
            "alpha": alpha,
            "bias_degrees_per_sample": bias,
            "sample_hz_label": float(contract["trace"]["nominal_sample_hz"]),
            "causal_latency_calibrated": False,
        },
        "support": {
            "train_requested_minimum_degrees": float(
                np.min(requested_elbow[:train_count])
            ),
            "train_requested_maximum_degrees": float(
                np.max(requested_elbow[:train_count])
            ),
            "train_observed_minimum_degrees": float(
                np.min(observed_elbow[:train_count])
            ),
            "train_observed_maximum_degrees": float(
                np.max(observed_elbow[:train_count])
            ),
            "full_observed_minimum_degrees": float(np.min(observed_elbow)),
            "full_observed_maximum_degrees": float(np.max(observed_elbow)),
        },
        "heldout": {
            "start_row": train_count,
            "end_row_inclusive": expected_rows - 1,
            "rmse_degrees": rmse,
            "maximum_absolute_error_degrees": maximum,
            "requested_as_prediction_rmse_degrees": naive_rmse,
            "relative_improvement_over_requested": relative_improvement,
        },
        "checks": checks,
        "tensors": tensors,
        "task_outcomes_used": False,
        "dynamic_task_replay": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "claim_boundary": contract["claim_boundary"],
    }
    receipt_path = output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def apply_elbow_tracking_challenger(
    requested_model: np.ndarray,
    *,
    candidate_config: Mapping[str, Any],
    alpha: float,
    bias_degrees_per_sample: float,
    initial_actual_degrees: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply only the frozen elbow tracking response; preserve requested bytes."""

    requested = np.asarray(requested_model, dtype="<f8", order="C")
    physical_requested = _static._physical_actions(
        requested, candidate_config
    )
    physical_applied = physical_requested.copy(order="C")
    physical_applied[0, 2] = initial_actual_degrees
    for index in range(1, len(physical_applied)):
        prior = physical_applied[index - 1, 2]
        physical_applied[index, 2] = (
            prior
            + alpha * (physical_requested[index, 2] - prior)
            + bias_degrees_per_sample
        )
    transforms = candidate_config["physical_adapter"]["joint_transform"][
        "joints"
    ]
    applied_model = requested.copy(order="C")
    elbow_transform = transforms[2]
    applied_model[:, 2] = (
        physical_applied[:, 2]
        * float(elbow_transform["sign"])
        * float(elbow_transform["scale"])
        + float(elbow_transform["zero_offset"])
    )
    return (
        np.asarray(applied_model, dtype="<f8", order="C"),
        np.asarray(physical_applied, dtype="<f8", order="C"),
    )
