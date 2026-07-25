from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from sim2claw import c922_exact_mode_calibration as calibration


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(calibration.REPO_ROOT.resolve()))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace() -> tempfile.TemporaryDirectory[str]:
    (calibration.REPO_ROOT / "outputs").mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(
        prefix="test-c922-calibration-",
        dir=calibration.REPO_ROOT / "outputs",
    )


def _base_manifest(contract: dict[str, object]) -> dict[str, object]:
    camera = copy.deepcopy(contract["camera"])
    assert isinstance(camera, dict)
    camera["focus_setting"] = "manual_locked_42"
    return {
        "schema_version": calibration.INPUT_SCHEMA,
        "dataset_id": "test-c922-dataset",
        "camera": camera,
        "target": {
            "asset_path": contract["target"]["asset_path"],  # type: ignore[index]
            "asset_sha256": contract["target"]["asset_sha256"],  # type: ignore[index]
            "printed_grid_measurement_receipt": None,
        },
        "splits_frozen_before_fit": True,
        "frames": [],
    }


def _pose_corners(
    target_fraction: tuple[float, float],
    *,
    depth: float,
    rotation_degrees: tuple[float, float, float],
) -> np.ndarray:
    matrix = np.array(
        [[600.0, 0.0, 320.0], [0.0, 600.0, 240.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    points = calibration._object_points((9, 6)).astype(np.float64)
    center = np.array([4.0, 2.5, 0.0], dtype=np.float64)
    target = np.array(
        [target_fraction[0] * 640.0, target_fraction[1] * 480.0],
        dtype=np.float64,
    )
    desired_camera_center = np.array(
        [
            (target[0] - 320.0) * depth / 600.0,
            (target[1] - 240.0) * depth / 600.0,
            depth,
        ],
        dtype=np.float64,
    )
    rotation = np.radians(np.asarray(rotation_degrees, dtype=np.float64))
    rotation_matrix, _ = cv2.Rodrigues(rotation)
    translation = desired_camera_center - rotation_matrix @ center
    projected, _ = cv2.projectPoints(
        points,
        rotation,
        translation,
        matrix,
        np.zeros(5, dtype=np.float64),
    )
    return projected.reshape(-1, 2).astype(np.float32)


POSES = [
    ((0.23, 0.23), 26.0, (0.0, 0.0, -20.0)),
    ((0.77, 0.23), 26.0, (25.0, 0.0, 20.0)),
    ((0.23, 0.77), 26.0, (0.0, 25.0, -20.0)),
    ((0.77, 0.77), 26.0, (0.0, 0.0, 20.0)),
    ((0.50, 0.50), 11.0, (0.0, 0.0, 0.0)),
    ((0.50, 0.50), 17.0, (25.0, 0.0, 0.0)),
    ((0.50, 0.50), 17.0, (0.0, 25.0, 0.0)),
    ((0.50, 0.50), 26.0, (-25.0, 0.0, 0.0)),
    ((0.50, 0.50), 11.0, (0.0, 0.0, 20.0)),
    ((0.50, 0.50), 17.0, (0.0, 0.0, -20.0)),
    ((0.24, 0.24), 18.0, (20.0, 0.0, 0.0)),
    ((0.76, 0.76), 18.0, (0.0, -20.0, 0.0)),
    ((0.76, 0.24), 24.0, (-20.0, 0.0, -15.0)),
    ((0.24, 0.76), 24.0, (0.0, 20.0, 15.0)),
    ((0.50, 0.50), 15.0, (0.0, 0.0, 0.0)),
    ((0.24, 0.24), 25.0, (15.0, 0.0, 18.0)),
    ((0.76, 0.76), 25.0, (0.0, -15.0, -18.0)),
    ((0.50, 0.50), 13.0, (20.0, 10.0, 0.0)),
]


def _dataset(
    root: Path,
    contract: dict[str, object],
    *,
    duplicate_last: bool = False,
    caller_corners_index: int | None = None,
    mode_substitution_index: int | None = None,
    focus_substitution_index: int | None = None,
    malformed_index: int | None = None,
) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    root.mkdir(parents=True, exist_ok=True)
    manifest = _base_manifest(contract)
    frames = manifest["frames"]
    assert isinstance(frames, list)
    corners_by_name: dict[str, np.ndarray] = {}
    for index, pose in enumerate(POSES):
        split = "fit" if index < 12 else "validation" if index < 15 else "held_out"
        image = root / f"frame-{index:02d}.png"
        if duplicate_last and index == len(POSES) - 1:
            image.write_bytes((root / "frame-00.png").read_bytes())
        elif malformed_index == index:
            image.write_bytes(b"not-a-png")
        else:
            pixels = np.full((480, 640, 3), 255, dtype=np.uint8)
            pixels[0, index, :] = np.array([index, 255 - index, index], dtype=np.uint8)
            Image.fromarray(pixels, mode="RGB").save(image)
        corners_by_name[image.name] = _pose_corners(
            pose[0],
            depth=pose[1],
            rotation_degrees=pose[2],
        )
        camera = copy.deepcopy(contract["camera"])
        assert isinstance(camera, dict)
        if mode_substitution_index == index:
            camera["format_index"] = 99
        receipt = {
            "schema_version": calibration.FRAME_RECEIPT_SCHEMA,
            "frame_id": f"frame-{index:02d}",
            "split": split,
            "camera": camera,
            "focus_setting": (
                "autofocus_changed"
                if focus_substitution_index == index
                else "manual_locked_42"
            ),
            "image_path": _relative(image),
            "image_sha256": _sha(image),
            "source_pts_seconds": float(index),
            "caller_supplied_corners": (
                [[1.0, 2.0]] if caller_corners_index == index else None
            ),
            "capture_authority": "physical_camera_frame",
            "synthetic": False,
        }
        receipt_path = root / f"frame-{index:02d}-receipt.json"
        _write_json(receipt_path, receipt)
        frames.append(
            {
                "frame_id": receipt["frame_id"],
                "split": split,
                "receipt_path": _relative(receipt_path),
                "receipt_sha256": _sha(receipt_path),
            }
        )
    return manifest, corners_by_name


def _detector(corners_by_name: dict[str, np.ndarray]):
    def detect(
        image_path: Path,
        inner_corners: tuple[int, int],
        expected_size: tuple[int, int],
    ) -> np.ndarray:
        assert inner_corners == (9, 6)
        assert expected_size == (640, 480)
        try:
            with Image.open(image_path) as image:
                assert image.size == expected_size
                image.verify()
        except Exception as error:
            raise calibration.C922CalibrationError(
                f"Frame image is malformed: {error}"
            ) from error
        return corners_by_name[image_path.name]

    return detect


def test_contract_target_models_and_software_only_budget_are_frozen() -> None:
    contract = calibration.load_contract()
    assert calibration.sha256_file(calibration.DEFAULT_CONTRACT_PATH) == calibration.CONTRACT_SHA256
    target = calibration.REPO_ROOT / contract["target"]["asset_path"]
    assert calibration.sha256_file(target) == contract["target"]["asset_sha256"]
    assert contract["dataset"]["required_split_counts"] == {
        "fit": 12,
        "validation": 3,
        "held_out": 3,
    }
    assert contract["models"]["candidates"] == [
        "opencv_pinhole_zero_distortion",
        "opencv_pinhole_k1_k2_p1_p2_k3",
    ]
    assert contract["budgets"] == {
        "dataset_evaluations_maximum": 1,
        "model_fits_maximum": 2,
        "camera_sessions_maximum": 0,
        "new_camera_frames_maximum": 0,
        "robot_motions_maximum": 0,
        "simulator_replays_maximum": 0,
        "provider_calls_maximum": 0,
        "training_rows_maximum": 0,
    }


def test_pending_manifest_materializes_byte_identical_not_ready_without_receipts() -> None:
    with _workspace() as directory:
        output = Path(directory) / "result"
        first = calibration.materialize(output_root=output)
        second = calibration.materialize(output_root=output)
        assert first == second
        assert first["verdict"] == "calibration_dataset_not_ready"
        assert first["receipt_path"] is None
        assert first["intrinsics_path"] is None
        assert first["distortion_path"] is None
        evaluation = json.loads(Path(first["evaluation_path"]).read_text())
        assert evaluation["model_budget"]["used"] == 0
        assert evaluation["readiness"]["accepted_frame_count"] == 0
        assert evaluation["readiness"]["missing_prerequisites"] == [
            "constant_focus_setting",
            "fit_split_count",
            "held_out_split_count",
            "minimum_accepted_frames",
            "minimum_near_frontal_views",
            "minimum_orientation_bins",
            "minimum_scale_bins",
            "minimum_tilted_views",
            "required_centroid_bins",
            "validation_split_count",
        ]
        stale = Path(first["output_root"]) / "receipt.json"
        stale.write_text("{}\n", encoding="utf-8")
        with pytest.raises(
            calibration.C922CalibrationError,
            match="stale calibration artifact",
        ):
            calibration.materialize(output_root=output)


def test_real_detector_reads_image_bytes_and_rejects_malformed_image() -> None:
    with _workspace() as directory:
        root = Path(directory)
        pixels = np.full((480, 640), 255, dtype=np.uint8)
        square = 40
        origin_x, origin_y = 120, 100
        for row in range(7):
            for column in range(10):
                if (row + column) % 2 == 0:
                    pixels[
                        origin_y + row * square : origin_y + (row + 1) * square,
                        origin_x + column * square : origin_x + (column + 1) * square,
                    ] = 0
        image = root / "checkerboard.png"
        Image.fromarray(pixels, mode="L").save(image)
        corners = calibration.detect_corners(image, (9, 6), (640, 480))
        assert corners is not None
        assert corners.shape == (54, 2)
        malformed = root / "malformed.png"
        malformed.write_bytes(b"not-a-png")
        with pytest.raises(calibration.C922CalibrationError, match="malformed"):
            calibration.detect_corners(malformed, (9, 6), (640, 480))


def test_complete_public_dataset_executes_two_models_and_passes_held_out() -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        root = Path(directory)
        manifest, corners = _dataset(root, contract)
        evaluation = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="a" * 64,
            detector=_detector(corners),
        )
        assert evaluation["verdict"] == "exact_mode_intrinsics_and_distortion_verified"
        assert evaluation["model_budget"] == {"maximum": 2, "used": 2}
        assert evaluation["readiness"]["split_counts"] == {
            "fit": 12,
            "validation": 3,
            "held_out": 3,
        }
        assert evaluation["readiness"]["rejected_frame_count"] == 0
        assert evaluation["fit_metrics"]["rms_px"] < 0.01
        assert evaluation["validation_metrics"]["rms_px"] < 0.01
        assert evaluation["held_out_metrics"]["rms_px"] < 0.01
        assert all(row["passed"] for row in evaluation["gates"])


def test_pass_materialization_emits_metric_readiness_compatible_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        root = Path(directory)
        manifest, corners = _dataset(root, contract)
        manifest_path = root / "manifest.json"
        _write_json(manifest_path, manifest)
        monkeypatch.setattr(calibration, "detect_corners", _detector(corners))
        result = calibration.materialize(
            input_path=manifest_path,
            output_root=root / "result",
        )
        assert result["verdict"] == "exact_mode_intrinsics_and_distortion_verified"
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        intrinsics = json.loads(Path(result["intrinsics_path"]).read_text())
        distortion = json.loads(Path(result["distortion_path"]).read_text())
        assert receipt["accepted_frame_count"] == 18
        assert receipt["model_fits_used"] == 2
        assert receipt["camera_sessions_used"] == 0
        assert intrinsics["schema_version"] == calibration.INTRINSICS_SCHEMA
        assert intrinsics["camera_id"] == "logitech-overhead"
        assert intrinsics["image_size_px"] == [640, 480]
        assert intrinsics["evaluator_owned"] is True
        assert intrinsics["self_scored"] is False
        assert distortion["schema_version"] == calibration.DISTORTION_SCHEMA
        assert len(distortion["coefficients"]) >= 4
        assert distortion["metric_scale_claimed"] is False


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"duplicate_last": True}, "Duplicate/replayed frame bytes"),
        ({"caller_corners_index": 4}, "Caller-supplied corners"),
        ({"mode_substitution_index": 5}, "exact-mode identity changed"),
        ({"focus_substitution_index": 5}, "focus setting changed"),
        ({"malformed_index": 6}, "malformed"),
    ],
)
def test_invalid_or_substituted_frames_fail_closed(
    kwargs: dict[str, object],
    reason: str,
) -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        manifest, corners = _dataset(Path(directory), contract, **kwargs)
        evaluation = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="b" * 64,
            detector=_detector(corners),
        )
        assert evaluation["verdict"] == "calibration_evaluator_reject"
        assert any(reason in row["reason"] for row in evaluation["readiness"]["rejected_frames"])
        assert evaluation["model_budget"]["used"] == 0
        assert evaluation["held_out_metrics"] is None


def test_split_mutation_and_insufficient_diversity_never_fit() -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        root = Path(directory)
        manifest, corners = _dataset(root, contract)
        frames = manifest["frames"]
        assert isinstance(frames, list)
        frames.pop()
        evaluation = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="c" * 64,
            detector=_detector(corners),
        )
        assert evaluation["verdict"] == "calibration_dataset_not_ready"
        assert "held_out_split_count" in evaluation["readiness"]["missing_prerequisites"]
        assert evaluation["model_budget"]["used"] == 0

        manifest, corners = _dataset(root / "second", contract)
        one_view = _pose_corners((0.5, 0.5), depth=17.0, rotation_degrees=(0.0, 0.0, 0.0))
        detector = _detector({name: one_view for name in corners})
        evaluation = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="d" * 64,
            detector=detector,
        )
        assert evaluation["verdict"] == "calibration_dataset_not_ready"
        missing = evaluation["readiness"]["missing_prerequisites"]
        assert "required_centroid_bins" in missing
        assert "minimum_scale_bins" in missing
        assert "minimum_tilted_views" in missing
        assert "minimum_orientation_bins" in missing
        assert evaluation["model_budget"]["used"] == 0


def test_held_out_changes_cannot_change_validation_selected_model() -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        manifest, corners = _dataset(Path(directory), contract)
        first = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="e" * 64,
            detector=_detector(corners),
        )
        altered = {
            name: (
                values
                if not name.startswith(("frame-15", "frame-16", "frame-17"))
                else values
                + np.column_stack(
                    [
                        np.linspace(-0.4, 0.4, len(values)),
                        np.linspace(0.4, -0.4, len(values)),
                    ]
                ).astype(np.float32)
            )
            for name, values in corners.items()
        }
        second = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="f" * 64,
            detector=_detector(altered),
        )
        assert first["selected_model"]["model_id"] == second["selected_model"]["model_id"]
        assert (
            first["selected_model"]["validation_rms_improvement_px_for_distortion_model"]
            == second["selected_model"]["validation_rms_improvement_px_for_distortion_model"]
        )
        assert first["held_out_metrics"] != second["held_out_metrics"]


def test_path_escape_contract_mutation_and_output_replay_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = calibration.load_contract()
    with _workspace() as directory:
        root = Path(directory)
        manifest, corners = _dataset(root, contract)
        first_receipt = calibration.REPO_ROOT / manifest["frames"][0]["receipt_path"]
        receipt = json.loads(first_receipt.read_text())
        receipt["image_path"] = "../../outside.png"
        _write_json(first_receipt, receipt)
        manifest["frames"][0]["receipt_sha256"] = _sha(first_receipt)
        evaluation = calibration._evaluate_manifest(
            contract,
            manifest,
            input_sha256="1" * 64,
            detector=_detector(corners),
        )
        assert evaluation["verdict"] == "calibration_evaluator_reject"
        assert "escapes repository" in evaluation["readiness"]["rejected_frames"][0]["reason"]

        mutated_contract = root / "mutated-contract.json"
        changed = copy.deepcopy(contract)
        changed["acceptance"]["maximum_held_out_rms_px"] = 999.0
        _write_json(mutated_contract, changed)
        with pytest.raises(calibration.C922CalibrationError, match="identity changed"):
            calibration.load_contract(mutated_contract)

        manifest, corners = _dataset(root / "replay", contract)
        manifest_path = root / "replay-manifest.json"
        _write_json(manifest_path, manifest)
        monkeypatch.setattr(calibration, "detect_corners", _detector(corners))
        result = calibration.materialize(
            input_path=manifest_path,
            output_root=root / "materialized",
        )
        Path(result["evaluation_path"]).write_text("{}\n", encoding="utf-8")
        with pytest.raises(calibration.C922CalibrationError, match="not byte-identical"):
            calibration.materialize(
                input_path=manifest_path,
                output_root=root / "materialized",
            )
