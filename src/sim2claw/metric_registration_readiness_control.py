"""Post-terminal control for the exhausted metric-readiness evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

from sim2claw.metric_registration_readiness import (
    MetricRegistrationReadinessError,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "current_100mm_metric_registration_readiness_v1_exhausted.json"
)
EXPECTED_GUARD = {
    "schema_version": "sim2claw.metric_registration_readiness_exhaustion.v1",
    "contract_id": "current_100mm_metric_registration_readiness_v1",
    "status": "terminal_readiness_budget_exhausted_measurements_missing",
    "contract_sha256": (
        "dc8cbd7ee4363943512522774f2fb8e882f7bf88a192768ffdd9d210fd3c4910"
    ),
    "input_manifest_sha256": (
        "05cb1ba4a9907dab168bf9f62abd08af7d9c388c977d079342dd7730e9bc61f7"
    ),
    "execution_commit": "4bdba091d14ca7300e392b47514e06beb92ae001",
    "evaluator_sha256": (
        "40b1d75109708c9058240e12fd35dae39e7c728f07728a7a26cb255e75b2ea08"
    ),
    "evaluation_sha256": (
        "5900ff1297385d16ca7753aab5dfa89e828e60c49c5e0ee3a470bd704c3cdf7e"
    ),
    "evaluation_digest": (
        "bb7bd2f324710bb61132aec8be575d1a49791274a1dd46dc80fe6e47101e7f7d"
    ),
    "receipt_sha256": (
        "12b1624d6fdb6f2114df274cab2cd80e0b1c97a2aed72e37e8061991371f2df4"
    ),
    "receipt_digest": (
        "18bcbb0297e8660fce22613e66685aba35f11f134f788feef62812a810707057"
    ),
    "verdict": "measurement_prerequisites_missing",
    "missing_prerequisites": [
        "all_four_board_quadrants",
        "direct_board_measurement",
        "exact_mode_camera_intrinsics",
        "frame_extraction_lineage",
        "independent_board_fit_evaluation",
        "lens_distortion_control",
        "metric_object_keypoints_with_uncertainty",
        "minimum_independent_board_correspondences",
        "overhead_camera_to_workcell_transform",
        "wrist_camera_extrinsics",
    ],
    "invalid_input_count": 0,
    "readiness_evaluations_used": 1,
    "readiness_evaluations_maximum": 1,
    "camera_sessions_used": 0,
    "frames_captured": 0,
    "robot_motions_used": 0,
    "simulator_replays_used": 0,
    "provider_calls_used": 0,
    "training_rows_used": 0,
    "retry_authorized": False,
}


def load_exhaustion_guard(path: Path = GUARD_PATH) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MetricRegistrationReadinessError(
            f"Metric-readiness exhaustion guard is unavailable: {error}"
        ) from error
    if payload != EXPECTED_GUARD:
        raise MetricRegistrationReadinessError(
            "Metric-readiness exhaustion guard changed."
        )
    return payload


def run_authorized_evaluation(*_: object, **__: object) -> NoReturn:
    """Refuse every post-terminal evaluation before evaluator delegation."""

    load_exhaustion_guard()
    raise MetricRegistrationReadinessError(
        "Metric-registration readiness v1 is exhausted; use a new transaction."
    )
