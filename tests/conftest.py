from __future__ import annotations

import copy
from pathlib import Path

import pytest

from evals.inspect_gapbench import dataset as gapbench_dataset
from evals.inspect_gapbench.dataset import PUBLIC_SOURCE
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    load_json_object,
    sha256_file,
)


@pytest.fixture
def gapbench_smoke_sealed_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, str]:
    """Create non-campaign evaluator bytes solely for public test execution."""

    public = load_json_object(PUBLIC_SOURCE, label="GapBench public smoke source")
    cases = []
    for case in public["cases"]:
        target = copy.deepcopy(case["baseline_candidate"]["parameters"])
        target["reset_offset_m"] = 0.49
        feature_names = tuple(case["parameter_envelopes"])
        active_features = {name: 0.0 for name in feature_names}
        active_features["reset_offset_m"] = 1.0
        guard_features = {name: 0.0 for name in feature_names}
        case_id = str(case["case_id"])
        cases.append(
            {
                "schema_version": "sim2claw.gapbench_sealed_case.v1",
                "case_id": case_id,
                "fault_family": "reset_support",
                "evaluator_identity": "sim2claw-gapbench-public-ci-smoke-v1",
                "target_parameters": target,
                "hidden_rows": [
                    {
                        "row_id": f"{case_id}-smoke-active",
                        "features": active_features,
                        "bias": 0.0,
                        "observed": 0.49,
                        "consequence_threshold": 0.25,
                        "regression_guard": False,
                    },
                    {
                        "row_id": f"{case_id}-smoke-guard",
                        "features": guard_features,
                        "bias": 0.15,
                        "observed": 0.15,
                        "consequence_threshold": 0.25,
                        "regression_guard": True,
                    },
                ],
                "probe_results": {
                    "phase_alignment_probe": {
                        "dominant_mechanism": "reset_support",
                        "measurement": "public_ci_smoke_only",
                        "value": 0.49,
                        "unit": "synthetic",
                        "uncertainty": 0.0,
                        "interpretation": "Throwaway public CI evaluator.",
                    },
                    "identity_receipt_check": {
                        "identities_match": True,
                        "mismatch_localized": False,
                        "interpretation": "Throwaway public CI identities match.",
                    },
                },
            }
        )
    path = tmp_path / "gapbench-public-ci-smoke-sealed.json"
    atomic_write_json(
        path,
        {
            "schema_version": "sim2claw.gapbench_sealed_case_set.v1",
            "cases": cases,
        },
    )
    digest = sha256_file(path)
    binding = gapbench_dataset._sealed_source_binding()
    monkeypatch.setattr(
        gapbench_dataset,
        "_sealed_source_binding",
        lambda: {**binding, "sha256": digest},
    )
    monkeypatch.setenv(str(binding["environment"]), str(path))
    return path, digest
