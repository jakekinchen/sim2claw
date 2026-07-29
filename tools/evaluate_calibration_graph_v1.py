#!/usr/bin/env python3
"""Evaluate the frozen minimum CalibrationGraph.v1."""

from __future__ import annotations

import json
from pathlib import Path

from sim2claw.calibration_graph_v1 import evaluate
from sim2claw.paths import REPO_ROOT


def main() -> None:
    contract = (
        REPO_ROOT / "configs/evaluations/calibration_graph_v1.json"
    )
    raw = json.loads(contract.read_text(encoding="utf-8"))
    receipt = evaluate(
        contract.resolve(),
        (REPO_ROOT / raw["output_directory"]).resolve(),
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "physical_model_mapping_approved": receipt[
                    "physical_model_mapping_approved"
                ],
                "jacobian": receipt["jacobian"],
                "rejection_reasons": receipt["rejection_reasons"],
                "physical_motion": receipt["physical_motion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
