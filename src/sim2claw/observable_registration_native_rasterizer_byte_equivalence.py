"""Footage-blind exact acceleration gate for the OR78 triangle raster loop."""

from __future__ import annotations

import ctypes
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    quaternion_matrix_wxyz,
    sha256_file,
)
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import (
    _local_triangles_for_geom,
    _project_camera,
    _rasterize_triangle,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_native_rasterizer_byte_equivalence_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_native_rasterizer_byte_equivalence_v1"


def _prepare_triangle_stream(
    scene: dict[str, Any],
    trace: dict[str, Any],
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    camera: dict[str, Any],
    renderer: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, int]]:
    if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
        raise ValueError("scene and trace body ordering drifted")
    state = trace["frames"][0]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    body_rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    ]
    light = np.asarray(renderer["lighting"]["world_direction"], dtype=np.float64)
    light /= np.linalg.norm(light)
    ambient = float(renderer["lighting"]["ambient"])
    diffuse = float(renderer["lighting"]["diffuse"])
    projected: list[np.ndarray] = []
    depths: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    mesh_source_triangles = 0
    mesh_raster_triangles = 0

    for geom in scene["geoms"]:
        local, source_count, is_mesh = _local_triangles_for_geom(
            geom, meshes=meshes, config=renderer
        )
        body_id = int(geom["body_id"])
        geom_rotation = body_rotations[body_id] @ quaternion_matrix_wxyz(
            geom["quaternion_wxyz"]
        )
        geom_center = body_positions[body_id] + body_rotations[body_id] @ np.asarray(
            geom["position"], dtype=np.float64
        )
        world = local @ geom_rotation.T + geom_center
        geom_pixels, geom_depths = _project_camera(
            world,
            camera,
            int(renderer["width_px"]),
            int(renderer["height_px"]),
        )
        normals = np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0])
        normal_norms = np.linalg.norm(normals, axis=1)
        unit_normals = np.divide(
            normals,
            normal_norms[:, None],
            out=np.zeros_like(normals),
            where=normal_norms[:, None] > 1e-12,
        )
        lambert = np.abs(unit_normals @ light)
        intensity = np.clip(ambient + diffuse * lambert, 0.0, 1.0)
        base_rgb = np.clip(np.asarray(geom["rgba"][:3], dtype=np.float64), 0.0, 1.0)
        geom_colors = np.rint(
            base_rgb[::-1][None, :] * intensity[:, None] * 255.0
        ).astype(np.uint8)
        projected.append(geom_pixels)
        depths.append(geom_depths)
        colors.append(geom_colors)
        if is_mesh:
            mesh_source_triangles += source_count
            mesh_raster_triangles += len(local)

    all_pixels = np.ascontiguousarray(np.concatenate(projected, axis=0), dtype=np.float64)
    all_depths = np.ascontiguousarray(np.concatenate(depths, axis=0), dtype=np.float64)
    all_colors = np.ascontiguousarray(np.concatenate(colors, axis=0), dtype=np.uint8)
    return all_pixels, all_depths, all_colors, {
        "total_raster_triangle_count": len(all_pixels),
        "mesh_source_triangle_count": mesh_source_triangles,
        "mesh_raster_triangle_count": mesh_raster_triangles,
    }


def _blank_buffers(renderer: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]
    zbuffer = np.full((height, width), np.inf, dtype=np.float64)
    return frame, zbuffer


def _python_rasterize(
    pixels: np.ndarray,
    depths: np.ndarray,
    colors: np.ndarray,
    renderer: dict[str, Any],
) -> tuple[np.ndarray, int, int, float]:
    frame, zbuffer = _blank_buffers(renderer)
    updates = 0
    occluded = 0
    started = time.perf_counter()
    for triangle_pixels, triangle_depths, color in zip(
        pixels, depths, colors, strict=True
    ):
        triangle_updates, triangle_occluded = _rasterize_triangle(
            frame, zbuffer, triangle_pixels, triangle_depths, color
        )
        updates += triangle_updates
        occluded += triangle_occluded
    elapsed = time.perf_counter() - started
    return frame, updates, occluded, elapsed


def _compile_native(
    contract: dict[str, Any], output_directory: Path
) -> tuple[Path, list[str], str]:
    source = REPO_ROOT / contract["sources"]["native_source"]["path"]
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    library = output_directory / f"or79_triangle_rasterizer{suffix}"
    command = [
        contract["compiler"]["executable"],
        "-O2",
        "-std=c11",
        *( ["-dynamiclib"] if platform.system() == "Darwin" else ["-shared", "-fPIC"] ),
        str(source),
        "-o",
        str(library),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return library, command, completed.stderr


def _native_rasterize(
    library_path: Path,
    pixels: np.ndarray,
    depths: np.ndarray,
    colors: np.ndarray,
    renderer: dict[str, Any],
) -> tuple[np.ndarray, int, int, float]:
    library = ctypes.CDLL(str(library_path))
    function = library.rasterize_triangles
    function.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64),
    ]
    function.restype = ctypes.c_int
    frame, zbuffer = _blank_buffers(renderer)
    updates = ctypes.c_uint64(0)
    occluded = ctypes.c_uint64(0)
    started = time.perf_counter()
    result = function(
        frame.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        zbuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        int(renderer["width_px"]),
        int(renderer["height_px"]),
        pixels.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        depths.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        colors.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        len(pixels),
        ctypes.byref(updates),
        ctypes.byref(occluded),
    )
    elapsed = time.perf_counter() - started
    if result != 0:
        raise RuntimeError(f"native rasterizer returned {result}")
    return frame, updates.value, occluded.value, elapsed


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR79 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name in {"mesh_asset_root", "native_source"}:
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    trace_binding = contract["sources"]["development_state_trace"]
    trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    camera = {
        "name": "or73_shared_development_camera",
        "position": contract["camera"]["position"],
        "target": contract["camera"]["target"],
        "fov_degrees": contract["camera"]["fov_degrees"],
    }
    pixels, depths, colors, stream_metrics = _prepare_triangle_stream(
        scene, trace, meshes, camera, contract["renderer"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        contract, output_directory
    )
    python_frame, python_updates, python_occluded, python_seconds = _python_rasterize(
        pixels, depths, colors, contract["renderer"]
    )
    native_frame, native_updates, native_occluded, native_seconds = _native_rasterize(
        library_path, pixels, depths, colors, contract["renderer"]
    )
    reference = cv2.imread(
        str(REPO_ROOT / contract["sources"]["or78_reference_image"]["path"]),
        cv2.IMREAD_COLOR,
    )
    if reference is None:
        raise ValueError("OR78 reference image could not be read")
    image_path = output_directory / "native_equivalence_frame.png"
    ok, encoded = cv2.imencode(".png", native_frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("failed to encode OR79 frame")
    image_path.write_bytes(encoded.tobytes())
    speedup = python_seconds / native_seconds
    expected = contract["gates"]
    gates = {
        "total_raster_triangle_count": stream_metrics["total_raster_triangle_count"]
        == expected["expected_total_raster_triangle_count"],
        "mesh_source_triangle_count": stream_metrics["mesh_source_triangle_count"]
        == expected["expected_mesh_source_triangle_count"],
        "unique_mesh_asset_reads": len(asset_receipts)
        == expected["expected_unique_mesh_asset_reads"],
        "python_pixels_match_or78_reference": bool(np.array_equal(python_frame, reference)),
        "native_pixels_match_or78_reference": bool(np.array_equal(native_frame, reference)),
        "native_pixels_match_python": bool(np.array_equal(native_frame, python_frame)),
        "python_expected_depth_updates": python_updates
        == expected["expected_reference_depth_buffer_update_count"],
        "python_expected_occluded_fragments": python_occluded
        == expected["expected_reference_occluded_fragment_count"],
        "native_and_python_depth_updates_equal": native_updates == python_updates,
        "native_and_python_occluded_fragments_equal": native_occluded == python_occluded,
        "native_raster_stage_speedup": speedup
        >= expected["minimum_native_raster_stage_speedup"],
        "physical_validation_heldout_closed": True,
        "no_fits_replays_or_paid_compute": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_native_rasterizer_byte_equivalence_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_NATIVE_RASTERIZER_BYTE_EQUIVALENCE"
            if passed
            else "TERMINAL_NATIVE_RASTERIZER_EQUIVALENCE_GATE_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "native_source": {
            "path": contract["sources"]["native_source"]["path"],
            "sha256": sha256_file(REPO_ROOT / contract["sources"]["native_source"]["path"]),
        },
        "compiled_library": {
            "path": str(library_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(library_path),
            "command": compile_command,
            "compiler_stderr": compiler_stderr,
        },
        "frame": {
            "path": str(image_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(image_path),
            "reference_sha256": contract["sources"]["or78_reference_image"]["sha256"],
            "pixel_mismatch_count_native_to_reference": int(
                np.count_nonzero(native_frame != reference)
            ),
        },
        "metrics": {
            **stream_metrics,
            "unique_mesh_asset_reads": len(asset_receipts),
            "python_depth_buffer_update_count": python_updates,
            "native_depth_buffer_update_count": native_updates,
            "python_occluded_fragment_count": python_occluded,
            "native_occluded_fragment_count": native_occluded,
            "python_raster_seconds": python_seconds,
            "native_raster_seconds": native_seconds,
            "native_raster_stage_speedup": speedup,
        },
        "gates": gates,
        "execution": {
            "capability_frames": 1,
            "development_state_trace_reads": 1,
            "development_candidate_reference_reads": 1,
            "unique_mesh_asset_reads": len(asset_receipts),
            "physical_video_reads": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "ADVANCE_TO_FROZEN_FULL_MESH_DEVELOPMENT_TIMELINE"
            if passed
            else "DO_NOT_USE_NATIVE_RASTERIZER"
        ),
        "next_transition": (
            "freeze_or80_native_full_mesh_full_development_timeline"
            if passed
            else "retain_or78_python_renderer_and_revise_acceleration_without_footage"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
