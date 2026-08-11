from __future__ import annotations

import ast
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.observable_registration_d1_d2_nominal_wrist_presentation import (
    CONTRACT_PATH,
    OUTPUT_DIRECTORY,
    REPO_ROOT,
    build_projection_context,
    load_nominal_wrist_presentation_contract,
    verify_nominal_wrist_presentation,
)


SOURCE_PATH = (
    REPO_ROOT
    / "src/sim2claw/observable_registration_d1_d2_nominal_wrist_presentation.py"
)


def test_contract_trace_and_nominal_camera_are_frozen() -> None:
    contract = load_nominal_wrist_presentation_contract(CONTRACT_PATH)
    context = build_projection_context(contract)

    assert context.trace_model.shape == (531, 6)
    assert len(context.trace_rows) == 531
    assert np.all(np.diff(context.timestamps) > 0.0)

    camera_names = [
        mujoco.mj_id2name(context.model, mujoco.mjtObj.mjOBJ_CAMERA, index)
        for index in range(context.model.ncam)
    ]
    assert camera_names.count("left_wrist_cam") == 1
    assert context.camera_id == camera_names.index("left_wrist_cam")
    np.testing.assert_allclose(
        context.model.cam_pos[context.camera_id],
        contract["camera"]["model_local_position_m"],
        rtol=0.0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        context.model.cam_quat[context.camera_id],
        contract["camera"]["model_local_quaternion_wxyz"],
        rtol=0.0,
        atol=1e-12,
    )
    assert abs(
        float(context.model.cam_fovy[context.camera_id])
        - float(contract["camera"]["vertical_fov_degrees"])
    ) < 1e-9


def test_renderer_source_has_no_step_controller_or_scoring_path() -> None:
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {"mj_step", "mj_step1", "mj_step2"}
    observed_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert forbidden_calls.isdisjoint(observed_calls)

    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            else:
                targets.append(node.target)
        for target in targets:
            if isinstance(target, ast.Subscript) and isinstance(
                target.value, ast.Attribute
            ):
                assert target.value.attr != "ctrl"

    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "_contact_counts" not in source
    assert "_outcome(" not in source


def test_existing_render_verifies_when_present() -> None:
    if not (OUTPUT_DIRECTORY / "receipt.json").is_file():
        return
    report = verify_nominal_wrist_presentation()
    assert report["status"] == "pass"
    assert all(report["gates"].values())
