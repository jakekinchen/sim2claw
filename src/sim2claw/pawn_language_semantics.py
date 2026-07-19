"""Frozen language semantics for the current B-G pawn product surface."""

from __future__ import annotations

import hashlib
import json
import string
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT


DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs" / "tasks" / "pawn_b_g_language_semantics_v1.json"
)
EXPECTED_SCHEMA = "sim2claw.pawn_b_g_language_semantics.v1"
EXPECTED_BENCHMARK_PATH = Path(
    "configs/evaluations/pawn_rank12_bidirectional_v2.json"
)
EXPECTED_BENCHMARK_ID = "pawn_rank12_bidirectional_b_to_g_v2"
EXPECTED_BENCHMARK_SHA256 = (
    "8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3"
)
EXPECTED_BENCHMARK_COMMIT = "36f1ebc5f66e63317b1fba84ba9aaabf66a5ff2d"
EXPECTED_SCENE = {
    "scene_id": "operator_updated_chess_workcell_v3",
    "workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
    "board_pose_id": "board_robotward_100mm_20260718_v3",
    "piece_family": "pawn",
    "piece_color": "brown",
}
EXPECTED_TEMPLATE_IDS = (
    "canonical_move_v1",
    "pick_place_upright_v1",
    "relocate_undisturbed_v1",
)
EXPECTED_TEMPLATE_TEXT = {
    "canonical_move_v1": "Move the brown pawn from {SOURCE} to {DESTINATION}.",
    "pick_place_upright_v1": (
        "Pick up the brown pawn on {SOURCE} and place it upright on the empty "
        "square {DESTINATION}."
    ),
    "relocate_undisturbed_v1": (
        "Relocate the brown pawn from {SOURCE} to {DESTINATION}, leaving every "
        "other piece undisturbed."
    ),
}
EXPECTED_PROVENANCE = {
    "method": "deterministic_clean_room_template_expansion",
    "source": "semantic_fields_only",
    "archive_material_used": False,
    "heldout_content_used": False,
    "network_or_external_model_used": False,
    "review_status": "accepted",
}
EXPECTED_SOURCE_BINDING_FIELDS = (
    "source_episode_group_id",
    "source_episode_id",
    "semantic_id",
    "split",
    "scene_id",
    "workspace_pose_id",
    "board_pose_id",
    "piece_layout_id",
    "reset_id",
    "piece_id",
    "observed_source_pose_world",
    "continuous_target_pose_world",
    "source_receipt_sha256",
    "source_parquet_sha256",
    "source_video_sha256",
    "source_state_sha256",
    "source_action_sha256",
    "observation_action_schema_sha256",
    "admission_verdict_sha256",
    "evaluator_contract_sha256",
    "strict_success",
    "held_out_membership",
)
EXPECTED_RECEIPT_COUNTS = (
    "semantic_task_count",
    "unique_source_episode_group_count",
    "unique_source_episode_count",
    "train_prompt_variant_count",
    "derived_prompt_episode_count",
    "sampling_weight_replica_count",
    "derived_dataset_episode_count",
    "source_frame_count",
    "derived_frame_count",
    "heldout_rows_used",
)
EXPECTED_AUTHORITY = {
    "proves_training_occurred": False,
    "proves_language_generalization": False,
    "proves_policy_success": False,
    "proves_physical_calibration": False,
    "grants_physical_authority": False,
    "held_out_rows_opened": 0,
}
EXPECTED_ROOT_KEYS = {
    "schema_version",
    "contract_id",
    "frozen_before_dataset_export",
    "proof_class",
    "benchmark_binding",
    "scene_binding",
    "prompt_templates",
    "tasks",
    "augmentation_gate",
    "required_source_episode_binding_fields",
    "required_receipt_counts",
    "current_admission_snapshot",
    "authority",
    "claim_boundary",
}
FORBIDDEN_PROMPT_TOKENS = (
    "reward",
    "threshold",
    "held-out",
    "held_out",
    "seed",
    "offset",
    "phase",
    "joint",
    "action",
    "contact force",
)


class PawnLanguageContractError(ValueError):
    """Raised when the language contract can no longer prove its identity."""


def _strict_equal(actual: Any, expected: Any) -> bool:
    """Compare JSON-like values without Python's bool/int equivalence."""

    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _strict_equal(actual[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _strict_equal(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PawnLanguageContractError(f"JSON root must be an object: {path}")
    return value


def _placeholders(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }


def _validate_templates(templates: object) -> list[dict[str, Any]]:
    if not isinstance(templates, list) or len(templates) != 3:
        raise PawnLanguageContractError("language contract requires exactly three templates")
    if any(not isinstance(row, dict) for row in templates):
        raise PawnLanguageContractError("prompt template rows must be objects")
    rows = [deepcopy(row) for row in templates]
    if tuple(row.get("variant_id") for row in rows) != EXPECTED_TEMPLATE_IDS:
        raise PawnLanguageContractError("prompt template order or identity changed")
    if [row.get("split") for row in rows] != ["train", "train", "dev"]:
        raise PawnLanguageContractError("prompt split schedule changed")
    if not _strict_equal(
        [row.get("variant_index") for row in rows],
        [0, 1, 0],
    ):
        raise PawnLanguageContractError("prompt variant indices changed")
    for row in rows:
        if set(row) != {
            "variant_id",
            "split",
            "variant_index",
            "template",
            "provenance",
        }:
            raise PawnLanguageContractError("prompt template schema changed")
        template = row.get("template")
        if not isinstance(template, str) or _placeholders(template) != {
            "SOURCE",
            "DESTINATION",
        }:
            raise PawnLanguageContractError(
                "prompt template must use only SOURCE and DESTINATION"
            )
        lowered = template.lower()
        if any(token in lowered for token in FORBIDDEN_PROMPT_TOKENS):
            raise PawnLanguageContractError("prompt contains privileged or outcome data")
        if template != EXPECTED_TEMPLATE_TEXT[row["variant_id"]]:
            raise PawnLanguageContractError("prompt template text changed")
        if not _strict_equal(row.get("provenance"), EXPECTED_PROVENANCE):
            raise PawnLanguageContractError("prompt provenance changed")
    return rows


def _expected_skill_rows(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    skills = benchmark.get("skills")
    if not isinstance(skills, list) or len(skills) != 12:
        raise PawnLanguageContractError("benchmark must contain exactly 12 skills")
    expected: list[dict[str, Any]] = []
    for index, skill in enumerate(skills):
        source = str(skill["source_square"])
        destination = str(skill["destination_square"])
        semantic_id = str(skill["skill_id"])
        expected.append(
            {
                "semantic_index": index,
                "semantic_id": semantic_id,
                "piece_id": f"brown_pawn_{source}",
                "direction": str(skill["direction"]),
                "source_square": source,
                "destination_square": destination,
                "reverse_semantic_id": str(skill["reverse_skill_id"]),
                "canonical_instruction": (
                    f"Move the brown pawn from {source.upper()} to "
                    f"{destination.upper()}."
                ),
                "target": {
                    "kind": "benchmark_destination_square_center",
                    "coordinate_authority": "benchmark_binding.board_coordinate_system",
                },
            }
        )
    expected_ids = {row["semantic_id"] for row in expected}
    if expected_ids != {
        f"pawn_{column}{rank}_to_{column}{3 - rank}"
        for column in "bcdefg"
        for rank in (1, 2)
    }:
        raise PawnLanguageContractError("benchmark is not the exact B-G rank-1/2 surface")
    by_id = {row["semantic_id"]: row for row in expected}
    for row in expected:
        reverse = by_id.get(row["reverse_semantic_id"])
        if (
            reverse is None
            or reverse["reverse_semantic_id"] != row["semantic_id"]
            or reverse["source_square"] != row["destination_square"]
            or reverse["destination_square"] != row["source_square"]
        ):
            raise PawnLanguageContractError("benchmark reverse-pair semantics changed")
    return expected


def validate_language_contract(
    contract: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Validate the frozen semantic surface without admitting any episode."""

    if set(contract) != EXPECTED_ROOT_KEYS:
        raise PawnLanguageContractError("pawn language contract schema changed")
    if contract.get("schema_version") != EXPECTED_SCHEMA:
        raise PawnLanguageContractError("unsupported pawn language contract schema")
    if contract.get("contract_id") != "pawn_b_g_language_semantics_v1":
        raise PawnLanguageContractError("pawn language contract identity changed")
    if contract.get("frozen_before_dataset_export") is not True:
        raise PawnLanguageContractError("language contract was not frozen before export")
    if (
        contract.get("proof_class")
        != "language_semantics_contract_only_no_episode_or_policy_result"
    ):
        raise PawnLanguageContractError("pawn language proof class changed")
    binding = contract.get("benchmark_binding")
    if not isinstance(binding, dict):
        raise PawnLanguageContractError("benchmark binding is missing")
    if not _strict_equal(binding, {
        "path": EXPECTED_BENCHMARK_PATH.as_posix(),
        "evaluation_set_id": EXPECTED_BENCHMARK_ID,
        "sha256": EXPECTED_BENCHMARK_SHA256,
        "source_commit": EXPECTED_BENCHMARK_COMMIT,
        "coordinate_authority": "board_coordinate_system",
    }):
        raise PawnLanguageContractError("benchmark binding changed")
    benchmark_path = repo_root.resolve() / EXPECTED_BENCHMARK_PATH
    if _sha256(benchmark_path) != EXPECTED_BENCHMARK_SHA256:
        raise PawnLanguageContractError("bound benchmark bytes changed")
    benchmark = _load_object(benchmark_path)
    if benchmark.get("evaluation_set_id") != EXPECTED_BENCHMARK_ID:
        raise PawnLanguageContractError("bound benchmark identity changed")
    if not _strict_equal(contract.get("scene_binding"), EXPECTED_SCENE):
        raise PawnLanguageContractError("scene or piece-family binding changed")

    templates = _validate_templates(contract.get("prompt_templates"))
    expected_tasks = _expected_skill_rows(benchmark)
    if not _strict_equal(contract.get("tasks"), expected_tasks):
        raise PawnLanguageContractError("task semantics differ from the bound benchmark")

    gate = contract.get("augmentation_gate")
    required_gate = {
        "group_key": "source_episode_group_id",
        "train_task_index_rule": "2 * semantic_index + train_variant_index",
        "split_before_prompt_expansion": True,
        "prompt_variants_are_independent_evidence": False,
        "sampling_replicas_are_independent_evidence": False,
        "heldout_rows_may_enter_builder": False,
        "require_independently_admitted_current_geometry_source_group_per_semantic": True,
    }
    if not _strict_equal(gate, required_gate):
        raise PawnLanguageContractError("augmentation or evidence-counting gate changed")
    if tuple(contract.get("required_source_episode_binding_fields", ())) != (
        EXPECTED_SOURCE_BINDING_FIELDS
    ):
        raise PawnLanguageContractError("required source-episode binding fields changed")
    if tuple(contract.get("required_receipt_counts", ())) != EXPECTED_RECEIPT_COUNTS:
        raise PawnLanguageContractError("required evidence receipt counts changed")
    snapshot = contract.get("current_admission_snapshot")
    if not isinstance(snapshot, dict):
        raise PawnLanguageContractError("current admission snapshot is missing")
    expected_snapshot = {
        "created_at": "2026-07-19T03:20:00-05:00",
        "unique_admitted_source_group_count": 0,
        "training_row_count": 0,
        "all_12_semantics_covered": False,
        "paid_training_ready": False,
        "missing_semantic_ids": [row["semantic_id"] for row in expected_tasks],
        "current_sparse_layout_native_direction_count": 6,
        "reverse_direction_source_contract_required": True,
        "physical_catalog_training_rows": 0,
        "reason": (
            "No independently evaluator-admitted current-geometry B-G source "
            "group exists for any semantic. Prompt expansion cannot repair "
            "missing behavioral coverage."
        ),
    }
    if not _strict_equal(snapshot, expected_snapshot):
        raise PawnLanguageContractError("current no-launch admission snapshot changed")
    authority = contract.get("authority")
    if not _strict_equal(authority, EXPECTED_AUTHORITY):
        raise PawnLanguageContractError("language contract overstates its authority")
    if contract.get("claim_boundary") != (
        "This contract freezes B-G task meaning, prompt provenance, split order, "
        "and counting semantics only. It creates no robot episode, no independent "
        "evidence, no training result, and no permission to launch paid compute."
    ):
        raise PawnLanguageContractError("language contract claim boundary changed")

    validated = deepcopy(contract)
    validated["prompt_templates"] = templates
    return validated


def load_language_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    return validate_language_contract(_load_object(path), repo_root=repo_root)


def language_contract_sha256(path: Path = DEFAULT_CONTRACT_PATH) -> str:
    return _sha256(path)


def render_training_task_rows(
    contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Render deterministic task metadata; this does not create episode evidence."""

    validated = (
        load_language_contract()
        if contract is None
        else validate_language_contract(contract)
    )
    train_templates = [
        row for row in validated["prompt_templates"] if row["split"] == "train"
    ]
    rows: list[dict[str, Any]] = []
    for task in validated["tasks"]:
        for template in train_templates:
            task_index = 2 * int(task["semantic_index"]) + int(
                template["variant_index"]
            )
            prompt = str(template["template"]).format(
                SOURCE=str(task["source_square"]).upper(),
                DESTINATION=str(task["destination_square"]).upper(),
            )
            rows.append(
                {
                    "task_index": task_index,
                    "semantic_index": task["semantic_index"],
                    "semantic_id": task["semantic_id"],
                    "variant_id": template["variant_id"],
                    "variant_index": template["variant_index"],
                    "split": "train",
                    "task": prompt,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "independent_behavioral_evidence_added": False,
                }
            )
    if [row["task_index"] for row in rows] != list(range(24)):
        raise PawnLanguageContractError("rendered task indices are not contiguous")
    if len({row["task"] for row in rows}) != 24:
        raise PawnLanguageContractError("rendered train prompts are not unique")
    return rows
