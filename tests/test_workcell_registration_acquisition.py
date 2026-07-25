from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw import workcell_registration as registration
from sim2claw import workcell_registration_acquisition as acquisition
from sim2claw.cli import build_parser


def _write(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_backend(output: Path) -> dict[str, object]:
    video = output / "raw_burst.mp4"
    report = output / "native_report.json"
    ledger = output / "callbacks.jsonl"
    video.write_bytes(b"fake-native-video")
    report.write_text('{"status":"completed"}\n')
    ledger.write_text('{"stream":"c922"}\n')
    flat = np.full((480, 640, 3), 127, dtype=np.uint8)
    sharp = flat.copy()
    sharp[::4, ::4] = 255
    return {
        "frames": [
            {"frame_index": 4, "source_timestamp_seconds": 0.4, "pixels_bgr": flat},
            {"frame_index": 5, "source_timestamp_seconds": 0.5, "pixels_bgr": sharp},
            {"frame_index": 6, "source_timestamp_seconds": 0.6, "pixels_bgr": flat},
        ],
        "source_video_path": video,
        "native_report_path": report,
        "callback_ledger_path": ledger,
        "exact_mode": acquisition._expected_exact_mode(),
        "native_common_session": {"session_count": 1},
    }


def _captured(tmp_path: Path, *, synthetic: bool = False) -> dict[str, object]:
    root = tmp_path / "repo"
    root.mkdir()
    selector = root / "tools/selector.py"
    selector.parent.mkdir()
    shutil.copy2(Path(acquisition.__file__), selector)
    output = root / "runs/capture"
    if synthetic:
        result = acquisition.capture_stationary_bundle(
            output,
            acknowledgements={},
            focus_setting=None,
            dry_run=True,
            repo_root=root,
            selector_path=selector,
        )
    else:
        result = acquisition.capture_stationary_bundle(
            output,
            acknowledgements={name: True for name in acquisition.ACKNOWLEDGEMENTS},
            focus_setting="manual_locked_42",
            capture_backend=_fake_backend,
            repo_root=root,
            selector_path=selector,
        )
    return {"root": root, "selector": selector, "result": result}


def _finalize_fixture(tmp_path: Path) -> dict[str, object]:
    captured = _captured(tmp_path)
    root = Path(captured["root"])
    result = captured["result"]
    capture_path = Path(result["capture_receipt_path"])
    capture = json.loads(capture_path.read_text())
    artifacts = root / "artifacts"
    board_path = artifacts / "board.json"
    board_sha = _write(
        board_path,
        {
            "schema_version": "sim2claw.direct_board_measurement_receipt.v1",
            "measurement_method": "direct_physical_measurement",
            "playing_side_m": 0.3556,
            "standard_uncertainty_m": 0.0002,
            "measurement_tool_id": "caliper-1",
            "nominal_value_substituted": False,
            "synthetic": False,
        },
    )
    exact = acquisition._expected_exact_mode()
    intrinsics = artifacts / "intrinsics.json"
    _write(
        intrinsics,
        {
            "schema_version": "sim2claw.camera_intrinsics_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "exact_mode": exact,
            "camera_matrix": [[600.0, 0.0, 320.0], [0.0, 600.0, 240.0], [0.0, 0.0, 1.0]],
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    distortion = artifacts / "distortion.json"
    _write(
        distortion,
        {
            "schema_version": "sim2claw.lens_distortion_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "exact_mode": exact,
            "model": "opencv_pinhole_k1_k2_p1_p2_k3",
            "coefficients": [0.0, 0.0, 0.0, 0.0, 0.0],
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    notes = artifacts / "survey-notes.txt"
    notes.write_text("physical survey fixture")
    survey_path = artifacts / "survey.json"
    survey = {
        "schema_version": registration.SURVEY_SCHEMA,
        "status": "independently_reviewed_physical_survey",
        "workspace_pose_id": registration.WORKSPACE_POSE_ID,
        "board_pose_id": registration.BOARD_POSE_ID,
        "board_measurement_sha256": board_sha,
        "frame_convention": {
            "origin": "physical_board_center",
            "physical_a1_marker": "red",
            "physical_h1_marker": "blue",
            "physical_a8_marker": "green",
            "positive_x": "a1_to_h1",
            "positive_y": "a1_to_a8_robotward",
            "positive_z": "table_normal_upward",
            "handedness": "right_handed",
        },
        "transform_direction": "board_to_workcell",
        "board_to_workcell_transform_4x4": np.eye(4).tolist(),
        "measurement": {
            "method": "survey",
            "tool_id": "survey-tool",
            "operator": "operator",
            "measured_at": "2026-07-25T10:00:00-05:00",
            "translation_uncertainty_95_m": 0.001,
            "rotation_uncertainty_95_degrees": 0.2,
        },
        "independent_review": {
            "reviewer": "reviewer",
            "decision": "accepted",
            "reviewed_at": "2026-07-25T11:00:00-05:00",
        },
        "evidence_attachments": [
            {
                "kind": "measurement_notes",
                "path": str(notes.relative_to(root)),
                "sha256": hashlib.sha256(notes.read_bytes()).hexdigest(),
            }
        ],
        "nominal_values_substituted": False,
        "synthetic": False,
        "self_scored": False,
        "evaluator_owned": False,
        "physical_authority": False,
    }
    _write(survey_path, survey)
    bundle = result["annotation_bundle"]
    a_path = Path(bundle["annotation_templates"]["annotator_a"])
    b_path = Path(bundle["annotation_templates"]["annotator_b"])
    a = json.loads(a_path.read_text())
    b = json.loads(b_path.read_text())
    object_points = np.asarray(
        [
            [fraction[0] * 0.3556, fraction[1] * 0.3556, 0.0]
            for _, fraction, _ in acquisition.POINT_PLAN
        ],
        dtype=np.float64,
    )
    projected, _ = cv2.projectPoints(
        object_points,
        np.asarray([0.12, -0.15, 0.06]),
        np.asarray([0.01, -0.02, 0.82]),
        np.asarray([[600.0, 0.0, 320.0], [0.0, 600.0, 240.0], [0.0, 0.0, 1.0]]),
        np.zeros(5),
    )
    for value, identity, offset in ((a, "alice", 0.0), (b, "bob", 0.2)):
        value["status"] = "complete_independent_annotation"
        value["annotator_id"] = identity
        for index, point in enumerate(value["points"]):
            pixel = projected.reshape(-1, 2)[index]
            point["pixel_xy"] = [float(pixel[0] + offset), float(pixel[1])]
    a_path.unlink()
    b_path.unlink()
    _write(a_path, a)
    _write(b_path, b)
    return {
        **captured,
        "capture_path": capture_path,
        "capture": capture,
        "board_path": board_path,
        "survey_path": survey_path,
        "survey": survey,
        "intrinsics": intrinsics,
        "distortion": distortion,
        "a_path": a_path,
        "b_path": b_path,
        "a": a,
        "b": b,
    }


def _finalize(fixture: dict[str, object], output: Path) -> dict[str, object]:
    return acquisition.finalize_metric_registration_input(
        capture_receipt_path=Path(fixture["capture_path"]),
        annotator_a_path=Path(fixture["a_path"]),
        annotator_b_path=Path(fixture["b_path"]),
        board_measurement_path=Path(fixture["board_path"]),
        survey_path=Path(fixture["survey_path"]),
        intrinsics_path=Path(fixture["intrinsics"]),
        distortion_path=Path(fixture["distortion"]),
        output_path=output,
        repo_root=Path(fixture["root"]),
    )


def test_fake_capture_selects_sharpest_frame_and_seals_lineage(tmp_path: Path) -> None:
    fixture = _captured(tmp_path)
    receipt = json.loads(Path(fixture["result"]["capture_receipt_path"]).read_text())
    extraction_path = (
        Path(fixture["root"])
        / receipt["frame_extraction_receipt"]["artifact_path"]
    )
    extraction = json.loads(extraction_path.read_text())
    assert extraction["source_frame_index"] == 5
    assert extraction["selection_rule"].startswith("maximum_laplacian")
    assert extraction["output_frame_sha256"] == receipt["selected_frame_sha256"]
    assert receipt["robot_gateway_constructed"] is False
    assert receipt["robot_motion_used"] == 0


def test_cli_exposes_capture_and_finalize_phases() -> None:
    capture = build_parser().parse_args(
        [
            "workcell-registration-input",
            "--phase",
            "capture",
            "--output",
            "runs/registration-capture",
            "--dry-run",
        ]
    )
    finalize = build_parser().parse_args(
        [
            "workcell-registration-input",
            "--phase",
            "finalize",
            "--output",
            "runs/registration-inputs.json",
        ]
    )
    assert capture.phase == "capture" and capture.dry_run is True
    assert finalize.phase == "finalize"


def test_dry_run_never_calls_native_and_cannot_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        acquisition,
        "_native_backend",
        lambda _: (_ for _ in ()).throw(AssertionError("hardware opened")),
    )
    fixture = _captured(tmp_path, synthetic=True)
    receipt = json.loads(Path(fixture["result"]["capture_receipt_path"]).read_text())
    assert receipt["synthetic"] is True
    assert receipt["evaluator_owned"] is False
    with pytest.raises(registration.WorkcellRegistrationError, match="synthetic"):
        acquisition.finalize_metric_registration_input(
            capture_receipt_path=Path(fixture["result"]["capture_receipt_path"]),
            annotator_a_path=Path(
                fixture["result"]["annotation_bundle"]["annotation_templates"][
                    "annotator_a"
                ]
            ),
            annotator_b_path=Path(
                fixture["result"]["annotation_bundle"]["annotation_templates"][
                    "annotator_b"
                ]
            ),
            board_measurement_path=Path(fixture["root"]) / "missing-board.json",
            survey_path=Path(fixture["root"]) / "missing-survey.json",
            intrinsics_path=Path(fixture["root"]) / "missing-intrinsics.json",
            distortion_path=Path(fixture["root"]) / "missing-distortion.json",
            output_path=Path(fixture["root"]) / "runs/finalized.json",
            repo_root=Path(fixture["root"]),
        )


def test_real_capture_acknowledgements_fail_before_backend(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    selector = root / "selector.py"
    selector.write_text("# fixture")
    with pytest.raises(registration.WorkcellRegistrationError, match="acknowledgement"):
        acquisition.capture_stationary_bundle(
            root / "runs/capture",
            acknowledgements={name: False for name in acquisition.ACKNOWLEDGEMENTS},
            focus_setting="locked",
            capture_backend=lambda _: (_ for _ in ()).throw(
                AssertionError("backend opened")
            ),
            repo_root=root,
            selector_path=selector,
        )


def test_finalize_merges_independent_annotations_into_existing_schema(tmp_path: Path) -> None:
    fixture = _finalize_fixture(tmp_path)
    output = Path(fixture["root"]) / "runs/finalized/metric_registration_inputs.json"
    result = _finalize(fixture, output)
    manifest = json.loads(output.read_text())
    assert manifest["schema_version"] == "sim2claw.metric_registration_inputs.v1"
    assert result["point_count"] == 8
    assert result["annotator_ids"] == ["alice", "bob"]
    assert manifest["physical_source"]["proof_class"] == "physical_camera_frame"
    assert all(
        len(row["annotations"]) == 2
        and row["annotations"][0]["annotator_id"]
        != row["annotations"][1]["annotator_id"]
        for row in manifest["metric_measurements"]["board_correspondences"]
    )
    assert manifest["metric_measurements"]["board_fit_evaluation"] is None
    assert manifest["metric_measurements"]["overhead_camera_to_workcell_transform"] is None


def test_finalized_manifest_is_consumed_by_p13(tmp_path: Path) -> None:
    fixture = _finalize_fixture(tmp_path)
    manifest = Path(fixture["root"]) / "runs/finalized/metric_registration_inputs.json"
    _finalize(fixture, manifest)
    evaluator = Path(fixture["root"]) / "tools/workcell_registration.py"
    shutil.copy2(Path(registration.__file__), evaluator)
    result = registration.evaluate_stationary_registration(
        survey_path=Path(fixture["survey_path"]),
        manifest_path=manifest,
        output_directory=Path(fixture["root"]) / "runs/p13-evaluation",
        repo_root=Path(fixture["root"]),
        evaluator_path=evaluator,
    )
    assert result["status"] == "stationary_camera_to_workcell_registration_verified"
    assert Path(result["transform_receipt_path"]).is_file()


def test_same_or_copied_annotator_rejected(tmp_path: Path) -> None:
    fixture = _finalize_fixture(tmp_path)
    fixture["b"]["annotator_id"] = "alice"
    Path(fixture["b_path"]).unlink()
    _write(Path(fixture["b_path"]), fixture["b"])
    with pytest.raises(registration.WorkcellRegistrationError, match="identities"):
        _finalize(fixture, Path(fixture["root"]) / "runs/rejected.json")
    with pytest.raises(registration.WorkcellRegistrationError, match="byte-identical"):
        acquisition.finalize_metric_registration_input(
            capture_receipt_path=Path(fixture["capture_path"]),
            annotator_a_path=Path(fixture["a_path"]),
            annotator_b_path=Path(fixture["a_path"]),
            board_measurement_path=Path(fixture["board_path"]),
            survey_path=Path(fixture["survey_path"]),
            intrinsics_path=Path(fixture["intrinsics"]),
            distortion_path=Path(fixture["distortion"]),
            output_path=Path(fixture["root"]) / "runs/copied.json",
            repo_root=Path(fixture["root"]),
        )


@pytest.mark.parametrize(
    "mutation",
    ("point", "quadrant", "pixel", "survey", "review", "board", "frame", "mode"),
)
def test_finalize_rejects_incomplete_or_drifted_inputs(
    tmp_path: Path, mutation: str
) -> None:
    fixture = _finalize_fixture(tmp_path)
    if mutation == "point":
        fixture["a"]["points"].pop()
        Path(fixture["a_path"]).unlink()
        _write(Path(fixture["a_path"]), fixture["a"])
        match = "points changed"
    elif mutation == "quadrant":
        fixture["a"]["points"][0]["board_quadrant"] = "north_east"
        Path(fixture["a_path"]).unlink()
        _write(Path(fixture["a_path"]), fixture["a"])
        match = "point identity"
    elif mutation == "pixel":
        fixture["a"]["points"][0]["pixel_xy"] = [640.0, 20.0]
        Path(fixture["a_path"]).unlink()
        _write(Path(fixture["a_path"]), fixture["a"])
        match = "pixel bounds"
    elif mutation == "survey":
        fixture["survey"]["frame_convention"]["physical_a1_marker"] = None
        Path(fixture["survey_path"]).unlink()
        _write(Path(fixture["survey_path"]), fixture["survey"])
        match = "a1, h1, and a8"
    elif mutation == "review":
        fixture["survey"]["independent_review"]["decision"] = "pending"
        Path(fixture["survey_path"]).unlink()
        _write(Path(fixture["survey_path"]), fixture["survey"])
        match = "independent accepting review"
    elif mutation == "board":
        board = json.loads(Path(fixture["board_path"]).read_text())
        board["nominal_value_substituted"] = True
        Path(fixture["board_path"]).unlink()
        _write(Path(fixture["board_path"]), board)
        match = "nominal"
    elif mutation == "frame":
        frame = Path(fixture["root"]) / fixture["capture"]["selected_frame_path"]
        frame.write_bytes(b"drift")
        match = "hash changed"
    else:
        fixture["capture"]["exact_mode"]["format_index"] = 15
        Path(fixture["capture_path"]).unlink()
        _write(Path(fixture["capture_path"]), fixture["capture"])
        match = "wrong-mode"
    with pytest.raises(registration.WorkcellRegistrationError, match=match):
        _finalize(fixture, Path(fixture["root"]) / f"runs/{mutation}.json")


def test_output_overwrite_rejected(tmp_path: Path) -> None:
    fixture = _finalize_fixture(tmp_path)
    output = Path(fixture["root"]) / "runs/finalized.json"
    _finalize(fixture, output)
    with pytest.raises(registration.WorkcellRegistrationError, match="already exists"):
        _finalize(fixture, output)
