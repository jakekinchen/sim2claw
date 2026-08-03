"""Audit whether the renderer collapsed upstream SO-101 material semantics."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_post_final_robot_material_semantics_loss_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_robot_material_semantics_loss_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_robot_material_semantics_loss_attribution_v1"


def load_post_final_robot_material_semantics_loss_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR105 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    audit = contract["audit"]
    if audit["manifest_robot_body_ids"] != list(range(29, 45)) or audit["manifest_mesh_side_prefixes"] != ["left_", "right_"]:
        raise ValueError("OR105 robot identity boundary drifted")
    if audit["physical_pixels_used"] is not False or audit["selection_if_passed"] != "freeze_two_class_robot_material_palette_calibration":
        raise ValueError("OR105 audit boundary drifted")
    expected = {
        "scene_manifest_reads_allowed": 1,
        "upstream_xml_reads_allowed": 1,
        "physical_video_decodes_allowed": 0,
        "candidate_video_decodes_allowed": 0,
        "renders_allowed": 0,
        "fits_allowed": 0,
        "parameter_values_allowed": 0,
        "simulator_replays_allowed": 0,
        "action_or_state_mutations_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }
    if contract["resource_boundary"] != expected or any(contract["authority"].values()):
        raise ValueError("OR105 resource or authority boundary drifted")
    if contract["claim_limits"]["material_palette_calibrated"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR105 claim boundary drifted")
    return contract


def _rgba(value: str) -> tuple[float, float, float, float]:
    parsed = tuple(float(item) for item in value.split())
    if len(parsed) != 4:
        raise ValueError("OR105 expected four-channel upstream material")
    return parsed


def _base_mesh_name(name: str, prefixes: list[str]) -> str:
    for prefix in prefixes:
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR105 one-run receipt already exists")
    contract = load_post_final_robot_material_semantics_loss_attribution_contract(contract_path)
    or104 = json.loads((REPO_ROOT / contract["sources"]["or104_closeout"]["path"]).read_text())
    if or104["reviewer_decision"] != "REJECT_SHARED_SHOULDER_LIFT_AND_REATTRIBUTE_ARTICULATION_RESIDUAL":
        raise ValueError("OR104 did not authorize residual reattribution")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR105 scene revision mismatch")
    mesh_name_by_id = {int(row["id"]): row["name"] for row in scene["meshes"]}
    body_ids = set(int(value) for value in contract["audit"]["manifest_robot_body_ids"])
    robot_geoms = [row for row in scene["geoms"] if int(row["body_id"]) in body_ids and row["type"] == contract["audit"]["manifest_robot_geom_type"]]
    prefixes = [str(value) for value in contract["audit"]["manifest_mesh_side_prefixes"]]

    root = ET.parse(REPO_ROOT / contract["sources"]["upstream_so101_xml"]["path"]).getroot()
    material_rgba = {
        row.attrib["name"]: _rgba(row.attrib["rgba"])
        for row in root.findall("./asset/material")
        if "name" in row.attrib and "rgba" in row.attrib
    }
    upstream_visual_by_mesh: dict[str, dict[str, Any]] = {}
    for geom in root.findall(".//geom"):
        if geom.attrib.get("class") != "visual" or "mesh" not in geom.attrib or "material" not in geom.attrib:
            continue
        material = geom.attrib["material"]
        if material not in material_rgba:
            raise ValueError("OR105 visual geom references an unbound material")
        mesh = geom.attrib["mesh"]
        value = {"mesh": mesh, "material": material, "rgba": list(material_rgba[material])}
        previous = upstream_visual_by_mesh.get(mesh)
        if previous is not None and previous != value:
            raise ValueError("OR105 upstream mesh has conflicting material semantics")
        upstream_visual_by_mesh[mesh] = value

    manifest_rows: list[dict[str, Any]] = []
    mapped = 0
    for geom in robot_geoms:
        mesh_name = mesh_name_by_id[int(geom["mesh_id"])]
        base_name = _base_mesh_name(mesh_name, prefixes)
        upstream = upstream_visual_by_mesh.get(base_name)
        if upstream is not None:
            mapped += 1
        manifest_rows.append(
            {
                "geom_id": int(geom["id"]),
                "body_id": int(geom["body_id"]),
                "manifest_mesh_name": mesh_name,
                "base_mesh_name": base_name,
                "manifest_rgba": [float(value) for value in geom["rgba"]],
                "upstream": upstream,
            }
        )
    mapping_fraction = mapped / max(len(manifest_rows), 1)
    manifest_unique_rgba = sorted({tuple(row["manifest_rgba"]) for row in manifest_rows})
    upstream_unique_rgba = sorted({tuple(row["rgba"]) for row in upstream_visual_by_mesh.values()})
    dark_meshes = sorted(row["mesh"] for row in upstream_visual_by_mesh.values() if float(np.mean(row["rgba"][:3])) <= 0.2)
    structural_meshes = sorted(row["mesh"] for row in upstream_visual_by_mesh.values() if float(np.mean(row["rgba"][:3])) > 0.2)
    acceptance = contract["acceptance"]
    gates = {
        "minimum_manifest_robot_mesh_geom_count": len(manifest_rows) >= int(acceptance["minimum_manifest_robot_mesh_geom_count"]),
        "complete_manifest_to_upstream_visual_mesh_mapping": mapping_fraction >= float(acceptance["minimum_manifest_to_upstream_visual_mesh_mapping_fraction"]),
        "manifest_robot_materials_collapsed": len(manifest_unique_rgba) <= int(acceptance["maximum_manifest_unique_robot_rgba_count_for_collapse"]),
        "upstream_has_multiple_visual_material_classes": len(upstream_unique_rgba) >= int(acceptance["minimum_upstream_unique_visual_material_rgba_count"]),
        "upstream_has_dark_servo_and_nonservo_structural_classes": bool(dark_meshes) and bool(structural_meshes),
        "source_revision_and_provenance_hashes_verified": True,
        "zero_pixel_decode_render_fit_parameter_replay_action_state_mutation_hardware_or_paid_compute": True,
        "material_semantics_attribution_not_palette_calibration_fidelity_or_promotion": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_robot_material_semantics_loss_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ROBOT_MATERIAL_SEMANTICS_LOSS_ATTRIBUTED" if passed else "TERMINAL_ROBOT_MATERIAL_SEMANTICS_LOSS_NOT_SUPPORTED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "manifest_rows": manifest_rows,
        "summary": {
            "manifest_robot_mesh_geom_count": len(manifest_rows),
            "manifest_unique_robot_rgba": [list(value) for value in manifest_unique_rgba],
            "manifest_to_upstream_visual_mesh_mapping_fraction": mapping_fraction,
            "upstream_visual_mesh_count": len(upstream_visual_by_mesh),
            "upstream_unique_visual_material_rgba": [list(value) for value in upstream_unique_rgba],
            "upstream_dark_servo_meshes": dark_meshes,
            "upstream_nonservo_structural_meshes": structural_meshes,
        },
        "gates": gates,
        "execution": {"scene_manifest_reads": 1, "upstream_xml_reads": 1, "physical_video_decodes": 0, "candidate_video_decodes": 0, "renders": 0, "fits": 0, "parameter_values": 0, "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_TWO_CLASS_ROBOT_MATERIAL_PALETTE_CALIBRATION" if passed else "STOP_ROBOT_MATERIAL_LANE",
        "next_transition": "freeze_or106_two_class_robot_material_palette_calibration" if passed else "stop_robot_material_lane",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
