from __future__ import annotations

from pathlib import Path

from sim2claw.observable_registration_studio_publication import (
    compile_observable_registration_publication,
    load_observable_registration_studio_proof,
    load_publication_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_publication_contract_is_read_only_and_preserves_base() -> None:
    contract = load_publication_contract()
    assert contract["rules"]["base_proof_may_be_rewritten"] is False
    assert contract["rules"]["base_timeline_may_be_changed"] is False
    assert contract["rules"]["global_mapping_must_remain_unapproved"] is True
    assert not any(contract["authority"].values())


def test_publication_compiler_is_deterministic_and_explicit(tmp_path) -> None:
    first = compile_observable_registration_publication(
        output_directory=tmp_path / "first"
    )
    second = compile_observable_registration_publication(
        output_directory=tmp_path / "second"
    )
    assert first["supplement"]["artifact_sha256"] == second["supplement"][
        "artifact_sha256"
    ]
    assert first["base_proof_unchanged"] == second["base_proof_unchanged"]
    assert first["acceptance"]["exact_replay_denominator"] == 2
    assert first["acceptance"]["validation_boundary_explicit"] is True
    assert first["acceptance"]["global_mapping_approved"] is False
    assert first["acceptance"]["camera_pixel_refinement_present"] is True
    assert first["acceptance"]["canonical_simulator_camera_replaced"] is False


def test_publication_loader_merges_registration_without_timeline_change(
    tmp_path,
) -> None:
    compile_observable_registration_publication(output_directory=tmp_path)
    payload = load_observable_registration_studio_proof(
        output_directory=tmp_path
    )
    registration = payload["registration_successor"]
    assert payload["timeline"]["sample_count"] == 531
    assert registration["first_contact_divergence"]["gap_samples"] == 154
    assert registration["exact_replay"]["attempts"] == 2
    assert registration["exact_replay"]["successes"] == 0
    assert registration["signed_geometric_gap"][
        "enclosure_fixed_jaw_gap_mm"
    ] > 60.0
    assert registration["spatial_mechanism"]["jacobian_rank"] == 2
    refinement = registration["camera_pixel_refinement"]
    assert refinement["reviewed_visible_intersection_count"] == 14
    assert refinement["cross_cohort_agreement_rms_px"] < 0.4
    assert refinement["candidate_cross_cohort_validation_rms_px"] < 1.0
    assert refinement["rms_improvement_fraction"] > 0.75
    assert refinement["exact_intrinsics_approved"] is False
    assert refinement["canonical_simulator_camera_replaced"] is False
    assert (
        registration["spatial_mechanism"]["validation_admissible_pose_count"]
        == 0
    )
    assert registration["authority"]["physical_motion"] is False
