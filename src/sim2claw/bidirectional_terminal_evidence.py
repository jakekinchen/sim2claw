"""Build the local Q13 terminal-boundary evidence package."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT

CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_terminal_evidence_package_v1.json"
)


class TerminalEvidenceError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_and_verify_inputs(
    repo_root: Path = REPO_ROOT,
    contract_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = contract_path or (
        repo_root
        / "configs"
        / "evaluations"
        / "bidirectional_terminal_evidence_package_v1.json"
    )
    contract = json.loads(path.read_bytes())
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_terminal_evidence_package_contract.v1"
    ):
        raise TerminalEvidenceError("unexpected terminal package schema")
    inputs: dict[str, dict[str, Any]] = {}
    for row in contract["inputs"]:
        input_path = repo_root / row["path"]
        if not input_path.is_file() or sha256(input_path) != row["sha256"]:
            raise TerminalEvidenceError(f"changed evidence input: {row['path']}")
        inputs[row["role"]] = json.loads(input_path.read_bytes())
    return contract, inputs


def _case_rows(scene_gate: dict[str, Any]) -> str:
    rows = []
    for case in scene_gate["case_results"]:
        rows.append(
            "<tr>"
            f"<td>{html.escape(case['case_id'])}</td>"
            f"<td>{html.escape(case['direction'])}</td>"
            f"<td>{html.escape(case['source_square'].upper())}"
            f"→{html.escape(case['destination_direction_square'].upper())}</td>"
            f"<td>{case['minimum_center_to_route_clearance_mm']:.2f} mm</td>"
            f"<td>{html.escape(case['nearest_excluded_square'].upper())}</td>"
            "<td>REJECTED</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _viewer_html(
    contract: dict[str, Any],
    inputs: dict[str, dict[str, Any]],
) -> str:
    scene_gate = inputs["q06_scene_gate_receipt"]
    capture = inputs["fresh_rgb_capture_receipt"]
    heldout = inputs["heldout_registration_receipt"]
    retrospective = inputs["c2_retrospective_receipt"]
    frames = scene_gate["camera_frames"]
    claim = contract["claim_boundary"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bidirectional pawn push — terminal safety boundary</title>
<style>
body{{font:16px/1.45 system-ui,sans-serif;margin:0;background:#0d1117;color:#e6edf3}}
main{{max-width:1100px;margin:auto;padding:24px}} h1{{font-size:2rem}}
.warning{{border:2px solid #d29922;background:#2d2107;padding:18px;border-radius:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin:20px 0}}
figure{{margin:0;background:#161b22;padding:12px;border-radius:8px}} img{{width:100%;height:auto}}
figcaption{{font-size:.9rem;color:#9da7b3}} table{{width:100%;border-collapse:collapse}}
th,td{{padding:8px;border-bottom:1px solid #30363d;text-align:left}} code{{color:#79c0ff}}
</style>
</head>
<body><main>
<h1>Bidirectional pawn push: terminal safety boundary</h1>
<div class="warning"><strong>No task-transfer result.</strong>
{html.escape(claim['statement'])}</div>
<p>Proof class: <code>{html.escape(contract['proof_class'])}</code>.
REAL→SIM: 0 successful / 0 attempted. SIM→REAL: 0 successful / 0 attempted.
Physical attempts: 0 / 10 maximum.</p>
<div class="grid">
<figure><img src="../20260727-q06-scene-v1/c922_scene.png" alt="C922 scene">
<figcaption>C922 outcome-owner RGB · {frames['c922']['sha256']}</figcaption></figure>
<figure><img src="../20260727-q06-scene-v1/d405_scene.png" alt="D405 color scene">
<figcaption>D405 color RGB only · {frames['d405_color']['sha256']}</figcaption></figure>
<figure><img src="../20260727-q06-scene-v1/pi_imx708.jpg" alt="Pi scene">
<figcaption>Pi IMX708 arm context · {frames['pi_imx708']['sha256']}</figcaption></figure>
</div>
<h2>Frozen case admission</h2>
<p>Required center-to-route exclusion clearance: 88.90 mm.</p>
<table><thead><tr><th>Case</th><th>Direction</th><th>Lane</th><th>Clearance</th>
<th>Nearest exclusion</th><th>Gate</th></tr></thead>
<tbody>{_case_rows(scene_gate)}</tbody></table>
<h2>Registration and retrospective diagnostics</h2>
<ul>
<li>V4 fit residual: 24.631505 mm.</li>
<li>Single-open held-out B7 residual: 164.353128 mm; v4 rejected.</li>
<li>Immutable C2 old/v4 clearance: 312.326353 / 75.624879 mm.</li>
<li>C2 v4 contact, rise, and off-source displacement: zero.</li>
</ul>
<p>Capture status: {html.escape(capture['status'])}.
Held-out status: {html.escape(heldout['status'])}.
C2 retrospective status: {html.escape(retrospective['status'])}.</p>
<p>No synchronized action comparison exists because Q06 rejected every case
before action compilation. The three fresh RGB frames are presented as
separate camera views, not as exposure-synchronized media or task evidence.</p>
</main></body></html>
"""


def build(
    repo_root: Path = REPO_ROOT,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    contract, inputs = load_and_verify_inputs(repo_root, contract_path)
    scene_gate = inputs["q06_scene_gate_receipt"]
    if (
        scene_gate.get("status")
        != "terminal_safety_boundary_no_admissible_case"
        or scene_gate.get("admitted_case_ids") != []
        or scene_gate.get("counted_physical_attempts") != 0
        or scene_gate.get("robot_motion_commands") != 0
    ):
        raise TerminalEvidenceError("Q06 receipt does not prove a zero-motion boundary")
    claim = contract["claim_boundary"]
    if (
        claim.get("counted_action_hashes") != []
        or claim.get("new_action_compiled") is not False
        or claim.get("bidirectional_transfer_verified") is not False
        or claim.get("total_physical_attempts") != 0
    ):
        raise TerminalEvidenceError("terminal package overstates authority")

    output = contract["output"]
    viewer_path = repo_root / output["viewer_path"]
    receipt_path = repo_root / output["receipt_path"]
    viewer_path.parent.mkdir(parents=True, exist_ok=True)
    viewer_path.write_text(_viewer_html(contract, inputs), encoding="utf-8")

    receipt = {
        "schema_version": "sim2claw.bidirectional_terminal_evidence_package.v1",
        "package_id": contract["package_id"],
        "task_id": contract["task_id"],
        "status": "terminal_safety_boundary_no_admissible_case",
        "proof_class": contract["proof_class"],
        "contract_sha256": sha256(contract_path or CONTRACT_PATH),
        "input_hashes": {
            row["role"]: row["sha256"] for row in contract["inputs"]
        },
        "viewer": {
            "path": output["viewer_path"],
            "sha256": sha256(viewer_path),
        },
        "poster": scene_gate["camera_frames"]["c922"],
        "camera_frames": scene_gate["camera_frames"],
        "case_results": scene_gate["case_results"],
        "registration": {
            "candidate": "bidirectional_pawn_push_scene_registration_v4",
            "fit_residual_mm": 24.631505,
            "heldout_residual_mm": 164.353128,
            "accepted": False,
        },
        "retrospective_c2": {
            "old_minimum_clearance_mm": 312.326353,
            "v4_minimum_clearance_mm": 75.624879,
            "selected_contact_count": 0,
            "off_source": False,
            "promotion_authority": False,
        },
        "evaluator": {
            "id": "bidirectional_off_source_push_float64_40hz_v1",
            "sha256": inputs["q06_scene_gate_receipt"]["evaluator_sha256"],
            "format": "native little-endian float64 C-order at 40 Hz",
        },
        "counted_action_hashes": [],
        "denominator": {
            "real_to_sim": {"successful": 0, "attempted": 0},
            "sim_to_real": {"successful": 0, "attempted": 0},
            "physical_attempts": 0,
            "maximum_physical_attempts": 10,
        },
        "terminal_boundary": scene_gate["terminal_boundary"],
        "claim_boundary": claim["statement"],
        "browser_comparison": {
            "available": False,
            "reason": "No case was admitted and no action was compiled.",
        },
        "raw_recordings_published": False,
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
