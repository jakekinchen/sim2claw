#!/usr/bin/env python3
"""Run the copy-safe wrist-corner evaluator without wrapper recursion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

import tools.evaluate_calibration_graph_d405_corner_shape_heldout_v2 as shape_v2
import tools.evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v4 as evaluator_v4


ORIGINAL_BODY_ROTATION = shape_v2.body_rotation


def copied_body_rotation(*args: Any, **kwargs: Any) -> np.ndarray:
    return ORIGINAL_BODY_ROTATION(*args, **kwargs).copy()


def evaluate(contract_path: Path) -> dict[str, Any]:
    prior = evaluator_v4.copied_body_rotation
    evaluator_v4.copied_body_rotation = copied_body_rotation
    try:
        return evaluator_v4.evaluate(contract_path)
    finally:
        evaluator_v4.copied_body_rotation = prior


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate(arguments.contract.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
