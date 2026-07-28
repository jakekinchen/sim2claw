from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v2.json"
)
V3 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v3.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v3_binds_exact_v2_and_changes_only_internal_key_path() -> None:
    contract = json.loads(V3.read_text(encoding="utf-8"))
    assert _sha(ROOT / contract["frozen_v2_contract"]["path"]) == contract[
        "frozen_v2_contract"
    ]["sha256"]
    for field in (
        "implementation",
        "v2_implementation",
        "base_implementation",
    ):
        binding = contract[field]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["only_change"] == {
        "legacy_internal_key": "minimum_joint_limit_margin_rad",
        "value_source": "gates.minimum_arm_joint_limit_margin_rad",
        "temporary_internal_contract_only": True,
        "temporary_contract_retained": False,
        "public_gate_semantics_changed": False,
        "grid_or_action_changed": False,
        "scene_or_registration_changed": False,
        "dynamic_rule_changed": False,
    }
    assert not any(contract["authority"].values())


def test_v3_cli_reaches_receipt_on_bounded_real_mujoco_fixture() -> None:
    (ROOT / "runs" / "orchestration-fixtures").mkdir(
        parents=True, exist_ok=True
    )
    fixture_root = Path(
        tempfile.mkdtemp(
            prefix="v05-v3-e2e-",
            dir=ROOT / "runs" / "orchestration-fixtures",
        )
    )
    try:
        v2 = json.loads(V2.read_text(encoding="utf-8"))
        v2["rehearsal_id"] = "bounded-v3-orchestration-fixture"
        v2["cases"] = [
            row for row in v2["cases"] if row["case_id"] == "R2S_A2_A3"
        ]
        v2["grid"]["stroke_lengths_m"] = [0.09]
        v2["grid"]["contact_heights_m"] = [0.018]
        v2["robustness_variants"] = [
            row
            for row in v2["robustness_variants"]
            if row["variant_id"] == "nominal"
        ]
        fixture_v2 = fixture_root / "fixture-v2.json"
        fixture_v2.write_text(
            json.dumps(v2, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        v3 = json.loads(V3.read_text(encoding="utf-8"))
        v3["rehearsal_id"] = "bounded-v3-orchestration-fixture"
        v3["frozen_v2_contract"] = {
            "path": str(fixture_v2.relative_to(ROOT)),
            "sha256": _sha(fixture_v2),
        }
        fixture_v3 = fixture_root / "fixture-v3.json"
        fixture_v3.write_text(
            json.dumps(v3, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output = fixture_root / "receipt.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal_v3",
                str(fixture_v3),
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        receipt = json.loads(output.read_text(encoding="utf-8"))
        assert receipt["schema_version"].endswith("_receipt.v3")
        assert len(receipt["grid_results"]) == 1
        row = receipt["grid_results"][0]
        assert set(row["static_checks"]) == {
            "ik",
            "arm_joint_margin",
            "closed_jaw_target",
            "closed_jaw_simulator_bounds",
            "closed_jaw_hardware_bounds",
            "action_identity",
        }
        assert receipt["orchestration_compatibility"][
            "temporary_contract_retained"
        ] is False
        assert not list(fixture_root.glob("v05-v3-compat-*.json"))
        assert receipt["physical_motion"] is False
        assert receipt["physical_task_attempts"] == 0
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
