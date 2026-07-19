#!/usr/bin/env python3
"""Run a preserved, synthetic LF-00 through LF-13 acceptance fixture."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sim2claw.learning_factory import LearningFactory
from sim2claw.learning_factory_artifacts import atomic_write_json
from sim2claw.paths import REPO_ROOT
from sim2claw.project_bundle import (
    EXPECTED_BG_SKILL_IDS,
    EXPECTED_BG_SKILL_SPECS,
    PROJECT_AUTHORITY_CONTRACT,
    PROJECT_BUNDLE_ENTRIES,
    PROJECT_PIPELINE_CONTRACT,
    PROJECT_TRAINING_LOCK,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(workspace: Path) -> Path:
    graph = workspace / "configs/learning_factory/graph_v1.json"
    graph.parent.mkdir(parents=True, exist_ok=True)
    graph.write_bytes((REPO_ROOT / "configs/learning_factory/graph_v1.json").read_bytes())
    contract = workspace / "configs/evaluations/frozen.json"
    catalog = workspace / "configs/data/physical_pawn_move_catalog_20260719.json"
    state = workspace / "docs/autonomous-workflow/project_state.json"
    project = workspace / "configs/projects/learning-factory-clean-fixture.json"
    atomic_write_json(
        contract,
        {
            "schema_version": "sim2claw.pawn_bidirectional_composability_eval.v2",
            "evaluation_set_id": "learning-factory-clean-fixture-evaluation",
            "benchmark_scope": {
                "current_physical_corpus": catalog.relative_to(workspace).as_posix()
            },
            "skills": list(EXPECTED_BG_SKILL_SPECS),
        },
    )
    atomic_write_json(
        catalog,
        {
            "schema_version": "sim2claw.physical_pawn_move_catalog.v1",
            "catalog_id": "learning-factory-clean-fixture-catalog",
            "episodes": [{"recording_id": "fixture-episode"}],
        },
    )
    atomic_write_json(
        state,
        {
            "schema_version": "sim2claw.autonomous_project_state.v1",
            "locked_product_evaluation": {
                "evaluation_set_id": "learning-factory-clean-fixture-evaluation",
                "contract": contract.relative_to(workspace).as_posix(),
                "sha256": _sha256(contract),
                "core_directed_cases": 12,
                "files": list("bcdefg"),
                "current_catalog_episode_count": 1,
            },
            "training_lock": PROJECT_TRAINING_LOCK,
            "promotion_owner": PROJECT_PIPELINE_CONTRACT["promotion_owner"],
            "workspace_registration": {"status": "synthetic_fixture"},
        },
    )
    atomic_write_json(
        workspace / "datasets/manipulation_source_recordings/fixture.json",
        {"proof_class": "synthetic_fixture"},
    )
    atomic_write_json(
        workspace / "outputs/pawn_composability/recovered_corpus_v2/fixture.json",
        {"proof_class": "synthetic_fixture"},
    )
    capture = workspace / "configs/polycam/fixture.json"
    mass = workspace / "calibration/so101/fixture.json"
    atomic_write_json(capture, {"proof_class": "synthetic_fixture"})
    atomic_write_json(mass, {"proof_class": "synthetic_fixture"})
    atomic_write_json(
        project,
        {
            "schema_version": "sim2claw.project.v1",
            "project_id": "learning-factory-clean-fixture",
            "source_of_truth": {
                "project_state": state.relative_to(workspace).as_posix(),
                "project_state_sha256": _sha256(state),
                "evaluation_contract": contract.relative_to(workspace).as_posix(),
                "evaluation_contract_sha256": _sha256(contract),
                "physical_source_catalog": catalog.relative_to(workspace).as_posix(),
                "physical_source_catalog_sha256": _sha256(catalog),
            },
            "scope": {
                "files": list("bcdefg"),
                "ranks": [1, 2],
                "directed_skill_count": 12,
                "directed_skill_ids": list(EXPECTED_BG_SKILL_IDS),
                "include_a_or_h": False,
            },
            "bundle_entries": list(PROJECT_BUNDLE_ENTRIES),
            "pipeline": copy.deepcopy(PROJECT_PIPELINE_CONTRACT),
            "learning_factory": {
                "graph": graph.relative_to(workspace).as_posix(),
                "profile": "deterministic_fixture",
                "campaign": {
                    "campaign_id": "synthetic-controller-mechanism",
                    "generation": 0,
                    "parent_generation": None,
                },
                "visual_context": {"required": False, "reason": "synthetic fixture"},
                "twin_candidate": {
                    "scene_id": "fixture-scene",
                    "capture_config": capture.relative_to(workspace).as_posix(),
                    "mass_profile": mass.relative_to(workspace).as_posix(),
                    "proof_class": "synthetic_fixture",
                },
                "source_mode": "synthetic_fixture",
                "replay_readiness_source": state.relative_to(workspace).as_posix(),
            },
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
            "claim_boundary": "Synthetic mechanism proof only; no physical or B-G policy claim.",
        },
    )
    return project.relative_to(workspace)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs/learning_factory",
    )
    args = parser.parse_args()
    run_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    workspace = (args.output_root / f"fixture-{run_id}").resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    project = _write_fixture(workspace)
    factory = LearningFactory(project, repo_root=workspace)
    report = factory.run_range("LF-00", "LF-13")
    evidence = {
        "schema_version": "sim2claw.learning_factory_fixture_evidence.v1",
        "proof_class": "synthetic_fixture",
        "workspace": str(workspace),
        "run": report,
        "status": factory.status(),
    }
    atomic_write_json(workspace / "fixture_evidence.json", evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if report["final_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
