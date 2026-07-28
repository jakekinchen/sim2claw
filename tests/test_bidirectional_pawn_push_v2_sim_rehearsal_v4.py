from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v2.json"
)
V3 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v3.json"
)
V4 = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_sim_rehearsal_v4.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("relative_cli_paths", [True, False])
def test_v4_cli_finalizes_resolvable_receipt_after_cleanup(
    relative_cli_paths: bool,
) -> None:
    parent = ROOT / "runs" / "orchestration-fixtures"
    parent.mkdir(parents=True, exist_ok=True)
    fixture_root = Path(
        tempfile.mkdtemp(prefix="v05-v4-e2e-", dir=parent)
    )
    try:
        v2 = json.loads(V2.read_text(encoding="utf-8"))
        v2["rehearsal_id"] = "bounded-v4-path-fixture"
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
        v3["rehearsal_id"] = "bounded-v4-path-fixture"
        v3["frozen_v2_contract"] = {
            "path": str(fixture_v2.relative_to(ROOT)),
            "sha256": _sha(fixture_v2),
        }
        fixture_v3 = fixture_root / "fixture-v3.json"
        fixture_v3.write_text(
            json.dumps(v3, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        v4 = json.loads(V4.read_text(encoding="utf-8"))
        v4["rehearsal_id"] = "bounded-v4-path-fixture"
        v4["frozen_v3_contract"] = {
            "path": str(fixture_v3.relative_to(ROOT)),
            "sha256": _sha(fixture_v3),
        }
        fixture_v4 = fixture_root / "fixture-v4.json"
        fixture_v4.write_text(
            json.dumps(v4, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output = fixture_root / "receipt.json"
        contract_arg = (
            fixture_v4.relative_to(ROOT)
            if relative_cli_paths
            else fixture_v4
        )
        output_arg = (
            output.relative_to(ROOT) if relative_cli_paths else output
        )

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "sim2claw.bidirectional_pawn_push_v2_sim_rehearsal_v4",
                str(contract_arg),
                str(output_arg),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        receipt = json.loads(output.read_text(encoding="utf-8"))
        assert receipt["schema_version"].endswith("_receipt.v4")
        assert len(receipt["grid_results"]) == 1
        assert set(receipt["grid_results"][0]["static_checks"]) == {
            "ik",
            "arm_joint_margin",
            "closed_jaw_target",
            "closed_jaw_simulator_bounds",
            "closed_jaw_hardware_bounds",
            "action_identity",
        }
        retained = ROOT / receipt["contract_path"]
        assert retained == fixture_v4
        assert retained.is_file()
        assert _sha(retained) == receipt["contract_sha256"]
        assert receipt["public_path_resolution"] == {
            "contract_resolved_before_repo_binding": True,
            "output_resolved_before_write": True,
            "retained_contract_resolves": True,
            "temporary_contract_retained": False,
            "grid_or_action_changed": False,
        }
        assert not list(parent.glob("v05-v3-compat-*.json"))
        assert receipt["physical_motion"] is False
        assert receipt["physical_task_attempts"] == 0
    finally:
        shutil.rmtree(fixture_root, ignore_errors=True)
