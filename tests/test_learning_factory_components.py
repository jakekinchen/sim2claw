from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from sim2claw.learning_factory_components import (
    build_twin_candidate,
    freeze_and_replay_ready_episodes,
    run_calibration_fit,
    run_independent_calibration_evaluator,
    validate_reconstruction_receipt,
    validate_twin_candidate,
)
from sim2claw.system_identification import _hash_fraction


REPO_ROOT = Path(__file__).resolve().parents[1]
SYSID_FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/sysid"
SYSID_CONFIG = SYSID_FIXTURE_ROOT / "smooth_slider_sysid_v1.json"
SYSID_EPISODE = SYSID_FIXTURE_ROOT / "recorded_slider_episode_v1.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()


def test_reused_iphone_3dgs_receipt_revalidates_every_bound_file() -> None:
    with tempfile.TemporaryDirectory(
        dir=REPO_ROOT / "artifacts/private",
        prefix="learning-factory-3dgs-test-",
    ) as temporary:
        root = Path(temporary)
        source = root / "source.mov"
        source.write_bytes(b"fixture-video")
        artifact = root / "candidate.ply"
        artifact.write_bytes(
            b"ply\n"
            b"format binary_little_endian 1.0\n"
            b"element vertex 1\n"
            b"property float x\n"
            b"property float y\n"
            b"property float z\n"
            b"property float opacity\n"
            b"property float scale_0\n"
            b"property float rot_0\n"
            b"end_header\n"
            + b"\x00" * 24
        )
        from sim2claw.iphone_3dgs import inspect_gaussian_ply

        dependency = Path(sys.executable).resolve()
        receipt: dict[str, object] = {
            "schema_version": "sim2claw.iphone_video_3dgs_receipt.v1",
            "proof_class": "monocular_video_relative_scale_3dgs",
            "source": {
                "path": str(source),
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
            },
            "artifact": {"path": str(artifact), **inspect_gaussian_ply(artifact)},
            "split": {
                "frozen_before_reconstruction": True,
                "training": ["frame-1.jpg"],
                "heldout": ["frame-2.jpg"],
            },
            "runtime_dependencies": {
                "python-fixture": {
                    "path": str(dependency),
                    "sha256": _sha256(dependency),
                }
            },
            "authority": {"metric_scale": False},
        }
        receipt["canonical_payload_sha256"] = _canonical(receipt)
        receipt_path = root / "receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        result = validate_reconstruction_receipt(
            receipt_path, repo_root=REPO_ROOT
        )
        assert result["mode"] == "reused"
        assert result["artifact"]["sha256"] == _sha256(artifact)
        assert result["metric_authority"] is False
        artifact.write_bytes(artifact.read_bytes() + b"tamper")
        try:
            validate_reconstruction_receipt(receipt_path, repo_root=REPO_ROOT)
        except ValueError as error:
            assert "artifact bytes mismatch" in str(error)
        else:
            raise AssertionError("tampered 3DGS artifact was accepted")


def test_real_twin_validator_compiles_settles_renders_and_hashes_trace() -> None:
    declaration = {
        "scene_id": "operator_updated_chess_workcell_v3",
        "capture_config": "configs/polycam/8873B66C-774C-48B1-B51D-338645867009.json",
        "mass_profile": "calibration/so101/follower_mass_profile_v1.json",
        "proof_class": "operator_updated_simulation_scene",
    }
    candidate = build_twin_candidate(
        declaration,
        repo_root=REPO_ROOT,
        implementation_sha256="f" * 64,
    )
    with tempfile.TemporaryDirectory(
        dir=REPO_ROOT / "runs", prefix="learning-factory-twin-test-"
    ) as temporary:
        result = validate_twin_candidate(
            candidate,
            repo_root=REPO_ROOT,
            attempt_dir=Path(temporary),
            settle_steps=25,
        )
    assert result["passed"] is True
    assert all(result["gates"].values())
    assert result["model_dimensions"]["ngeom"] > 0
    assert len(result["trace_sha256"]) == 64
    assert result["physical_authority"] is False


def test_real_split_and_exact_replay_chain_uses_payload_bytes() -> None:
    with tempfile.TemporaryDirectory(
        dir=REPO_ROOT / "runs", prefix="learning-factory-replay-test-"
    ) as temporary:
        root = Path(temporary)
        base = json.loads(SYSID_EPISODE.read_text(encoding="utf-8"))
        ids_by_role: dict[str, str] = {}
        index = 0
        while len(ids_by_role) < 2:
            candidate_id = f"factory-slider-{index:03d}"
            role = (
                "held_out"
                if _hash_fraction("fixture", candidate_id) < 0.5
                else "train"
            )
            ids_by_role.setdefault(role, candidate_id)
            index += 1
        episodes = []
        for role, episode_id in sorted(ids_by_role.items()):
            payload = copy.deepcopy(base)
            payload["episode_id"] = episode_id
            path = root / f"{role}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            episodes.append(
                {
                    "recording_id": episode_id,
                    "source_path": str(path),
                    "samples_sha256": _sha256(path),
                    "proof_class": "synthetic_recorded_action_fixture",
                    "assets": {"samples": str(path)},
                }
            )
        catalog_path = root / "catalog.json"
        catalog_path.write_text(
            json.dumps({"catalog_id": "factory-slider", "episodes": episodes}),
            encoding="utf-8",
        )
        result = freeze_and_replay_ready_episodes(
            catalog_path=catalog_path,
            config_path=SYSID_CONFIG,
            output_directory=root / "replay",
            repo_root=REPO_ROOT,
            strategy="deterministic_hash",
        )
        assert result["split_counts"] == {"train": 1, "held_out": 1}
        assert result["exact_replay_count"] == 2
        assert result["held_out_rows_opened"] == 0
        for row in result["exact_replays"]:
            receipt = REPO_ROOT / row["receipt_path"]
            assert receipt.is_file()
            assert _sha256(receipt) == row["receipt_sha256"]
        split_path = REPO_ROOT / result["split_manifest_path"]
        fit = run_calibration_fit(
            split_manifest_path=split_path,
            config_path=SYSID_CONFIG,
            output_directory=root / "fit",
            repo_root=REPO_ROOT,
            baseline_twin_id="fixture-baseline-twin",
            backend="official",
        )
        assert fit["trainer_or_runner_can_promote"] is False
        assert fit["fit"]["official_sysid_exercised"] is True
        evaluation = run_independent_calibration_evaluator(
            split_manifest_path=split_path,
            config_path=SYSID_CONFIG,
            fit_receipt_path=REPO_ROOT / fit["fit_receipt_path"],
            output_directory=root / "calibration-evaluation",
            repo_root=REPO_ROOT,
        )
        assert evaluation["evaluator_owner"] == "separate_cpu_calibration_evaluator"
        assert evaluation["held_out_rows_opened_for_training"] == 0
        assert evaluation["policy_probe"]["used_for_admission"] is False
        assert evaluation["verdict"] == "rejected"
        assert "required_parameter_stage_not_valid" in evaluation["reasons"]
        assert evaluation["process"]["exit_code"] == 0
