from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

import sim2claw.metric_registration_readiness as readiness


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "configs/evaluations/current_100mm_metric_registration_readiness_v1.json"
)
MANIFEST_PATH = (
    ROOT / "configs/evaluations/current_100mm_metric_registration_inputs_v1.json"
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pointer(path: Path, root: Path) -> dict[str, str]:
    return {
        "artifact_path": str(path.relative_to(root)),
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _source_repo(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    root = tmp_path / "repo"
    video = root / "evidence/overhead.mp4"
    frame = root / "evidence/frame.png"
    receipt = root / "evidence/capture.json"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"content-addressed-video")
    Image.new("RGB", (640, 480), (30, 40, 50)).save(frame)
    video_sha = hashlib.sha256(video.read_bytes()).hexdigest()
    frame_sha = hashlib.sha256(frame.read_bytes()).hexdigest()
    capture = {
        "proof_class": "physical_command_replay_observation_unqualified_dual_camera",
        "promotion_authority": False,
        "training_admission": False,
        "camera_reports": [
            {
                "id": "logitech-overhead",
                "name": "C922 Pro Stream Webcam",
                "role": "overhead_workspace",
                "filter": "hflip,vflip",
                "status": "completed_full_timestamp_coverage",
                "sha256": video_sha,
                "size": "640x480",
            }
        ],
    }
    receipt_sha = _write_json(receipt, capture)
    manifest = {
        "schema_version": readiness.INPUT_SCHEMA,
        "input_id": "synthetic-completeness-test",
        "physical_source": {
            "capture_receipt_path": str(receipt.relative_to(root)),
            "capture_receipt_sha256": receipt_sha,
            "overhead_video_path": str(video.relative_to(root)),
            "overhead_video_sha256": video_sha,
            "source_frame_path": str(frame.relative_to(root)),
            "source_frame_sha256": frame_sha,
            "source_frame_size_px": [640, 480],
            "frame_extraction_receipt": None,
            "camera_id": "logitech-overhead",
            "camera_name": "C922 Pro Stream Webcam",
            "camera_role": "overhead_workspace",
            "capture_orientation_filter": "hflip,vflip",
            "proof_class": "physical_command_replay_observation_unqualified_dual_camera",
        },
        "metric_measurements": {
            "board_playing_side": None,
            "camera_intrinsics_receipt": None,
            "lens_distortion_receipt": None,
            "board_correspondences": [],
            "board_fit_evaluation": None,
            "object_keypoint_observations": [],
            "overhead_camera_to_workcell_transform": None,
            "wrist_camera_extrinsics": None,
        },
        "authority": {
            "nominal_board_size_is_measurement": False,
            "proposal_homography_is_metric_calibration": False,
            "synthetic_values_allowed": False,
            "training_rows_authorized": 0,
            "promotion_authority": False,
            "physical_motion_authority": False,
            "task_success_verified": False,
        },
    }
    return manifest, {"root": root, "video_sha": video_sha, "frame_sha": frame_sha}


def _complete_manifest(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    contract = _load(CONTRACT_PATH)
    manifest, evidence = _source_repo(tmp_path)
    root = evidence["root"]
    assert isinstance(root, Path)
    frame_sha = evidence["frame_sha"]
    video_sha = evidence["video_sha"]
    artifacts = root / "artifacts"
    tools = root / "tools"
    tools.mkdir(parents=True)
    decoder = tools / "decoder"
    decoder.write_bytes(b"reviewed-decoder-binary")
    evaluator = tools / "board-fit-evaluator"
    evaluator.write_bytes(b"independent-board-fit-evaluator")
    decoder_identity = {
        "name": "test-decoder",
        "version": "1.0",
        "executable_path": str(decoder.relative_to(root)),
        "executable_sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
    }
    evaluator_identity = {
        "name": "test-board-fit-evaluator",
        "version": "1.0",
        "executable_path": str(evaluator.relative_to(root)),
        "executable_sha256": hashlib.sha256(evaluator.read_bytes()).hexdigest(),
    }
    extraction = artifacts / "extraction.json"
    _write_json(
        extraction,
        {
            "schema_version": "sim2claw.frame_extraction_receipt.v1",
            "source_video_sha256": video_sha,
            "source_timestamp_seconds": 0.0,
            "decoder_identity": decoder_identity,
            "orientation_filter": "hflip,vflip",
            "output_frame_sha256": frame_sha,
        },
    )
    board = artifacts / "board.json"
    _write_json(
        board,
        {
            "schema_version": "sim2claw.direct_board_measurement_receipt.v1",
            "measurement_method": "direct_physical_measurement",
            "playing_side_m": 0.3556,
            "standard_uncertainty_m": 0.0002,
            "measurement_tool_id": "traceable-caliper-001",
            "nominal_value_substituted": False,
            "synthetic": False,
        },
    )
    intrinsics = artifacts / "intrinsics.json"
    _write_json(
        intrinsics,
        {
            "schema_version": "sim2claw.camera_intrinsics_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "camera_matrix": [[600.0, 0.0, 320.0], [0.0, 600.0, 240.0], [0.0, 0.0, 1.0]],
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    distortion = artifacts / "distortion.json"
    _write_json(
        distortion,
        {
            "schema_version": "sim2claw.lens_distortion_receipt.v1",
            "camera_id": "logitech-overhead",
            "image_size_px": [640, 480],
            "model": "opencv_rational",
            "coefficients": [0.1, -0.2, 0.0, 0.0, 0.01],
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    board_points = [
        (-0.12, 0.12, "north_west"),
        (-0.04, 0.04, "north_west"),
        (0.04, 0.04, "north_east"),
        (0.12, 0.12, "north_east"),
        (-0.12, -0.12, "south_west"),
        (-0.04, -0.04, "south_west"),
        (0.04, -0.04, "south_east"),
        (0.12, -0.12, "south_east"),
    ]
    correspondences = []
    for index, (board_x, board_y, quadrant) in enumerate(board_points):
        correspondences.append(
            {
                "point_id": f"grid-{index}",
                "board_xy_m": [board_x, board_y],
                "board_quadrant": quadrant,
                "source_frame_sha256": frame_sha,
                "synthetic": False,
                "annotations": [
                    {"annotator_id": "annotator-a", "pixel_xy": [100.0 + index, 200.0]},
                    {"annotator_id": "annotator-b", "pixel_xy": [100.2 + index, 200.1]},
                ],
            }
        )
    board_fit = artifacts / "board-fit.json"
    _write_json(
        board_fit,
        {
            "schema_version": "sim2claw.board_fit_evaluation_receipt.v1",
            "evaluation_method": "leave_one_out",
            "board_rms_m": 0.001,
            "max_annotator_disagreement_m": 0.0003,
            "point_ids": [f"grid-{index}" for index in range(8)],
            "evaluator_owned": True,
            "self_scored": False,
            "uncertainty_propagated": True,
            "evaluator_identity": evaluator_identity,
            "source_frame_sha256": frame_sha,
            "correspondences_digest": readiness.canonical_digest(correspondences),
            "thresholds_digest": readiness.canonical_digest(
                contract["readiness_thresholds"]
            ),
        },
    )
    overhead = artifacts / "overhead-transform.json"
    transform = [
        [1.0, 0.0, 0.0, 0.1],
        [0.0, 1.0, 0.0, 0.2],
        [0.0, 0.0, 1.0, 0.3],
        [0.0, 0.0, 0.0, 1.0],
    ]
    _write_json(
        overhead,
        {
            "schema_version": "sim2claw.camera_to_workcell_transform_receipt.v1",
            "camera_id": "logitech-overhead",
            "transform_4x4": transform,
            "translation_uncertainty_95_m": 0.001,
            "rotation_uncertainty_95_degrees": 0.1,
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    wrist = artifacts / "wrist-transform.json"
    _write_json(
        wrist,
        {
            "schema_version": "sim2claw.wrist_camera_extrinsics_receipt.v1",
            "camera_role": "wrist_gripper_upward",
            "transform_4x4": transform,
            "translation_uncertainty_95_m": 0.001,
            "rotation_uncertainty_95_degrees": 0.1,
            "evaluator_owned": True,
            "self_scored": False,
        },
    )
    values = manifest["metric_measurements"]
    assert isinstance(values, dict)
    values.update(
        {
            "board_playing_side": _pointer(board, root),
            "camera_intrinsics_receipt": _pointer(intrinsics, root),
            "lens_distortion_receipt": _pointer(distortion, root),
            "board_correspondences": correspondences,
            "board_fit_evaluation": _pointer(board_fit, root),
            "object_keypoint_observations": [
                {
                    "object_id": "pawn-c2",
                    "base_center_board_xy_m": [0.11, 0.07],
                    "uncertainty_95_m": 0.001,
                    "source_frame_sha256": frame_sha,
                    "independently_reviewed": True,
                    "synthetic": False,
                }
            ],
            "overhead_camera_to_workcell_transform": _pointer(overhead, root),
            "wrist_camera_extrinsics": _pointer(wrist, root),
        }
    )
    manifest["physical_source"]["frame_extraction_receipt"] = _pointer(
        extraction, root
    )
    return contract, manifest, evidence


def test_frozen_current_manifest_fails_closed_with_exact_missing_inputs() -> None:
    contract = _load(CONTRACT_PATH)
    manifest = _load(MANIFEST_PATH)
    result = readiness.evaluate_manifest(contract, manifest, repo_root=ROOT)
    assert result["verdict"] == "measurement_prerequisites_missing"
    assert result["source_valid"] is True
    assert result["invalid_inputs"] == []
    assert result["missing_prerequisites"] == [
        "all_four_board_quadrants",
        "direct_board_measurement",
        "exact_mode_camera_intrinsics",
        "frame_extraction_lineage",
        "independent_board_fit_evaluation",
        "lens_distortion_control",
        "metric_object_keypoints_with_uncertainty",
        "minimum_independent_board_correspondences",
        "overhead_camera_to_workcell_transform",
        "wrist_camera_extrinsics",
    ]
    assert result["budget"]["camera_sessions_used"] == 0
    assert result["authority"]["twin_fidelity_changed"] is False


def test_complete_independently_owned_measurements_pass_readiness_only(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    result = readiness.evaluate_manifest(
        contract, manifest, repo_root=evidence["root"]
    )
    assert result["verdict"] == "ready_for_separately_owned_metric_fit"
    assert result["missing_prerequisites"] == []
    assert result["invalid_inputs"] == []
    assert all(result["readiness_gates"].values())
    assert result["authority"]["metric_calibration_claimed"] is False
    assert result["authority"]["geometry_scale_domain_change_authorized"] is False


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("source_hash", "source:overhead_video_sha256"),
        ("nominal_board", "direct_board_measurement:not_direct_traceable_measurement"),
        ("missing_distortion", "lens_distortion_control"),
        (
            "one_annotator",
            "minimum_independent_board_correspondences:malformed_nonindependent_or_not_spatial",
        ),
        (
            "three_quadrants",
            "all_four_board_quadrants:malformed_nonindependent_or_not_spatial",
        ),
        (
            "self_scored_fit",
            "independent_board_fit_evaluation:threshold_or_ownership_invalid",
        ),
        (
            "bad_uncertainty",
            "overhead_camera_to_workcell_transform:identity_transform_or_ownership_invalid",
        ),
    ],
)
def test_adversarial_measurement_or_source_substitution_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    values = manifest["metric_measurements"]
    assert isinstance(values, dict)
    root = evidence["root"]
    assert isinstance(root, Path)
    if mutation == "source_hash":
        manifest["physical_source"]["overhead_video_sha256"] = "0" * 64
    elif mutation == "nominal_board":
        pointer = values["board_playing_side"]
        artifact = _load(root / pointer["artifact_path"])
        artifact["measurement_method"] = "nominal_product_dimension"
        pointer["artifact_sha256"] = _write_json(
            root / pointer["artifact_path"], artifact
        )
    elif mutation == "missing_distortion":
        values["lens_distortion_receipt"] = None
    elif mutation == "one_annotator":
        for row in values["board_correspondences"]:
            row["annotations"] = row["annotations"][:1]
    elif mutation == "three_quadrants":
        for row in values["board_correspondences"]:
            if row["board_quadrant"] == "south_east":
                row["board_quadrant"] = "south_west"
    elif mutation == "self_scored_fit":
        pointer = values["board_fit_evaluation"]
        artifact = _load(root / pointer["artifact_path"])
        artifact["self_scored"] = True
        pointer["artifact_sha256"] = _write_json(
            root / pointer["artifact_path"], artifact
        )
    elif mutation == "bad_uncertainty":
        pointer = values["overhead_camera_to_workcell_transform"]
        artifact = _load(root / pointer["artifact_path"])
        artifact["translation_uncertainty_95_m"] = 0.0
        pointer["artifact_sha256"] = _write_json(
            root / pointer["artifact_path"], artifact
        )
    result = readiness.evaluate_manifest(contract, manifest, repo_root=root)
    assert result["verdict"] != "ready_for_separately_owned_metric_fit"
    assert expected in result["invalid_inputs"] + result["missing_prerequisites"]


def test_path_escape_and_receipt_camera_substitution_are_invalid(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    root = evidence["root"]
    assert isinstance(root, Path)
    escaped = copy.deepcopy(manifest)
    escaped["physical_source"]["source_frame_path"] = "../outside.png"
    result = readiness.evaluate_manifest(contract, escaped, repo_root=root)
    assert "source:source_frame_path" in result["invalid_inputs"]

    substituted = copy.deepcopy(manifest)
    receipt_path = root / substituted["physical_source"]["capture_receipt_path"]
    receipt = _load(receipt_path)
    receipt["camera_reports"][0]["id"] = "another-camera"
    substituted["physical_source"]["capture_receipt_sha256"] = _write_json(
        receipt_path, receipt
    )
    result = readiness.evaluate_manifest(contract, substituted, repo_root=root)
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert "source:receipt_camera_match" in result["invalid_inputs"]


def test_manifest_authority_cannot_self_promote() -> None:
    contract = _load(CONTRACT_PATH)
    manifest = _load(MANIFEST_PATH)
    manifest["authority"]["promotion_authority"] = True
    result = readiness.evaluate_manifest(contract, manifest, repo_root=ROOT)
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert "manifest_authority" in result["invalid_inputs"]


def test_collapsed_points_cannot_self_declare_quadrant_coverage(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    values = manifest["metric_measurements"]
    for row in values["board_correspondences"]:
        row["board_xy_m"] = [0.01, 0.01]
    result = readiness.evaluate_manifest(
        contract, manifest, repo_root=evidence["root"]
    )
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert (
        "minimum_independent_board_correspondences:"
        "malformed_nonindependent_or_not_spatial"
    ) in result["invalid_inputs"]
    assert "all_four_board_quadrants:malformed_nonindependent_or_not_spatial" in result[
        "invalid_inputs"
    ]


def test_nonrigid_transforms_are_invalid_even_when_rehashed(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    root = evidence["root"]
    values = manifest["metric_measurements"]
    for field in (
        "overhead_camera_to_workcell_transform",
        "wrist_camera_extrinsics",
    ):
        pointer = values[field]
        artifact_path = root / pointer["artifact_path"]
        artifact = _load(artifact_path)
        artifact["transform_4x4"] = [[0.0] * 4 for _ in range(4)]
        pointer["artifact_sha256"] = _write_json(artifact_path, artifact)
    result = readiness.evaluate_manifest(contract, manifest, repo_root=root)
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert (
        "overhead_camera_to_workcell_transform:"
        "identity_transform_or_ownership_invalid"
    ) in result["invalid_inputs"]
    assert "wrist_camera_extrinsics:transform_or_ownership_invalid" in result[
        "invalid_inputs"
    ]


def test_board_fit_requires_bound_evaluator_inputs_and_thresholds(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    root = evidence["root"]
    pointer = manifest["metric_measurements"]["board_fit_evaluation"]
    artifact_path = root / pointer["artifact_path"]
    artifact = _load(artifact_path)
    artifact["evaluator_identity"]["executable_sha256"] = "0" * 64
    artifact["correspondences_digest"] = "1" * 64
    artifact["thresholds_digest"] = "2" * 64
    pointer["artifact_sha256"] = _write_json(artifact_path, artifact)
    result = readiness.evaluate_manifest(contract, manifest, repo_root=root)
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert (
        "independent_board_fit_evaluation:threshold_or_ownership_invalid"
        in result["invalid_inputs"]
    )


def test_supplied_malformed_objects_and_correspondences_are_invalid(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    values = manifest["metric_measurements"]
    values["object_keypoint_observations"][0]["uncertainty_95_m"] = 0.0
    values["board_correspondences"] = [
        {
            "point_id": "bad-point",
            "board_xy_m": [0.0, 0.0],
            "board_quadrant": "north_west",
            "source_frame_sha256": evidence["frame_sha"],
            "synthetic": False,
            "annotations": [],
        }
    ]
    result = readiness.evaluate_manifest(
        contract, manifest, repo_root=evidence["root"]
    )
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert "metric_object_keypoints_with_uncertainty:malformed_or_unreviewed" in result[
        "invalid_inputs"
    ]
    assert (
        "minimum_independent_board_correspondences:"
        "malformed_nonindependent_or_not_spatial"
    ) in result["invalid_inputs"]


def test_empty_decoder_identity_is_invalid(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    root = evidence["root"]
    pointer = manifest["physical_source"]["frame_extraction_receipt"]
    artifact_path = root / pointer["artifact_path"]
    artifact = _load(artifact_path)
    artifact["decoder_identity"] = {}
    pointer["artifact_sha256"] = _write_json(artifact_path, artifact)
    result = readiness.evaluate_manifest(contract, manifest, repo_root=root)
    assert result["verdict"] == "invalid_or_tampered_inputs"
    assert "frame_extraction_lineage:lineage_mismatch" in result["invalid_inputs"]


def test_valid_but_insufficient_correspondences_remain_missing(
    tmp_path: Path,
) -> None:
    contract, manifest, evidence = _complete_manifest(tmp_path)
    values = manifest["metric_measurements"]
    values["board_correspondences"] = values["board_correspondences"][:4]
    values["board_fit_evaluation"] = None
    result = readiness.evaluate_manifest(
        contract, manifest, repo_root=evidence["root"]
    )
    assert result["verdict"] == "measurement_prerequisites_missing"
    assert "minimum_independent_board_correspondences" in result["missing_prerequisites"]
    assert "independent_board_fit_evaluation" in result["missing_prerequisites"]
    assert result["invalid_inputs"] == []


def test_materializer_refuses_noncanonical_or_replayed_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(
        readiness.MetricRegistrationReadinessError,
        match="canonical output root",
    ):
        readiness.materialize(
            contract_path=CONTRACT_PATH,
            output_root=tmp_path / "substituted",
        )

    canonical = tmp_path / "canonical"
    canonical.mkdir()
    monkeypatch.setattr(readiness, "DEFAULT_OUTPUT_ROOT", canonical)
    with pytest.raises(
        readiness.MetricRegistrationReadinessError,
        match="already exists",
    ):
        readiness.materialize(
            contract_path=CONTRACT_PATH,
            output_root=canonical,
        )
