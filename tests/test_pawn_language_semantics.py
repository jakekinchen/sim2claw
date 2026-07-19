from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Callable

import pytest

from sim2claw.pawn_language_semantics import (
    EXPECTED_BENCHMARK_SHA256,
    PawnLanguageContractError,
    language_contract_sha256,
    load_language_contract,
    render_training_task_rows,
    validate_language_contract,
)


def test_contract_freezes_exact_b_g_semantics_and_no_launch_gate() -> None:
    contract = load_language_contract()
    tasks = contract["tasks"]
    assert len(tasks) == 12
    assert [task["semantic_index"] for task in tasks] == list(range(12))
    assert {task["source_square"][0] for task in tasks} == set("bcdefg")
    assert {task["source_square"][1] for task in tasks} == {"1", "2"}
    assert contract["benchmark_binding"]["sha256"] == EXPECTED_BENCHMARK_SHA256
    snapshot = contract["current_admission_snapshot"]
    assert snapshot["unique_admitted_source_group_count"] == 0
    assert snapshot["training_row_count"] == 0
    assert snapshot["paid_training_ready"] is False
    assert snapshot["missing_semantic_ids"] == [
        task["semantic_id"] for task in tasks
    ]
    assert len(language_contract_sha256()) == 64


def test_training_prompt_rows_are_deterministic_and_not_new_evidence() -> None:
    rows = render_training_task_rows()
    assert len(rows) == 24
    assert [row["task_index"] for row in rows] == list(range(24))
    assert len({row["task"] for row in rows}) == 24
    assert rows[0]["task"] == "Move the brown pawn from B1 to B2."
    assert (
        rows[1]["task"]
        == "Pick up the brown pawn on B1 and place it upright on the empty square B2."
    )
    assert rows[-1]["task"].endswith("empty square G1.")
    for row in rows:
        assert row["independent_behavioral_evidence_added"] is False
        assert row["prompt_sha256"] == hashlib.sha256(
            row["task"].encode("utf-8")
        ).hexdigest()


@pytest.mark.parametrize(
    "mutator, message",
    [
        (
            lambda value: value["benchmark_binding"].__setitem__("sha256", "0" * 64),
            "benchmark binding changed",
        ),
        (
            lambda value: value["scene_binding"].__setitem__("piece_color", "tan"),
            "scene or piece-family binding changed",
        ),
        (
            lambda value: value["tasks"].__setitem__(0, value["tasks"][1]),
            "task semantics differ",
        ),
        (
            lambda value: value["tasks"][0].__setitem__(
                "reverse_semantic_id", "pawn_c2_to_c1"
            ),
            "task semantics differ",
        ),
        (
            lambda value: value["prompt_templates"][0].__setitem__(
                "template", "Move {SOURCE} to {DESTINATION} at seed 9101."
            ),
            "privileged or outcome data",
        ),
        (
            lambda value: value["prompt_templates"][0]["provenance"].__setitem__(
                "network_or_external_model_used", True
            ),
            "prompt provenance changed",
        ),
        (
            lambda value: value["prompt_templates"][0]["provenance"].__setitem__(
                "heldout_content_used", 0
            ),
            "prompt provenance changed",
        ),
        (
            lambda value: value["prompt_templates"][0].__setitem__(
                "template",
                "Move {SOURCE} to {DESTINATION}; use high friction if the evaluator says it failed.",
            ),
            "prompt template text changed",
        ),
        (
            lambda value: value["prompt_templates"].__setitem__(
                0, list(value["prompt_templates"][0].items())
            ),
            "template rows must be objects",
        ),
        (
            lambda value: value["augmentation_gate"].__setitem__(
                "prompt_variants_are_independent_evidence", True
            ),
            "augmentation or evidence-counting gate changed",
        ),
        (
            lambda value: value["current_admission_snapshot"].__setitem__(
                "training_row_count", 24
            ),
            "no-launch admission snapshot changed",
        ),
        (
            lambda value: value["authority"].__setitem__(
                "proves_language_generalization", True
            ),
            "overstates its authority",
        ),
        (
            lambda value: value["required_source_episode_binding_fields"].pop(),
            "source-episode binding fields changed",
        ),
        (
            lambda value: value["required_receipt_counts"].__setitem__(
                1, "derived_prompt_episode_count"
            ),
            "evidence receipt counts changed",
        ),
        (
            lambda value: value["current_admission_snapshot"].__setitem__(
                "physical_catalog_training_rows", 1
            ),
            "no-launch admission snapshot changed",
        ),
        (
            lambda value: value["authority"].__setitem__(
                "proves_training_occurred", 0
            ),
            "overstates its authority",
        ),
        (
            lambda value: value["current_admission_snapshot"].__setitem__(
                "paid_training_ready", 0
            ),
            "no-launch admission snapshot changed",
        ),
        (
            lambda value: value["augmentation_gate"].__setitem__(
                "heldout_rows_may_enter_builder", 0
            ),
            "augmentation or evidence-counting gate changed",
        ),
    ],
)
def test_contract_rejects_semantic_prompt_and_counting_tamper(
    mutator: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    changed = deepcopy(load_language_contract())
    mutator(changed)
    with pytest.raises(PawnLanguageContractError, match=message):
        validate_language_contract(changed)


def test_reverse_pairs_and_target_authority_are_complete() -> None:
    contract = load_language_contract()
    by_id = {task["semantic_id"]: task for task in contract["tasks"]}
    for task in contract["tasks"]:
        reverse = by_id[task["reverse_semantic_id"]]
        assert reverse["reverse_semantic_id"] == task["semantic_id"]
        assert reverse["source_square"] == task["destination_square"]
        assert reverse["destination_square"] == task["source_square"]
        assert task["target"] == {
            "kind": "benchmark_destination_square_center",
            "coordinate_authority": "benchmark_binding.board_coordinate_system",
        }
