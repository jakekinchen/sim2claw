from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v3.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v3",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wrist_evaluator_exposes_callable_entrypoint() -> None:
    assert callable(MODULE.evaluate)
