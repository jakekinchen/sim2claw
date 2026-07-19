from __future__ import annotations

import copy
import hashlib
import json
import shutil
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
from sim2claw.learning_factory import LearningFactory
from sim2claw.learning_factory_recursion import (
    CORRECTION_SCHEMA,
    REGISTRY_SCHEMA,
    _independent_replay_digest,
    admit_correction_candidate,
)
from sim2claw.scene import board_square_center
from sim2claw.source_episode import admission_payload_sha256
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
    (REPO_ROOT / "artifacts/private").mkdir(parents=True, exist_ok=True)
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
    assert result["gates"]["robot_articulation_complete"] is True
    assert result["gates"]["task_piece_fixtures_complete"] is True
    assert result["gates"]["collision_penetration_bounded"] is True
    assert result["gates"]["actuation_sensitivity_nonzero"] is True
    assert result["gates"]["provenance_and_authority_complete"] is True
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


def test_real_component_campaign_executes_lf00_through_lf13() -> None:
    runtime_parent = REPO_ROOT / "runs"
    runtime_parent.mkdir(parents=True, exist_ok=True)
    required_bundle_directories = [
        REPO_ROOT / "datasets/manipulation_source_recordings",
        REPO_ROOT / "outputs/pawn_composability/recovered_corpus_v2",
    ]
    for directory in required_bundle_directories:
        directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=runtime_parent, prefix="learning-factory-component-campaign-"
    ) as temporary:
        root = Path(temporary)
        project_id = f"component-campaign-{root.name[-8:]}"
        model_path = root / "smooth_slider.xml"
        model_path.write_bytes(
            (SYSID_FIXTURE_ROOT / "smooth_slider.xml").read_bytes()
        )
        config = json.loads(SYSID_CONFIG.read_text(encoding="utf-8"))
        config["optimizer"].update(
            {"multi_start_count": 1, "maximum_iterations": 4}
        )
        contact = config["parameter_stages"][2]
        contact["requires_any_observable"] = ["joint_position"]
        contact["parameters"] = [
            {
                "name": "contact_proxy_damping_scale",
                "target": "joint_damping_scale",
                "nominal": 1.0,
                "minimum": 0.8,
                "maximum": 1.2,
                "supports_observables": [
                    "joint_position",
                    "end_effector_position",
                    "end_effector_orientation",
                    "gripper_position",
                ],
                "smooth": True,
                "fallback_supported": True,
            }
        ]
        config_path = root / "sysid_config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        source = json.loads(SYSID_EPISODE.read_text(encoding="utf-8"))
        ids_by_role: dict[str, list[str]] = {"train": [], "held_out": []}
        index = 0
        while any(len(values) < 2 for values in ids_by_role.values()):
            episode_id = f"component-slider-{index:03d}"
            role = (
                "held_out"
                if _hash_fraction("fixture", episode_id) < 0.5
                else "train"
            )
            if len(ids_by_role[role]) < 2:
                ids_by_role[role].append(episode_id)
            index += 1
        episodes = []
        for episode_id in sorted(ids_by_role["train"] + ids_by_role["held_out"]):
            payload = copy.deepcopy(source)
            payload["episode_id"] = episode_id
            path = root / f"{episode_id}.json"
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
        catalog_path = root / "synthetic_catalog.json"
        catalog_path.write_text(
            json.dumps({"catalog_id": project_id, "episodes": episodes}),
            encoding="utf-8",
        )

        task = json.loads(
            (
                REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json"
            ).read_text(encoding="utf-8")
        )
        target_xy = board_square_center("a6")[:2]
        task["splits"]["object_destination_pairs"]["training"] = [
            "tan_pawn_c8:target_left_train"
        ]
        task["splits"]["target_pose_cells"]["training"][0]["x_m"] = [
            float(target_xy[0]),
            float(target_xy[0]),
        ]
        task["splits"]["target_pose_cells"]["training"][0]["y_m"] = [
            float(target_xy[1]),
            float(target_xy[1]),
        ]
        task_path = root / "goal_act_component_task.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        recipe = json.loads(
            (
                REPO_ROOT / "configs/training/goal_act_recipe_v1.json"
            ).read_text(encoding="utf-8")
        )
        recipe.update(
            {
                "recipe_id": "goal-act-component-acceptance-v1",
                "chunk_size": 4,
                "n_action_steps": 2,
                "model_dimension": 16,
                "attention_heads": 4,
                "encoder_layers": 1,
                "decoder_layers": 1,
                "feedforward_dimension": 32,
                "latent_dimension": 4,
                "batch_size": 16,
                "optimizer_updates": 2,
                "checkpoint_interval_updates": 1,
                "maximum_wall_seconds": 120,
            }
        )
        recipe_path = root / "goal_act_component_recipe.json"
        recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

        project = json.loads(
            (
                REPO_ROOT
                / "configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json"
            ).read_text(encoding="utf-8")
        )
        project["project_id"] = project_id
        project["title"] = "Synthetic real-component learning-factory acceptance"
        project["learning_factory"].update(
            {
                "profile": "component_fixture",
                "campaign": {
                    "campaign_id": "component-acceptance",
                    "generation": 0,
                    "parent_generation": None,
                },
                "component_fixture": {
                    "synthetic_catalog": catalog_path.relative_to(REPO_ROOT).as_posix(),
                    "sysid_config": config_path.relative_to(REPO_ROOT).as_posix(),
                    "split_strategy": "deterministic_hash",
                },
                "replay": {
                    "sysid_config": config_path.relative_to(REPO_ROOT).as_posix(),
                    "minimum_ready_episodes": 2,
                    "split_strategy": "deterministic_hash",
                    "held_out_column": None,
                    "sysid_backend": "official",
                },
                "curriculum": {
                    "task_contract": task_path.relative_to(REPO_ROOT).as_posix(),
                    "maximum_candidates": 1,
                    "admitted_source_episodes": [
                        {
                            "source_episode_id": "strict-c8-source-mechanism",
                            "source_proof_class": "simulation_strict_success",
                            "source_segment_ids": ["full_episode"],
                        }
                    ],
                    "candidate_executions": [],
                    "candidate_generation": {
                        "mode": "repo_native_pawn_source_expert_v1",
                        "maximum_executions": 1,
                        "object_dimensions_m": [0.03, 0.03, 0.053],
                        "gripper_aperture_mapping": {
                            "mapping_id": "so101_parallel_jaw_affine_v1",
                            "scale_m_per_rad": 0.02,
                            "offset_m": 0.01,
                        },
                    },
                },
                "training": {
                    "recipe": recipe_path.relative_to(REPO_ROOT).as_posix(),
                    "evaluation_cohort": "auto",
                },
                "recursion": {
                    "previous_registry": None,
                    "correction_candidates": [],
                    "raw_failures_are_training_data": False,
                },
            }
        )
        project_path = root / "project.json"
        project_path.write_text(
            json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        relative_project = project_path.relative_to(REPO_ROOT)
        factory = LearningFactory(relative_project, repo_root=REPO_ROOT)
        try:
            report = factory.run_range("LF-00", "LF-13")
            assert [row["stage_id"] for row in report["results"]] == [
                f"LF-{index:02d}" for index in range(14)
            ]
            assert report["results"][7]["output"]["verdict"] == "admitted"
            assert report["results"][9]["output"]["accepted_count"] == 1
            assert report["results"][9]["output"]["held_out_training_rows"] == 0
            assert report["results"][10]["output"]["dataset_sha256"] == (
                report["results"][9]["output"]["dataset_sha256"]
            )
            evaluation = report["results"][11]
            assert evaluation["status"] == "terminal_negative"
            assert set(evaluation["output"]["b_g_scorecard"]) == {
                f"pawn_{file_name}{source}_to_{file_name}{destination}"
                for file_name in "bcdefg"
                for source, destination in ((1, 2), (2, 1))
            }
            assert all(
                row["case_count"] == 1
                for row in evaluation["output"]["b_g_scorecard"].values()
            )
            assert report["results"][12]["output"]["counterexample_count"] >= 1
            assert report["results"][13]["status"] == "passed", report["results"][
                13
            ].get("diagnostics")
            assert report["results"][13]["output"]["state"] == "rejected"
            assert report["results"][13]["output"]["skill_package"] is None

            candidate_id = report["results"][8]["output"]["candidates"][0][
                "candidate_id"
            ]
            episode = (
                factory.root
                / "stages/LF-09/attempts"
                / report["results"][9]["attempt_id"]
                / "candidate_executions"
                / candidate_id
            )
            dataset_root = Path(
                report["results"][9]["output"]["dataset_receipt_path"]
            ).parent
            ordinary_verdict = json.loads(
                (dataset_root / f"{candidate_id}.evaluator.json").read_text(
                    encoding="utf-8"
                )
            )
            parent_id = "counterexample-corrective-component"
            action_trace_sha256 = "a" * 64
            registry_unsigned = {
                "schema_version": REGISTRY_SCHEMA,
                "source_evaluation_sha256": "b" * 64,
                "parent_registry_sha256": None,
                "counterexample_count": 1,
                "new_counterexample_count": 1,
                "counterexamples": [
                    {
                        "counterexample_id": parent_id,
                        "action_trace_sha256": action_trace_sha256,
                        "route_targets": ["LF-09"],
                    }
                ],
                "route_targets": ["LF-09"],
                "correction_candidates": [],
                "raw_failures_are_training_data": False,
            }
            registry = {
                **registry_unsigned,
                "artifact_sha256": _canonical(registry_unsigned),
            }
            correction_root = root / "correction"
            correction_root.mkdir()
            failed_prefix_path = correction_root / "failed_prefix.json"
            failed_prefix_path.write_text(
                json.dumps(
                    {
                        "parent_counterexample_id": parent_id,
                        "action_trace_sha256": action_trace_sha256,
                    }
                ),
                encoding="utf-8",
            )
            privileged_rows = [
                json.loads(line)
                for line in (
                    episode / "evaluator_privileged_state.jsonl"
                ).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            state_path = correction_root / "pre_failure_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "integration_state_float64": privileged_rows[0]["state"][
                            "integration_state_float64"
                        ]
                    }
                ),
                encoding="utf-8",
            )
            intervention_path = correction_root / "intervention.json"
            intervention_path.write_text(
                json.dumps(
                    {"owner": "geometric_expert", "start_sample_index": 1}
                ),
                encoding="utf-8",
            )
            corrective_verdict = {
                **ordinary_verdict,
                "admission_class": "corrective_suffix",
                "all_source_actions_admitted": False,
                "corrective_suffix": {
                    "start_sample_index": 1,
                    "end_sample_index_exclusive": ordinary_verdict[
                        "training_rows_authorized"
                    ],
                    "exact_pre_failure_integration_state_matched": True,
                    "failed_prefix_excluded_from_imitation_rows": True,
                    "independent_full_episode_replay_passed": True,
                    "corrective_actions_owned_by_declared_expert_or_teleoperator": True,
                    "parent_counterexample_id": parent_id,
                    "failed_prefix_sha256": _sha256(failed_prefix_path),
                    "pre_failure_integration_state_sha256": _sha256(state_path),
                    "intervention_sha256": _sha256(intervention_path),
                    "independent_full_episode_evidence_sha256": (
                        _independent_replay_digest(ordinary_verdict)
                    ),
                },
            }
            corrective_verdict["canonical_payload_sha256"] = (
                admission_payload_sha256(corrective_verdict)
            )
            verdict_path = correction_root / "corrective_verdict.json"
            verdict_path.write_text(json.dumps(corrective_verdict), encoding="utf-8")
            admitted_correction = admit_correction_candidate(
                {
                    "schema_version": CORRECTION_SCHEMA,
                    "correction_candidate_id": "component-correction-v1",
                    "parent_counterexample_id": parent_id,
                    "failed_prefix": {
                        "path": str(failed_prefix_path),
                        "sha256": _sha256(failed_prefix_path),
                    },
                    "pre_failure_integration_state": {
                        "path": str(state_path),
                        "sha256": _sha256(state_path),
                    },
                    "intervention": {
                        "path": str(intervention_path),
                        "sha256": _sha256(intervention_path),
                    },
                    "corrective_episode_directory": str(episode),
                    "admission_verdict_path": str(verdict_path),
                },
                registry=registry,
            )
            assert admitted_correction["independent_evaluator_admitted"] is True
            assert admitted_correction["failed_prefix_training_rows"] == 0
            assert admitted_correction["admitted_suffix_row_count"] == 561
        finally:
            shutil.rmtree(
                REPO_ROOT
                / "runs/learning-factory/projects"
                / project_id,
                ignore_errors=True,
            )
