from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/"
    "observable_registration_ephemeral_osmesa_renderer_capability_v1.json"
)
SCRIPT = ROOT / "tools/renderer/ephemeral_osmesa_capability.py"


def test_contract_freezes_one_frame_ephemeral_runtime_boundary() -> None:
    contract = json.loads(CONTRACT.read_text())

    assert contract["runtime"]["mujoco_version"] == "3.10.0"
    assert contract["runtime"]["numpy_version"] == "2.3.5"
    assert contract["runtime"]["gl_backend"] == "osmesa"
    assert contract["runtime"]["project_lock_sync_allowed"] is False
    assert contract["runtime"]["cuda_packages_allowed"] is False
    assert contract["render"]["frame_count"] == 1
    assert contract["resource_boundary"]["physical_video_reads_allowed"] == 0
    assert contract["resource_boundary"]["paid_compute_allowed"] is False
    assert not any(contract["authority"].values())


def test_capability_script_loads_without_importing_renderer_dependencies() -> None:
    specification = importlib.util.spec_from_file_location("or70_probe", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    payload = b"P6\n1 1\n255\n\x01\x02\x03"
    assert module._sha256(CONTRACT) == __import__("hashlib").sha256(
        CONTRACT.read_bytes()
    ).hexdigest()
    assert payload.startswith(b"P6\n")
