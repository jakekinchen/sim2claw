from __future__ import annotations

import hashlib
import inspect
import json

from sim2claw import canonical_contact_witness
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_contact_witness_v1.json"
)


def test_contact_witness_is_frozen_to_exact_negative_actions() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["plant_paths"] == [
        "canonical_direct_target",
        "diagnostic_zoh_0p11s",
    ]
    assert contract["action_identity"]["reset_variant"] == "nominal_only"
    assert contract["action_identity"]["dynamics_changed"] is False
    assert len(contract["cases"]) == 4
    for case in contract["cases"]:
        path = REPO_ROOT / case["action_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == (
            case["action_sha256"]
        )
    implementation = contract["inputs"]["implementation"]
    assert hashlib.sha256(
        (REPO_ROOT / implementation["path"]).read_bytes()
    ).hexdigest() == implementation["sha256"]
    assert not any(contract["authority"].values())


def test_contact_witness_source_has_no_hardware_or_mutation_path() -> None:
    source = inspect.getsource(canonical_contact_witness)
    for forbidden in (
        "SO101PhysicalGateway",
        "serial",
        "camera.open",
        ".set_torque(",
        "write_goal",
        "geom_friction[",
        "body_mass[",
        "body_inertia[",
    ):
        assert forbidden not in source
