from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .alignment import compare_alignment
from .capture import fetch_capture
from .doctor import doctor_json, format_doctor, run_doctor
from .paths import DEFAULT_OUTPUT_ROOT, REPO_ROOT, STUDIO_ASSET_ROOT
from .render import render_scene
from .scene import scene_summary


DEFAULT_SYSID_CONFIG = Path("configs/sysid/recorded_action_sysid_v1.json")
DEFAULT_PHYSICAL_CATALOG = Path(
    "configs/data/physical_pawn_move_catalog_20260719.json"
)


def _parameter_assignments(values: Sequence[str] | None) -> dict[str, float]:
    result: dict[str, float] = {}
    for assignment in values or []:
        if "=" not in assignment:
            raise ValueError(f"parameter must use name=value: {assignment}")
        name, raw_value = assignment.split("=", 1)
        name = name.strip()
        if not name or name in result:
            raise ValueError(f"parameter name is empty or duplicated: {name!r}")
        result[name] = float(raw_value)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sim2claw")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="fail-closed runtime preflight")
    doctor.add_argument(
        "--target", choices=("auto", "mac", "nvidia", "linux-cpu"), default="auto"
    )
    doctor.add_argument("--render-probe", action="store_true")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    dev_loop_audit = subparsers.add_parser(
        "dev-loop-audit",
        help="verify canonical autonomous-development authority and drift",
    )
    dev_loop_audit.add_argument("--root", type=Path, default=REPO_ROOT)
    dev_loop_audit.add_argument("--output", type=Path)

    dev_loop_ledger = subparsers.add_parser(
        "dev-loop-render-ledger",
        help="render or check the ledger's canonical current-state block",
    )
    dev_loop_ledger.add_argument("--root", type=Path, default=REPO_ROOT)
    ledger_mode = dev_loop_ledger.add_mutually_exclusive_group(required=True)
    ledger_mode.add_argument("--check", action="store_true")
    ledger_mode.add_argument("--write", action="store_true")

    dev_loop_benchmark = subparsers.add_parser(
        "dev-loop-benchmark",
        help="run the deterministic seeded development-loop control benchmark",
    )
    dev_loop_benchmark.add_argument("--config", type=Path, required=True)
    dev_loop_benchmark.add_argument("--output", type=Path, required=True)

    dev_loop_verify = subparsers.add_parser(
        "dev-loop-verify",
        help="run or reuse an exact-identity leased test receipt",
    )
    dev_loop_verify.add_argument("--root", type=Path, default=REPO_ROOT)
    dev_loop_verify.add_argument("--tier", required=True)
    dev_loop_verify.add_argument("--receipt-root", type=Path, required=True)
    dev_loop_verify.add_argument(
        "--relevant-path", action="append", required=True, dest="relevant_paths"
    )
    dev_loop_verify.add_argument("--wall-time-seconds", type=int, default=3600)
    dev_loop_verify.add_argument(
        "test_command",
        nargs=argparse.REMAINDER,
        help="test command after --",
    )

    subparsers.add_parser(
        "fetch-polycam", help="fetch and verify the owner-provided capture reference"
    )

    render = subparsers.add_parser(
        "render", help="compile, settle, and render the scene"
    )
    render.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_ROOT / "render.png"
    )
    render.add_argument("--width", type=int, default=768)
    render.add_argument("--height", type=int, default=1152)
    render.add_argument("--settle-steps", type=int, default=500)
    render.add_argument(
        "--camera",
        choices=(
            "photo_reference",
            "workcell",
            "overhead",
            "studio_overview",
            "studio_left",
            "studio_right",
            "studio_mug",
        ),
        default="photo_reference",
    )
    render.add_argument("--scan-overlay", action="store_true")

    compare = subparsers.add_parser(
        "compare-alignment",
        help="register the overhead photo and generate photo/Polycam overlays",
    )
    compare.add_argument("--photo", type=Path, required=True)
    compare.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT / "alignment",
    )

    subparsers.add_parser("scene-info", help="print the frozen scene contract")

    grasp = subparsers.add_parser(
        "grasp-probe",
        help="scripted single-piece grasp probe with receipt and frames",
    )
    grasp.add_argument("--arm", choices=("left", "right"), default="left")
    grasp.add_argument("--piece", type=str, default=None)
    grasp.add_argument("--no-frames", action="store_true")

    subparsers.add_parser(
        "act-train",
        help="train the frozen chess-rook ACT policy from fresh synthetic episodes",
    )
    act_eval = subparsers.add_parser(
        "act-eval",
        help="run the separately owned CPU/fp32 ACT chess-rook episode",
    )
    act_eval.add_argument("--checkpoint", type=Path, required=True)
    act_eval.add_argument("--no-video", action="store_true")
    contact_sensitivity = subparsers.add_parser(
        "act-contact-sensitivity",
        help="run the frozen ACT rook-lift evaluator over contact-prior variants",
    )
    contact_sensitivity.add_argument("--checkpoint", type=Path, required=True)
    contact_sensitivity.add_argument("--output-directory", type=Path, default=None)
    contact_sensitivity.add_argument("--render-video", action="store_true")

    studio = subparsers.add_parser(
        "studio",
        help="open the browser evidence studio and loopback-only ACT source recorder",
    )
    studio.add_argument("--host", default="127.0.0.1")
    studio.add_argument("--port", type=int, default=4173)
    studio.add_argument("--no-open", action="store_true")
    studio.add_argument(
        "--read-only",
        action="store_true",
        help="disable all recorder and live-device control endpoints",
    )
    studio.add_argument(
        "--enable-physical-demo",
        action="store_true",
        help=(
            "explicitly expose the fixed physical demo controller on loopback; "
            "disabled by default and incompatible with --read-only"
        ),
    )

    project_pack = subparsers.add_parser(
        "project-pack", help="create a hash-bound project evidence bundle"
    )
    project_pack.add_argument("--project", type=Path, required=True)
    project_pack.add_argument("--output", type=Path, required=True)

    project_inspect = subparsers.add_parser(
        "project-inspect", help="verify a project contract or packed bundle"
    )
    project_inspect.add_argument("--project", type=Path, required=True)
    project_inspect.add_argument("--bundle", type=Path, default=None)
    project_inspect.add_argument(
        "--expected-bundle-sha256",
        default=None,
        help="coordinator-computed outer bundle digest; required with --bundle",
    )

    pipeline_stage = subparsers.add_parser(
        "pipeline-stage", help="run one bounded, truth-preserving project stage"
    )
    pipeline_stage.add_argument("--project", type=Path, required=True)
    pipeline_stage.add_argument(
        "--stage",
        choices=(
            "inspect",
            "calibrate-sim",
            "evaluate-skills",
            "train-candidates",
            "compare-candidates",
        ),
        required=True,
    )

    pipeline_status = subparsers.add_parser(
        "pipeline-status", help="show the latest bounded NemoClaw stage result"
    )
    pipeline_status.add_argument("--project", type=Path, required=True)

    inspect_robots_offline = subparsers.add_parser(
        "inspect-robots-offline",
        help="run the optional Inspect Robots deterministic offline replay slice",
    )
    inspect_robots_offline.add_argument(
        "--fixture",
        type=Path,
        default=REPO_ROOT
        / "configs/integrations/inspect_robots_offline_fixture.json",
    )
    inspect_robots_offline.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "runs/inspect_robots_offline",
    )

    factory_inspect = subparsers.add_parser(
        "factory-inspect",
        help="verify a project and resolve its complete learning-factory graph",
    )
    factory_inspect.add_argument("--project", type=Path, required=True)
    factory_inspect.add_argument("--generation", type=int, default=None)
    factory_inspect.add_argument("--parent-generation", type=int, default=None)

    factory_status = subparsers.add_parser(
        "factory-status",
        help="show every learning-factory stage, blocker, and next action",
    )
    factory_status.add_argument("--project", type=Path, required=True)
    factory_status.add_argument("--generation", type=int, default=None)
    factory_status.add_argument("--parent-generation", type=int, default=None)

    factory_run = subparsers.add_parser(
        "factory-run",
        help="run the next stage, a bounded stage range, or a resumable attempt",
    )
    factory_run.add_argument("--project", type=Path, required=True)
    factory_run.add_argument("--generation", type=int, default=None)
    factory_run.add_argument("--parent-generation", type=int, default=None)
    factory_mode = factory_run.add_mutually_exclusive_group(required=True)
    factory_mode.add_argument("--next", action="store_true", dest="run_next")
    factory_mode.add_argument("--resume", action="store_true")
    factory_mode.add_argument("--from", choices=tuple(f"LF-{index:02d}" for index in range(14)), dest="from_stage")
    factory_run.add_argument(
        "--through",
        choices=tuple(f"LF-{index:02d}" for index in range(14)),
        dest="through_stage",
    )

    factory_explain = subparsers.add_parser(
        "factory-explain",
        help="explain one learning-factory stage and its latest evidence",
    )
    factory_explain.add_argument("--project", type=Path, required=True)
    factory_explain.add_argument("--generation", type=int, default=None)
    factory_explain.add_argument("--parent-generation", type=int, default=None)
    factory_explain.add_argument(
        "--stage",
        choices=tuple(f"LF-{index:02d}" for index in range(14)),
        required=True,
    )

    factory_recurse = subparsers.add_parser(
        "factory-recurse",
        help="fork an immutable child generation from LF-12 counterexample routes",
    )
    factory_recurse.add_argument("--project", type=Path, required=True)
    factory_recurse.add_argument("--generation", type=int, default=None)
    factory_recurse.add_argument("--parent-generation", type=int, default=None)
    factory_recurse.add_argument(
        "--target",
        action="append",
        choices=("LF-06", "LF-08", "LF-09"),
        default=None,
    )
    factory_recurse.add_argument(
        "--through",
        choices=tuple(f"LF-{index:02d}" for index in range(6, 14)),
        default="LF-11",
    )

    factory_act_evidence = subparsers.add_parser(
        "factory-act-evidence",
        help="bind a narrow ACT training/evaluation pair without widening its claim",
    )
    factory_act_evidence.add_argument("--training-receipt", type=Path, required=True)
    factory_act_evidence.add_argument("--evaluation-receipt", type=Path, required=True)
    factory_act_evidence.add_argument("--output", type=Path, default=None)

    subparsers.add_parser(
        "teleop-preflight",
        help="inspect SO-101 buses, calibrations, and recorder mode gates",
    )
    subparsers.add_parser(
        "physical-gateway-preflight",
        help="open both identified buses torque-off and verify physical gateway state",
    )
    physical_measurement = subparsers.add_parser(
        "physical-measurement-baseline",
        help="capture one preregistered torque-off camera and actuator baseline",
    )
    physical_measurement.add_argument("--output", type=Path, required=True)
    physical_measurement.add_argument("--samples", type=int, default=30)
    physical_measurement.add_argument("--interval-seconds", type=float, default=0.25)

    empty_gripper = subparsers.add_parser(
        "empty-gripper-diagnose",
        help=(
            "derive a hash-bound, non-promoting empty-gripper diagnostic "
            "without robot or simulator execution"
        ),
    )
    empty_gripper.add_argument("--config", type=Path, required=True)
    empty_gripper.add_argument("--output", type=Path, required=True)

    joint_limit = subparsers.add_parser(
        "joint-limit-compare",
        help=(
            "run the frozen action-identical current-vs-calibrated SO-101 "
            "joint-range diagnostic"
        ),
    )
    joint_limit.add_argument("--config", type=Path, required=True)
    joint_limit.add_argument("--output", type=Path, required=True)

    joint_identifiability = subparsers.add_parser(
        "joint-identifiability",
        help=(
            "derive a hash-bound offline scale/offset/lag identifiability "
            "audit without robot or simulator execution"
        ),
    )
    joint_identifiability.add_argument("--config", type=Path, required=True)
    joint_identifiability.add_argument("--output", type=Path, required=True)

    physical_replay = subparsers.add_parser(
        "physical-replay",
        help="replay one finalized physical command trace through the guarded follower",
    )
    physical_replay.add_argument("--recording", type=Path, required=True)
    physical_replay.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge that the powered follower workcell is clear for motion",
    )
    hil_identifiability = subparsers.add_parser(
        "hil-identifiability",
        help="run one or all preregistered dual-camera unloaded HIL packets",
    )
    hil_identifiability.add_argument("--config", type=Path, required=True)
    hil_identifiability.add_argument("--output", type=Path, required=True)
    hil_identifiability.add_argument("--packet", default=None)
    hil_identifiability.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge the owner-cleared powered follower workcell",
    )
    hil_simulator = subparsers.add_parser(
        "hil-simulator-compare",
        help="run the frozen two-replay shoulder-range HIL simulator comparison",
    )
    hil_simulator.add_argument("--config", type=Path, required=True)
    hil_simulator.add_argument("--output", type=Path, required=True)
    hil_evidence = subparsers.add_parser(
        "hil-compile-evidence",
        help="verify and summarize the frozen four-packet HIL campaign",
    )
    hil_evidence.add_argument("--config", type=Path, required=True)
    hil_evidence.add_argument("--campaign", type=Path, required=True)
    hil_evidence.add_argument("--output", type=Path, required=True)
    hil_trace_analysis = subparsers.add_parser(
        "hil-analyze-traces",
        help="derive zero-new-motion diagnostics from the frozen HIL traces",
    )
    hil_trace_analysis.add_argument("--config", type=Path, required=True)
    hil_trace_analysis.add_argument("--output", type=Path, required=True)
    hil_trace_decomposition = subparsers.add_parser(
        "hil-decompose-traces",
        help="audit requested/applied HIL actions, faults, excitation, and lag",
    )
    hil_trace_decomposition.add_argument("--config", type=Path, required=True)
    hil_trace_decomposition.add_argument("--output", type=Path, required=True)

    sail_inventory = subparsers.add_parser(
        "sail-inventory",
        help="verify the hash-bound retained SAIL evidence inventory",
    )
    sail_inventory.add_argument("--campaign", type=Path, required=True)

    sail_compile = subparsers.add_parser(
        "sail-compile-evidence",
        help="compile retained sources into ignored CalibrationEvidence.v1 artifacts",
    )
    sail_compile.add_argument("--campaign", type=Path, required=True)
    sail_compile.add_argument("--output", type=Path, required=True)

    sail_residuals = subparsers.add_parser(
        "sail-compile-residuals",
        help="compile phase-aligned ResidualField.v1 artifacts from retained evidence",
    )
    sail_residuals.add_argument("--config", type=Path, required=True)
    sail_residuals.add_argument("--output", type=Path, required=True)

    sail_belief_graph = subparsers.add_parser(
        "sail-compile-belief-graph",
        help="compile the deterministic retained SAIL belief graph and revisions",
    )
    sail_belief_graph.add_argument("--config", type=Path, required=True)
    sail_belief_graph.add_argument("--output", type=Path, required=True)

    sail_surprise = subparsers.add_parser(
        "sail-compile-structural-surprise",
        help="compile normalized SAIL compensation debt and mechanism request",
    )
    sail_surprise.add_argument("--config", type=Path, required=True)
    sail_surprise.add_argument("--output", type=Path, required=True)

    sail_mechanisms = subparsers.add_parser(
        "sail-compile-mechanisms",
        help="compile bounded SAIL mechanism plugins and seeded posteriors",
    )
    sail_mechanisms.add_argument("--config", type=Path, required=True)
    sail_mechanisms.add_argument("--output", type=Path, required=True)

    sail_loop_closure = subparsers.add_parser(
        "sail-compile-loop-closure",
        help="compile deterministic SAIL influence discovery and sparse loop closure",
    )
    sail_loop_closure.add_argument("--config", type=Path, required=True)
    sail_loop_closure.add_argument("--output", type=Path, required=True)

    sail_invariance = subparsers.add_parser(
        "sail-compile-invariance",
        help="compile plugin-declared whole-episode SAIL invariance verdicts",
    )
    sail_invariance.add_argument("--config", type=Path, required=True)
    sail_invariance.add_argument("--output", type=Path, required=True)

    sail_acquisition = subparsers.add_parser(
        "sail-compile-acquisition",
        help="compile deterministic SAIL structural-discrimination probe plans",
    )
    sail_acquisition.add_argument("--config", type=Path, required=True)
    sail_acquisition.add_argument("--output", type=Path, required=True)

    sail_live_operator = subparsers.add_parser(
        "sail-run-live-operator",
        help="run the SAIL decision/evidence control plane to a derived verdict or abstention",
    )
    sail_live_operator.add_argument("--config", type=Path, required=True)
    sail_live_operator.add_argument("--output", type=Path, required=True)
    sail_live_operator.add_argument(
        "--measurement-evaluator-receipt",
        type=Path,
        help="optional sealed-packet-bound offline measurement evaluator receipt",
    )
    sail_live_operator.add_argument(
        "--trusted-adapter-request",
        type=Path,
        help="optional result-free request for a registered deterministic simulator adapter",
    )

    sail_benchmark = subparsers.add_parser(
        "sail-compile-benchmark",
        help="compile the disjoint public/sealed seeded SAIL benchmark",
    )
    sail_benchmark.add_argument("--config", type=Path, required=True)
    sail_benchmark.add_argument("--output", type=Path, required=True)

    sail_executed_benchmark = subparsers.add_parser(
        "sail-compile-executed-benchmark",
        help="execute registered public-only SAIL methods and score them with the sealed evaluator",
    )
    sail_executed_benchmark.add_argument("--config", type=Path, required=True)
    sail_executed_benchmark.add_argument("--output", type=Path, required=True)

    sail_inspect_campaign = subparsers.add_parser(
        "sail-compile-inspect-campaign",
        help="compile the governed structural Inspect development campaign",
    )
    sail_inspect_campaign.add_argument("--config", type=Path, required=True)
    sail_inspect_campaign.add_argument("--output", type=Path, required=True)

    sail_retrospective_case = subparsers.add_parser(
        "sail-compile-retrospective-case",
        help="compile the retired-workcell SAIL loop-closure case and certificate",
    )
    sail_retrospective_case.add_argument("--config", type=Path, required=True)
    sail_retrospective_case.add_argument("--output", type=Path, required=True)

    sail_prospective_simulator = subparsers.add_parser(
        "sail-run-prospective-simulator",
        help="run the preregistered action-frozen prospective simulator campaign",
    )
    sail_prospective_simulator.add_argument("--config", type=Path, required=True)
    sail_prospective_simulator.add_argument("--output", type=Path, required=True)

    sail_twin_capability = subparsers.add_parser(
        "sail-compile-twin-capability",
        help="compile exact-scope TwinWorthiness kill-switch evidence",
    )
    sail_twin_capability.add_argument("--config", type=Path, required=True)
    sail_twin_capability.add_argument("--output", type=Path, required=True)

    sail_policy_flywheel = subparsers.add_parser(
        "sail-run-policy-flywheel",
        help="run and compile the gated synthetic policy-flywheel campaign",
    )
    sail_policy_flywheel.add_argument("--config", type=Path, required=True)
    sail_policy_flywheel.add_argument("--output", type=Path, required=True)

    sail_studio_observatory = subparsers.add_parser(
        "sail-compile-studio-observatory",
        help="compile the receipt-bound read-only SAIL Studio investigation surface",
    )
    sail_studio_observatory.add_argument("--config", type=Path, required=True)
    sail_studio_observatory.add_argument("--output", type=Path, required=True)

    sail_publication = subparsers.add_parser(
        "sail-compile-publication",
        help="compile the receipt-bound Phase 1 SAIL paper and reproduction package",
    )
    sail_publication.add_argument("--config", type=Path, required=True)
    sail_publication.add_argument("--output", type=Path, required=True)

    recorded_replay = subparsers.add_parser(
        "replay-recorded",
        help="replay one recorded command episode in MuJoCo and emit synchronized metrics",
    )
    recorded_replay.add_argument("--episode", type=Path, required=True)
    recorded_replay.add_argument(
        "--config", type=Path, default=DEFAULT_SYSID_CONFIG
    )
    recorded_replay.add_argument("--output", type=Path, required=True)
    recorded_replay.add_argument(
        "--parameter",
        action="append",
        help="bounded candidate override in name=value form; repeat as needed",
    )
    replay_eligibility = subparsers.add_parser(
        "replay-eligibility-audit",
        help="audit one manifest for exact-replay eligibility without replaying it",
    )
    replay_eligibility.add_argument("--manifest", type=Path, required=True)
    replay_eligibility.add_argument("--output", type=Path, required=True)
    physical_replay_eligibility = subparsers.add_parser(
        "physical-recording-replay-eligibility",
        help="materialize and audit exact-replay identity from a finalized recording",
    )
    physical_replay_eligibility.add_argument(
        "--recording", type=Path, required=True
    )
    physical_replay_eligibility.add_argument(
        "--manifest-output", type=Path, required=True
    )
    physical_replay_eligibility.add_argument(
        "--report-output", type=Path, required=True
    )
    eligible_physical_replay = subparsers.add_parser(
        "replay-eligible-physical-recording",
        help="replay P4-eligible physical actions offline with exact tensor identity",
    )
    eligible_physical_replay.add_argument("--recording", type=Path, required=True)
    eligible_physical_replay.add_argument("--manifest", type=Path, required=True)
    eligible_physical_replay.add_argument(
        "--config", type=Path, default=DEFAULT_SYSID_CONFIG
    )
    eligible_physical_replay.add_argument("--output", type=Path, required=True)
    hold_record = subparsers.add_parser("zero-displacement-hold-record")
    hold_record.add_argument(
        "--packet",
        type=Path,
        default=REPO_ROOT / "configs/hardware/p6_zero_displacement_hold_packet.json",
    )
    hold_record.add_argument("--yes", action="store_true")
    physical_excitation = subparsers.add_parser(
        "physical-excitation",
        help="compile, reposition, or execute one follower-only excitation packet",
    )
    physical_excitation.add_argument(
        "--phase", choices=("compile", "reposition", "execute"), required=True
    )
    physical_excitation.add_argument("--packet", type=Path, required=True)
    physical_excitation.add_argument("--output", type=Path)
    physical_excitation.add_argument("--yes", action="store_true")
    physical_excitation.add_argument("--dry-run", action="store_true")
    physical_canary = subparsers.add_parser(
        "physical-canary",
        help="normalize, compile, or execute one frozen simulation canary on the follower",
    )
    physical_canary.add_argument(
        "--phase", choices=("normalize", "compile", "execute"), required=True
    )
    physical_canary.add_argument("--packet", type=Path, required=True)
    physical_canary.add_argument("--bundle", type=Path)
    physical_canary.add_argument("--contact-receipt", type=Path)
    physical_canary.add_argument("--normalization-receipt", type=Path)
    physical_canary.add_argument("--output", type=Path)
    physical_canary.add_argument("--yes", action="store_true")
    geometric_physical = subparsers.add_parser(
        "geometric-physical",
        help=(
            "compile, independently review, or execute one evaluator-admitted "
            "geometric pawn episode"
        ),
    )
    geometric_physical.add_argument(
        "--phase", choices=("compile", "review", "execute"), required=True
    )
    geometric_physical.add_argument("--packet", type=Path, required=True)
    geometric_physical.add_argument("--episode", type=Path)
    geometric_physical.add_argument("--admission", type=Path)
    geometric_physical.add_argument("--candidate-manifest", type=Path)
    geometric_physical.add_argument("--review", type=Path)
    geometric_physical.add_argument("--output", type=Path)
    geometric_physical.add_argument("--reviewer")
    geometric_physical.add_argument("--decision-id")
    geometric_physical.add_argument("--yes", action="store_true")
    wrist_view_reposition = subparsers.add_parser(
        "wrist-view-reposition",
        help="compile, review, or execute one guarded follower-only D405 view stage",
    )
    wrist_view_reposition.add_argument(
        "--phase", choices=("compile", "review", "execute"), required=True
    )
    wrist_view_reposition.add_argument("--packet", type=Path, required=True)
    wrist_view_reposition.add_argument("--candidate-manifest", type=Path)
    wrist_view_reposition.add_argument("--route", type=Path)
    wrist_view_reposition.add_argument("--review", type=Path)
    wrist_view_reposition.add_argument("--output", type=Path)
    wrist_view_reposition.add_argument("--stage", type=int)
    wrist_view_reposition.add_argument("--prior-receipt", type=Path)
    wrist_view_reposition.add_argument("--reviewer")
    wrist_view_reposition.add_argument("--decision-id")
    wrist_view_reposition.add_argument("--yes", action="store_true")
    live_anchored_reposition = subparsers.add_parser(
        "live-anchored-camera-reposition",
        help="preview and execute one setup-only route from a settled torque-on anchor",
    )
    live_anchored_reposition.add_argument("--route", type=Path, required=True)
    live_anchored_reposition.add_argument(
        "--candidate-manifest", type=Path, required=True
    )
    live_anchored_reposition.add_argument("--output", type=Path, required=True)
    live_anchored_reposition.add_argument("--yes", action="store_true")
    c922_acquisition = subparsers.add_parser(
        "c922-calibration-acquisition-preflight",
        help="dry-run the frozen 18-view C922 calibration acquisition plan",
    )
    c922_acquisition.add_argument(
        "--plan",
        type=Path,
        default=REPO_ROOT
        / "configs/acquisition/c922_exact_mode_calibration.json",
    )
    c922_acquisition.add_argument("--output", type=Path, required=True)
    c922_capture = subparsers.add_parser(
        "c922-calibration-acquire",
        help="acquire the frozen operator-guided 18-view C922 corpus",
    )
    c922_capture.add_argument("--plan", type=Path, default=REPO_ROOT / "configs/acquisition/c922_exact_mode_calibration.json")
    c922_capture.add_argument("--output", type=Path, required=True)
    c922_capture.add_argument("--dry-run", action="store_true")
    metrology_transaction = subparsers.add_parser(
        "metrology-transaction-preflight",
        help="readiness-only P8/P13 metrology transaction; never opens cameras",
    )
    metrology_transaction.add_argument(
        "--transaction",
        type=Path,
        default=REPO_ROOT
        / "configs/acquisition/current_100mm_p8_p13_metrology_transaction_v1.json",
    )
    metrology_transaction.add_argument("--output", type=Path, required=True)
    d405_apriltag = subparsers.add_parser(
        "d405-apriltag-observe",
        help="detect tag36h11 id 0 offline in an existing D405 RGB image or video",
    )
    d405_apriltag.add_argument("--source", type=Path, required=True)
    d405_apriltag.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/acquisition/d405_wrist_apriltag_observation_v1.json",
    )
    d405_apriltag.add_argument("--capture-report", type=Path)
    d405_apriltag.add_argument("--selected-frame-output", type=Path)
    d405_apriltag.add_argument("--output", type=Path, required=True)
    static_tricam = subparsers.add_parser(
        "static-tricam-capture",
        help="capture one rigid C922, D405 RGB-D, and Pi still bundle",
    )
    static_tricam.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/acquisition/current_static_tricam_capture_v1.json",
    )
    static_tricam.add_argument("--output", type=Path, required=True)
    static_tricam.add_argument("--camera-session-token", required=True)
    static_tricam.add_argument("--fixed-mount-token", required=True)
    static_tricam.add_argument(
        "--yes",
        action="store_true",
        help="acknowledge that the scene and arm will remain rigid",
    )
    d405_rgbd_readiness = subparsers.add_parser(
        "d405-rgbd-readiness",
        help="inventory D405/librealsense metric-depth access without streaming",
    )
    d405_rgbd_readiness.add_argument("--output", type=Path, required=True)
    d405_rgbd_readiness.add_argument(
        "--enumeration-file",
        type=Path,
        help="ingest the stdout from an operator-run privileged calibration inventory",
    )
    workcell_registration = subparsers.add_parser(
        "workcell-registration",
        help="write or evaluate the stationary board-to-workcell survey",
    )
    workcell_registration.add_argument(
        "--phase", choices=("worksheet", "evaluate"), required=True
    )
    workcell_registration.add_argument("--output", type=Path, required=True)
    workcell_registration.add_argument("--survey", type=Path)
    workcell_registration.add_argument("--manifest", type=Path)
    workcell_input = subparsers.add_parser(
        "workcell-registration-input",
        help="capture, annotate, or finalize stationary P13 inputs",
    )
    workcell_input.add_argument(
        "--phase", choices=("capture", "bundle", "finalize"), required=True
    )
    workcell_input.add_argument("--output", type=Path, required=True)
    workcell_input.add_argument("--capture-receipt", type=Path)
    workcell_input.add_argument("--annotator-a", type=Path)
    workcell_input.add_argument("--annotator-b", type=Path)
    workcell_input.add_argument("--board-measurement", type=Path)
    workcell_input.add_argument("--survey", type=Path)
    workcell_input.add_argument("--intrinsics", type=Path)
    workcell_input.add_argument("--distortion", type=Path)
    workcell_input.add_argument("--focus-setting")
    workcell_input.add_argument("--dry-run", action="store_true")
    workcell_input.add_argument("--ack-board-camera-fixed", action="store_true")
    workcell_input.add_argument("--ack-board-cleared", action="store_true")
    workcell_input.add_argument("--ack-markers-visible", action="store_true")
    workcell_input.add_argument("--ack-focus-locked", action="store_true")
    workcell_input.add_argument("--ack-no-camera-owner", action="store_true")

    sysid_capability = subparsers.add_parser(
        "sysid-capability",
        help="inspect the pinned official MuJoCo sysid toolbox and optional exercise",
    )
    sysid_capability.add_argument("--exercise", action="store_true")
    sysid_capability.add_argument("--output", type=Path, default=None)

    sysid_input = subparsers.add_parser(
        "sysid-input-report",
        help="verify physical payload integrity without interpreting video",
    )
    sysid_input.add_argument("--catalog", type=Path, default=DEFAULT_PHYSICAL_CATALOG)
    sysid_input.add_argument("--config", type=Path, default=DEFAULT_SYSID_CONFIG)
    sysid_input.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    sysid_input.add_argument(
        "--inspection-scope",
        choices=(
            "auto",
            "canonical_checkout",
            "isolated_codex_worktree",
            "explicit_repo_root",
        ),
        default="auto",
    )
    sysid_input.add_argument("--output", type=Path, default=None)

    sysid_split = subparsers.add_parser(
        "sysid-freeze-split",
        help="freeze evaluator-owned whole-episode train and held-out assignments",
    )
    sysid_split.add_argument("--catalog", type=Path, default=DEFAULT_PHYSICAL_CATALOG)
    sysid_split.add_argument("--config", type=Path, default=DEFAULT_SYSID_CONFIG)
    sysid_split.add_argument("--output", type=Path, required=True)
    sysid_split.add_argument(
        "--strategy",
        choices=("deterministic_hash", "leave_one_column_out"),
        default="deterministic_hash",
    )
    sysid_split.add_argument(
        "--held-out-column",
        choices=tuple("abcdefgh"),
        default=None,
    )

    sysid_fit = subparsers.add_parser(
        "sysid-fit",
        help="run staged bounded fits and require frozen held-out improvement",
    )
    sysid_fit.add_argument("--split", type=Path, required=True)
    sysid_fit.add_argument("--config", type=Path, default=DEFAULT_SYSID_CONFIG)
    sysid_fit.add_argument("--output", type=Path, required=True)
    sysid_fit.add_argument(
        "--backend",
        choices=("auto", "official", "local"),
        default="auto",
    )
    timing_fit = subparsers.add_parser(
        "sysid-fit-physical-timing",
        help="fit timing/control only from P4-eligible current physical recordings",
    )
    timing_fit.add_argument("--cohort", type=Path, required=True)
    timing_fit.add_argument("--config", type=Path, default=DEFAULT_SYSID_CONFIG)
    timing_fit.add_argument("--output", type=Path, required=True)
    timing_fit.add_argument(
        "--backend",
        choices=("auto", "official", "local"),
        default="auto",
    )
    timing_admission = subparsers.add_parser(
        "sysid-admit-physical-timing",
        help="independently replay one frozen P9 candidate with CPU/fp32 metrics",
    )
    timing_admission.add_argument("--fit", type=Path, required=True)
    timing_admission.add_argument("--cohort", type=Path, required=True)
    timing_admission.add_argument("--config", type=Path, default=DEFAULT_SYSID_CONFIG)
    timing_admission.add_argument("--output", type=Path, required=True)
    timing_admission.add_argument("--synthetic-fixture", action="store_true")
    twin_candidate = subparsers.add_parser(
        "twin-candidate-canary",
        help="compose one admitted geometry/timing candidate and exact canary",
    )
    twin_candidate.add_argument("--p9-admission", type=Path, required=True)
    twin_candidate.add_argument("--p13-transform", type=Path)
    twin_candidate.add_argument("--p13-board-fit", type=Path)
    twin_candidate.add_argument("--baseline", type=Path, default=DEFAULT_SYSID_CONFIG)
    twin_candidate.add_argument("--canary-input", type=Path)
    twin_candidate.add_argument(
        "--p10-cohort",
        type=Path,
        help="completed P10 cohort for the simulation-only stationary anchor",
    )
    twin_candidate.add_argument("--output", type=Path, required=True)
    twin_candidate.add_argument("--synthetic-fixture", action="store_true")
    twin_candidate.add_argument("--simulation-only", action="store_true")
    canary_contact = subparsers.add_parser(
        "canary-contact-preflight",
        help="audit one frozen P15 canary at every native MuJoCo step",
    )
    canary_contact.add_argument("--candidate", type=Path, required=True)
    canary_contact.add_argument("--canary", type=Path, required=True)
    canary_contact.add_argument("--baseline", type=Path, default=DEFAULT_SYSID_CONFIG)
    canary_contact.add_argument("--p8-intrinsics", type=Path)
    canary_contact.add_argument("--p8-distortion", type=Path)
    canary_contact.add_argument("--p9-admission", type=Path, required=True)
    canary_contact.add_argument("--p13-transform", type=Path)
    canary_contact.add_argument("--p13-board-fit", type=Path)
    canary_contact.add_argument(
        "--policy",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/zero_contact_canary_policy_v1.json",
    )
    canary_contact.add_argument("--output", type=Path, required=True)
    canary_contact.add_argument("--synthetic-fixture", action="store_true")
    canary_contact.add_argument("--simulation-only", action="store_true")

    actuator_external = subparsers.add_parser(
        "actuator-external-validate",
        help="run the frozen five-session actuator response validation once",
    )
    actuator_external.add_argument("--output", type=Path, required=True)

    source_eval = subparsers.add_parser(
        "source-eval",
        help="replay and score one canonical pawn source episode on CPU/fp32",
    )
    source_eval.add_argument("--episode", type=Path, required=True)
    source_eval.add_argument("--output", type=Path, default=None)

    source_expert = subparsers.add_parser(
        "source-expert",
        help="collect the bounded current-scene geometric source candidate",
    )
    source_expert.add_argument("--output", type=Path, required=True)
    source_expert.add_argument("--render-size", type=int, default=224)
    source_expert.add_argument("--expert-profile", type=Path, default=None)

    source_adapt = subparsers.add_parser(
        "source-adapt",
        help="derive admitted ACT or GR00T rows from one canonical source episode",
    )
    source_adapt.add_argument("--episode", type=Path, required=True)
    source_adapt.add_argument("--admission", type=Path, required=True)
    source_adapt.add_argument("--adapter", choices=("act", "groot"), required=True)
    source_adapt.add_argument("--output", type=Path, required=True)

    pawn_groot_export = subparsers.add_parser(
        "pawn-groot-export",
        help="export admitted 100 mm pawn sources as a GR00T LeRobot dataset",
    )
    pawn_groot_export.add_argument("--output", type=Path, required=True)
    pawn_groot_export.add_argument(
        "--source-episode", type=Path, action="append", required=True
    )

    pawn_groot_preflight = subparsers.add_parser(
        "pawn-groot-preflight",
        help="verify pawn GR00T payload and frozen action-chunk denominators",
    )
    pawn_groot_preflight.add_argument("--dataset", type=Path, required=True)
    pawn_groot_preflight.add_argument("--output", type=Path, required=True)

    multisource_export = subparsers.add_parser(
        "groot-multisource-export",
        help="merge only receipt-admitted GR00T datasets into the frozen video mixture",
    )
    multisource_export.add_argument("--output", type=Path, required=True)
    multisource_export.add_argument("--nominal-dataset", type=Path, required=True)
    multisource_export.add_argument("--recovery-dataset", type=Path, required=True)
    multisource_export.add_argument("--pawn-dataset", type=Path, required=True)

    multisource_preflight = subparsers.add_parser(
        "groot-multisource-preflight",
        help="verify multisource hashes, row/video alignment, and frozen H16 counts",
    )
    multisource_preflight.add_argument("--dataset", type=Path, required=True)
    multisource_preflight.add_argument("--output", type=Path, required=True)

    sim_real = subparsers.add_parser(
        "sim-real-bridge",
        help="verify physical-source availability and freeze the 72mm-to-100mm comparison boundary",
    )
    sim_real.add_argument("--physical-root", type=Path, default=None)
    sim_real.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/sim_real_bridge/receipt.json"),
    )

    pawn_composability = subparsers.add_parser(
        "pawn-composability-eval",
        help="measure pawn endpoint bias, offset sensitivity, and composition support",
    )
    pawn_composability.add_argument("--annotations", type=Path, required=True)
    pawn_composability.add_argument("--output", type=Path, required=True)

    pawn_demo_sim = subparsers.add_parser(
        "pawn-bg-demo-sim-eval",
        help="diagnostically replay owner-reviewed B-G teleoperation commands in simulation",
    )
    pawn_demo_sim.add_argument("--catalog", type=Path, required=True)
    pawn_demo_sim.add_argument("--source-root", type=Path, required=True)
    pawn_demo_sim.add_argument("--output", type=Path, required=True)

    pawn_source_fit = subparsers.add_parser(
        "pawn-bg-source-fit",
        help="fit and score a bounded non-calibrating B-G physical joint adapter",
    )
    pawn_source_fit.add_argument(
        "--source-repository-root",
        type=Path,
        required=True,
        help="read-only repository root containing the hash-bound physical source assets",
    )
    pawn_source_fit.add_argument("--output", type=Path, required=True)

    pawn_source_fit_visuals = subparsers.add_parser(
        "pawn-bg-source-fit-visuals",
        help="render a synchronized source/sim episode and source-fit score history",
    )
    pawn_source_fit_visuals.add_argument(
        "--source-repository-root", type=Path, required=True
    )
    pawn_source_fit_visuals.add_argument("--receipt", type=Path, required=True)
    pawn_source_fit_visuals.add_argument("--folder-label", required=True)
    pawn_source_fit_visuals.add_argument("--output-directory", type=Path, required=True)
    pawn_source_fit_visuals.add_argument(
        "--simulation-camera",
        choices=("c922-angle-transfer", "scene-overhead"),
        default="c922-angle-transfer",
        help="render from the proposal-derived C922 perspective or the legacy scene overhead",
    )
    pawn_source_fit_visuals.add_argument(
        "--trajectory-mode",
        choices=("measured-actual-state", "command-driven-physics"),
        default="measured-actual-state",
        help="render measured follower encoder states kinematically or unchanged command-driven physics",
    )

    camera_overlay = subparsers.add_parser(
        "camera-overlay",
        help="fit the physical camera to the board and render robot-anchored comparison views",
    )
    camera_overlay.add_argument(
        "--config",
        type=Path,
        default=Path("configs/experiments/robot_anchored_camera_overlay_v1.json"),
    )
    camera_overlay.add_argument("--recording-directory", type=Path, default=None)
    camera_overlay.add_argument(
        "--output-directory",
        type=Path,
        default=Path("outputs/sim_real_bridge/robot_anchored_overlay"),
    )

    studio_assets = subparsers.add_parser(
        "studio-assets",
        help="regenerate inspection-only workcell posters from the current scene",
    )
    studio_assets.add_argument(
        "--output-directory",
        type=Path,
        default=STUDIO_ASSET_ROOT,
    )

    groot_export = subparsers.add_parser(
        "groot-export",
        help="export evaluator-accepted dynamic chess demonstrations for GR00T N1.7",
    )
    groot_export.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/chess_pick_place_groot_v1"),
    )
    groot_export.add_argument("--max-episodes", type=int, default=None)
    groot_export.add_argument(
        "--control-mode",
        choices=("physics_ramp", "sample_hold"),
        default="physics_ramp",
    )
    groot_export.add_argument(
        "--episode-index",
        action="append",
        type=int,
        dest="episode_indices",
    )

    groot_expert = subparsers.add_parser(
        "groot-expert-eval",
        help="run one frozen scripted pick/place consequence evaluation",
    )
    groot_expert.add_argument(
        "--split",
        choices=("training", "held_out"),
        default="held_out",
    )
    groot_expert.add_argument("--episode-index", type=int, default=0)
    groot_expert.add_argument("--render-frames", action="store_true")
    groot_expert.add_argument(
        "--control-mode",
        choices=("physics_ramp", "sample_hold"),
        default="physics_ramp",
    )

    recovery_export = subparsers.add_parser(
        "groot-recovery-export",
        help="export evaluator-accepted GR00T recovery demonstrations",
    )
    recovery_export.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/chess_pick_place_groot_recovery_v2"),
    )
    recovery_export.add_argument(
        "--split",
        choices=("training", "held_out"),
        default="training",
    )
    recovery_export.add_argument("--max-episodes", type=int, default=None)

    recovery_expert = subparsers.add_parser(
        "groot-recovery-expert-eval",
        help="run one frozen GR00T recovery consequence evaluation",
    )
    recovery_expert.add_argument(
        "--split",
        choices=("training", "held_out"),
        default="held_out",
    )
    recovery_expert.add_argument("--episode-index", type=int, default=0)
    recovery_expert.add_argument("--render-frames", action="store_true")

    iphone_3dgs = subparsers.add_parser(
        "iphone-3dgs",
        help="build an ignored relative-scale 3D Gaussian splat from one MOV",
    )
    iphone_3dgs.add_argument("--video", type=Path, required=True)
    iphone_3dgs.add_argument("--output", type=Path, required=True)
    iphone_3dgs.add_argument("--ffmpeg", type=Path, required=True)
    iphone_3dgs.add_argument("--ffprobe", type=Path, required=True)
    iphone_3dgs.add_argument("--colmap", type=Path, required=True)
    iphone_3dgs.add_argument("--brush", type=Path, required=True)
    iphone_3dgs.add_argument("--keyframes", type=int, default=80)
    iphone_3dgs.add_argument("--holdout-fraction", type=float, default=0.125)
    iphone_3dgs.add_argument("--max-resolution", type=int, default=1920)
    iphone_3dgs.add_argument("--training-steps", type=int, default=30_000)
    iphone_3dgs.add_argument("--max-splats", type=int, default=2_000_000)
    iphone_3dgs.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        report = run_doctor(args.target, args.render_probe)
        print(doctor_json(report) if args.as_json else format_doctor(report))
        return 0 if report["passed"] else 1
    if args.command == "dev-loop-render-ledger":
        from .dev_loop.state import update_current_ledger_block

        root = args.root.resolve()
        project_state = json.loads(
            (root / "docs/autonomous-workflow/project_state.json").read_text(
                encoding="utf-8"
            )
        )
        ledger_path = root / ".factory/orchestration-ledger.md"
        current = ledger_path.read_text(encoding="utf-8")
        expected = update_current_ledger_block(current, project_state=project_state)
        if args.write:
            ledger_path.write_text(expected, encoding="utf-8")
        report = {
            "schema_version": "sim2claw.dev_loop_ledger_render.v1",
            "status": "written" if args.write else ("pass" if current == expected else "fail"),
            "path": str(ledger_path.relative_to(root)),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if args.write or current == expected else 1
    if args.command == "dev-loop-audit":
        from .dev_loop.state import audit_dev_loop_authority
        from .learning_factory_artifacts import atomic_write_json

        report = audit_dev_loop_authority(args.root)
        if args.output is not None:
            atomic_write_json(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "pass" else 1
    if args.command == "dev-loop-benchmark":
        from .dev_loop.bench import DevLoopBenchmarkError, run_dev_loop_benchmark

        try:
            report = run_dev_loop_benchmark(args.config, output_root=args.output)
        except DevLoopBenchmarkError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "dev-loop-verify":
        from .dev_loop.lifecycle import DevLoopLifecycleError
        from .dev_loop.runner import DevLoopRunnerError, run_test_with_receipt

        command = list(args.test_command)
        if command[:1] == ["--"]:
            command = command[1:]
        try:
            report = run_test_with_receipt(
                repo_root=args.root,
                command=command,
                relevant_paths=args.relevant_paths,
                receipt_root=args.receipt_root,
                tier=args.tier,
                wall_time_seconds=args.wall_time_seconds,
            )
        except (DevLoopRunnerError, DevLoopLifecycleError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return int(report["exit_code"])
    if args.command == "fetch-polycam":
        print(json.dumps(fetch_capture(), indent=2, sort_keys=True))
        return 0
    if args.command == "render":
        report = render_scene(
            output_path=args.output,
            width=args.width,
            height=args.height,
            settle_steps=args.settle_steps,
            camera=args.camera,
            scan_overlay=args.scan_overlay,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "compare-alignment":
        report = compare_alignment(
            args.photo,
            output_directory=args.output_directory,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "scene-info":
        print(json.dumps(scene_summary(), indent=2, sort_keys=True))
        return 0
    if args.command == "grasp-probe":
        from dataclasses import asdict

        from .grasp import run_grasp_probe

        report = run_grasp_probe(
            arm=args.arm,
            piece=args.piece,
            render_frames=not args.no_frames,
        )
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
        return 0 if report.success else 1
    if args.command == "act-train":
        from .act_train import train_act

        print(json.dumps(train_act(), indent=2, sort_keys=True))
        return 0
    if args.command == "act-eval":
        from .act_evaluator import evaluate_act

        report = evaluate_act(
            args.checkpoint,
            render_video=not args.no_video,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["success"] else 1
    if args.command == "act-contact-sensitivity":
        from .contact_sensitivity import run_contact_sensitivity

        report = run_contact_sensitivity(
            args.checkpoint,
            output_directory=args.output_directory,
            render_video=args.render_video,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "studio":
        from .studio_server import serve_studio

        serve_studio(
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
            read_only=args.read_only,
            enable_physical_demo=args.enable_physical_demo,
        )
        return 0
    if args.command == "project-pack":
        from .project_bundle import pack_project

        report = pack_project(args.project, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "project-inspect":
        from .project_bundle import ProjectBundleError, inspect_bundle, inspect_project

        report = inspect_project(args.project)
        if args.bundle is not None:
            if args.expected_bundle_sha256 is None:
                raise ProjectBundleError(
                    "--expected-bundle-sha256 is required when --bundle is supplied"
                )
            report["bundle"] = inspect_bundle(
                args.bundle,
                expected_sha256=args.expected_bundle_sha256,
            )
        elif args.expected_bundle_sha256 is not None:
            raise ProjectBundleError(
                "--expected-bundle-sha256 is valid only when --bundle is supplied"
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "pipeline-stage":
        from .autonomous_pipeline import run_stage

        report = run_stage(args.stage, args.project)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "pipeline-status":
        from .autonomous_pipeline import pipeline_status
        from .project_bundle import inspect_project

        inspect_project(args.project)
        print(json.dumps(pipeline_status(args.project), indent=2, sort_keys=True))
        return 0
    if args.command == "factory-inspect":
        from .learning_factory import LearningFactory

        print(
            json.dumps(
                LearningFactory(
                    args.project,
                    generation=args.generation,
                    parent_generation=args.parent_generation,
                ).inspect(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "factory-status":
        from .learning_factory import LearningFactory

        print(
            json.dumps(
                LearningFactory(
                    args.project,
                    generation=args.generation,
                    parent_generation=args.parent_generation,
                ).status(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "factory-run":
        from .learning_factory import LearningFactory, LearningFactoryError

        factory = LearningFactory(
            args.project,
            generation=args.generation,
            parent_generation=args.parent_generation,
        )
        if args.run_next:
            if args.through_stage is not None:
                raise LearningFactoryError("--through requires --from")
            report = factory.run_next()
        elif args.resume:
            if args.through_stage is not None:
                raise LearningFactoryError("--through cannot be combined with --resume")
            report = factory.resume()
        else:
            if args.through_stage is None:
                raise LearningFactoryError("--through is required with --from")
            report = factory.run_range(args.from_stage, args.through_stage)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "factory-explain":
        from .learning_factory import LearningFactory

        print(
            json.dumps(
                LearningFactory(
                    args.project,
                    generation=args.generation,
                    parent_generation=args.parent_generation,
                ).explain(args.stage),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "factory-recurse":
        from .learning_factory import LearningFactory, LearningFactoryError

        factory = LearningFactory(
            args.project,
            generation=args.generation,
            parent_generation=args.parent_generation,
        )
        targets = args.target
        if targets is None:
            latest = factory._load_latest("LF-12")
            if latest is None or latest["status"] != "passed":
                raise LearningFactoryError(
                    "LF-12 must pass before inferred counterexample recursion"
                )
            targets = list((latest.get("output") or {}).get("route_targets") or [])
        report = factory.fork_generation(
            route_targets=list(targets), through=args.through
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "factory-act-evidence":
        from .learning_factory_artifacts import (
            atomic_write_json,
            bind_narrow_act_evidence,
        )

        report = bind_narrow_act_evidence(
            args.training_receipt, args.evaluation_receipt
        )
        if args.output is not None:
            atomic_write_json(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "teleop-preflight":
        from .teleop_recording import recorder_preflight

        report = recorder_preflight()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["modes"]["simulation_follower"]["ready"] else 1
    if args.command == "physical-gateway-preflight":
        from .teleop_recording import physical_gateway_preflight

        print(json.dumps(physical_gateway_preflight(), indent=2, sort_keys=True))
        return 0
    if args.command == "inspect-robots-offline":
        try:
            from .inspect_robots_adapter import (
                InspectRobotsIntegrationError,
                run_offline_slice,
            )
        except ImportError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        try:
            report = run_offline_slice(
                fixture_path=args.fixture,
                output_dir=args.output_dir,
            )
        except InspectRobotsIntegrationError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "physical-measurement-baseline":
        from .current_workcell_measurement import capture_torque_off_baseline

        report = capture_torque_off_baseline(
            args.output,
            sample_count=args.samples,
            sample_interval_seconds=args.interval_seconds,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "empty-gripper-diagnose":
        from .empty_gripper_diagnostic import (
            EmptyGripperDiagnosticError,
            derive_empty_gripper_diagnostic,
        )

        try:
            report = derive_empty_gripper_diagnostic(
                args.output,
                contract_path=args.config,
            )
        except EmptyGripperDiagnosticError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "joint-limit-compare":
        from .joint_limit_comparison import (
            JointLimitComparisonError,
            run_joint_limit_comparison,
        )

        try:
            report = run_joint_limit_comparison(
                args.output,
                contract_path=args.config,
            )
        except JointLimitComparisonError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "joint-identifiability":
        from .joint_identifiability import (
            JointIdentifiabilityError,
            derive_joint_identifiability_report,
        )

        try:
            report = derive_joint_identifiability_report(
                args.output,
                contract_path=args.config,
            )
        except JointIdentifiabilityError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "physical-replay":
        from .physical_trace_replay import (
            PhysicalTraceReplayError,
            run_physical_trace_replay,
        )

        try:
            report = run_physical_trace_replay(
                args.recording,
                operator_acknowledged=args.yes,
                progress=lambda row: print(
                    json.dumps(row, separators=(",", ":"), sort_keys=True),
                    flush=True,
                ),
            )
        except PhysicalTraceReplayError as error:
            print(
                json.dumps(
                    {
                        "error": str(error),
                        "run_directory": (
                            str(error.run_directory)
                            if error.run_directory is not None
                            else None
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "hil-identifiability":
        from .hil_identifiability import (
            HILIdentifiabilityError,
            run_hil_campaign,
        )

        try:
            report = run_hil_campaign(
                args.config,
                args.output,
                operator_acknowledged=args.yes,
                packet_id=args.packet,
            )
        except HILIdentifiabilityError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "hil-simulator-compare":
        from .hil_simulator_comparison import (
            HILSimulatorComparisonError,
            run_hil_simulator_comparison,
        )

        try:
            report = run_hil_simulator_comparison(
                args.output,
                contract_path=args.config,
            )
        except HILSimulatorComparisonError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "hil-compile-evidence":
        from .hil_evidence import HILEvidenceError, compile_hil_evidence

        try:
            report = compile_hil_evidence(
                args.campaign,
                args.output,
                contract_path=args.config,
            )
        except HILEvidenceError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "hil-analyze-traces":
        from .hil_trace_analysis import (
            HILTraceAnalysisError,
            derive_hil_trace_report,
        )

        try:
            report = derive_hil_trace_report(
                args.output,
                contract_path=args.config,
            )
        except HILTraceAnalysisError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "hil-decompose-traces":
        from .hil_trace_decomposition import (
            HILTraceDecompositionError,
            derive_hil_trace_decomposition,
        )

        try:
            report = derive_hil_trace_decomposition(
                args.output,
                contract_path=args.config,
            )
        except HILTraceDecompositionError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-inventory":
        from .sail.contracts import SailContractError
        from .sail.evidence import inventory_campaign

        try:
            report = inventory_campaign(args.campaign)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-evidence":
        from .sail.contracts import SailContractError
        from .sail.evidence import compile_campaign

        try:
            report = compile_campaign(args.campaign, args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-residuals":
        from .sail.contracts import SailContractError
        from .sail.residuals import compile_residuals

        try:
            report = compile_residuals(args.config, args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-belief-graph":
        from .sail.belief_graph import compile_belief_graph
        from .sail.contracts import SailContractError

        try:
            report = compile_belief_graph(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-structural-surprise":
        from .sail.contracts import SailContractError
        from .sail.structural_surprise import compile_structural_surprise

        try:
            report = compile_structural_surprise(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-mechanisms":
        from .sail.contracts import SailContractError
        from .sail.posterior import compile_mechanisms

        try:
            report = compile_mechanisms(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-loop-closure":
        from .sail.contracts import SailContractError
        from .sail.loop_closure import compile_loop_closure

        try:
            report = compile_loop_closure(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-invariance":
        from .sail.contracts import SailContractError
        from .sail.invariance import compile_invariance

        try:
            report = compile_invariance(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-acquisition":
        from .sail.acquisition import compile_acquisition
        from .sail.contracts import SailContractError

        try:
            report = compile_acquisition(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-run-live-operator":
        from .sail.contracts import SailContractError
        from .sail.live_operator import run_live_operator

        try:
            report = run_live_operator(
                args.config,
                output_root=args.output,
                measurement_evaluator_receipt_path=args.measurement_evaluator_receipt,
                trusted_adapter_request_path=args.trusted_adapter_request,
            )
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-benchmark":
        from .sail.benchmark import compile_benchmark
        from .sail.contracts import SailContractError
        try:
            report = compile_benchmark(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-executed-benchmark":
        from .sail.contracts import SailContractError
        from .sail.executed_benchmark import compile_executed_benchmark

        try:
            report = compile_executed_benchmark(
                args.config, output_root=args.output
            )
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-inspect-campaign":
        from .sail.agent_campaign import compile_campaign
        from .sail.contracts import SailContractError
        try:
            report = compile_campaign(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-retrospective-case":
        from .sail.contracts import SailContractError
        from .sail.retrospective_case import compile_case
        try:
            report = compile_case(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-run-prospective-simulator":
        from .sail.contracts import SailContractError
        from .sail.prospective_simulator import run_campaign
        try:
            report = run_campaign(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-twin-capability":
        from .sail.capability_campaign import compile_campaign
        from .sail.contracts import SailContractError
        try:
            report = compile_campaign(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-run-policy-flywheel":
        from .sail.contracts import SailContractError
        from .sail.policy_flywheel_campaign import compile_campaign
        try:
            report = compile_campaign(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-studio-observatory":
        from .sail.contracts import SailContractError
        from .sail.studio import compile_studio_observatory

        try:
            report = compile_studio_observatory(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sail-compile-publication":
        from .sail.contracts import SailContractError
        from .sail.publication import compile_publication

        try:
            report = compile_publication(args.config, output_root=args.output)
        except SailContractError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "replay-recorded":
        from .recorded_replay import ReplayContractError, replay_recorded_episode

        try:
            report = replay_recorded_episode(
                args.episode,
                config_path=args.config,
                output_directory=args.output,
                parameter_values=_parameter_assignments(args.parameter),
            )
        except (ReplayContractError, ValueError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "replay-eligibility-audit":
        from .replay_eligibility import audit_and_write_exact_replay_manifest

        report = audit_and_write_exact_replay_manifest(
            args.manifest,
            args.output,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["exact_replay_eligible"] else 1
    if args.command == "physical-recording-replay-eligibility":
        from .replay_eligibility import (
            materialize_physical_recording_exact_replay,
        )

        try:
            report = materialize_physical_recording_exact_replay(
                args.recording,
                args.manifest_output,
                args.report_output,
            )
        except ValueError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["exact_replay_eligible"] else 1
    if args.command == "replay-eligible-physical-recording":
        from .recorded_replay import (
            ReplayContractError,
            replay_exact_eligible_physical_recording,
        )

        try:
            receipt = replay_exact_eligible_physical_recording(
                args.recording,
                args.manifest,
                config_path=args.config,
                output_directory=args.output,
            )
        except (ReplayContractError, ValueError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "zero-displacement-hold-record":
        from .physical_gateway import PhysicalGatewayError
        from .teleop_recording import (
            RecorderError,
            run_zero_displacement_hold_packet,
        )

        try:
            receipt = run_zero_displacement_hold_packet(
                args.packet,
                operator_acknowledged=args.yes,
            )
        except (OSError, ValueError, RecorderError, PhysicalGatewayError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    if args.command == "physical-excitation":
        from .physical_gateway import PhysicalGatewayError
        from .teleop_recording import (
            RecorderError,
            compile_physical_excitation_packet,
            execute_physical_excitation_packet,
            reposition_physical_follower,
        )

        try:
            if args.phase == "compile":
                if args.output is not None or args.dry_run:
                    raise RecorderError(
                        "--output and --dry-run are only valid during reposition."
                    )
                result = compile_physical_excitation_packet(args.packet)
            elif args.phase == "reposition":
                if args.yes and args.dry_run:
                    raise RecorderError("Choose either --yes or --dry-run.")
                if not args.dry_run and args.output is None:
                    raise RecorderError(
                        "--output is required for a live reposition."
                    )
                result = reposition_physical_follower(
                    args.packet,
                    output_path=args.output,
                    dry_run=args.dry_run,
                    operator_acknowledged=args.yes,
                )
            else:
                if args.dry_run:
                    raise RecorderError("--dry-run is only valid during reposition.")
                if args.output is None:
                    raise RecorderError("--output is required during execution.")
                result = execute_physical_excitation_packet(
                    args.packet,
                    args.output,
                    operator_acknowledged=args.yes,
                )
        except (OSError, ValueError, RecorderError, PhysicalGatewayError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "physical-canary":
        from .physical_canary import (
            PhysicalCanaryError,
            compile_physical_canary_normalization,
            compile_physical_canary_packet,
            execute_physical_canary_normalization,
            execute_physical_canary_packet,
        )

        try:
            if args.phase == "normalize":
                if args.yes:
                    if args.output is None:
                        raise PhysicalCanaryError(
                            "--output is required for live normalization"
                        )
                    if (
                        args.bundle is not None
                        or args.contact_receipt is not None
                        or args.normalization_receipt is not None
                    ):
                        raise PhysicalCanaryError(
                            "bundle/receipt inputs are only valid during canary compilation"
                        )
                    result = execute_physical_canary_normalization(
                        args.packet, args.output, operator_acknowledged=True
                    )
                else:
                    if args.output is not None:
                        raise PhysicalCanaryError(
                            "--output is only valid for live normalization"
                        )
                    result = compile_physical_canary_normalization(args.packet)
            elif args.phase == "compile":
                if args.yes or args.output is not None:
                    raise PhysicalCanaryError(
                        "--yes/--output are only valid during execution or live normalization"
                    )
                if not all(
                    value is not None
                    for value in (
                        args.bundle,
                        args.contact_receipt,
                        args.normalization_receipt,
                    )
                ):
                    raise PhysicalCanaryError(
                        "--bundle, --contact-receipt, and --normalization-receipt are required"
                    )
                result = compile_physical_canary_packet(
                    args.bundle,
                    args.packet,
                    contact_receipt_path=args.contact_receipt,
                    normalization_receipt_path=args.normalization_receipt,
                )
            else:
                if not args.yes or args.output is None:
                    raise PhysicalCanaryError(
                        "--yes and --output are required for physical canary execution"
                    )
                result = execute_physical_canary_packet(
                    args.packet, args.output, operator_acknowledged=True
                )
        except (OSError, ValueError, PhysicalCanaryError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "geometric-physical":
        from .geometric_physical_gateway import (
            GeometricPhysicalGatewayError,
            compile_geometric_physical_packet,
            execute_geometric_physical_packet,
            review_geometric_physical_packet,
        )

        try:
            if args.phase == "compile":
                if (
                    args.episode is None
                    or args.admission is None
                    or args.candidate_manifest is None
                    or args.review is not None
                    or args.output is not None
                    or args.reviewer is not None
                    or args.decision_id is not None
                    or args.yes
                ):
                    raise GeometricPhysicalGatewayError(
                        "compile requires --episode, --admission, and "
                        "--candidate-manifest only"
                    )
                result = compile_geometric_physical_packet(
                    args.episode,
                    args.admission,
                    args.candidate_manifest,
                    args.packet,
                )
            elif args.phase == "review":
                if (
                    args.output is None
                    or not args.reviewer
                    or not args.decision_id
                    or args.episode is not None
                    or args.admission is not None
                    or args.candidate_manifest is not None
                    or args.review is not None
                    or args.yes
                ):
                    raise GeometricPhysicalGatewayError(
                        "review requires --output, --reviewer, and --decision-id only"
                    )
                result = review_geometric_physical_packet(
                    args.packet,
                    args.output,
                    reviewer=args.reviewer,
                    decision_id=args.decision_id,
                )
            else:
                if (
                    args.review is None
                    or args.output is None
                    or not args.yes
                    or args.episode is not None
                    or args.admission is not None
                    or args.candidate_manifest is not None
                    or args.reviewer is not None
                    or args.decision_id is not None
                ):
                    raise GeometricPhysicalGatewayError(
                        "execute requires --review, --output, and --yes only"
                    )
                result = execute_geometric_physical_packet(
                    args.packet,
                    args.review,
                    args.output,
                    operator_acknowledged=True,
                )
        except (
            OSError,
            TypeError,
            ValueError,
            GeometricPhysicalGatewayError,
        ) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "wrist-view-reposition":
        from .wrist_view_reposition import (
            WristViewRepositionError,
            compile_wrist_view_reposition_packet,
            execute_wrist_view_reposition_stage,
            review_wrist_view_reposition_packet,
        )

        try:
            if args.phase == "compile":
                if (
                    args.candidate_manifest is None
                    or args.route is None
                    or args.output is not None
                    or args.review is not None
                    or args.stage is not None
                    or args.prior_receipt is not None
                    or args.reviewer is not None
                    or args.decision_id is not None
                    or args.yes
                ):
                    raise WristViewRepositionError(
                        "compile requires only --packet, --candidate-manifest, and --route"
                    )
                result = compile_wrist_view_reposition_packet(
                    args.packet,
                    candidate_manifest_path=args.candidate_manifest,
                    route_path=args.route,
                )
            elif args.phase == "review":
                if (
                    args.output is None
                    or not args.reviewer
                    or not args.decision_id
                    or args.candidate_manifest is not None
                    or args.route is not None
                    or args.review is not None
                    or args.stage is not None
                    or args.prior_receipt is not None
                    or args.yes
                ):
                    raise WristViewRepositionError(
                        "review requires --packet, --output, --reviewer, and --decision-id"
                    )
                result = review_wrist_view_reposition_packet(
                    args.packet,
                    args.output,
                    reviewer=args.reviewer,
                    decision_id=args.decision_id,
                )
            else:
                if (
                    not args.yes
                    or args.review is None
                    or args.output is None
                    or args.stage is None
                    or args.candidate_manifest is not None
                    or args.route is not None
                    or args.reviewer is not None
                    or args.decision_id is not None
                ):
                    raise WristViewRepositionError(
                        "execute requires --packet, --review, --output, --stage, and --yes"
                    )
                result = execute_wrist_view_reposition_stage(
                    args.packet,
                    args.review,
                    args.output,
                    stage_index=args.stage,
                    prior_receipt_path=args.prior_receipt,
                    operator_acknowledged=True,
                )
        except (OSError, ValueError, WristViewRepositionError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "live-anchored-camera-reposition":
        from .live_anchored_camera_reposition import (
            LiveAnchoredCameraRepositionError,
            execute_live_anchored_camera_reposition,
        )

        try:
            result = execute_live_anchored_camera_reposition(
                route_path=args.route,
                candidate_manifest_path=args.candidate_manifest,
                output_root=args.output,
                operator_acknowledged=args.yes,
            )
        except (OSError, ValueError, LiveAnchoredCameraRepositionError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "c922-calibration-acquisition-preflight":
        from .c922_calibration_acquisition import preflight_and_write

        report = preflight_and_write(args.plan, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["capture_ready"] else 1
    if args.command == "c922-calibration-acquire":
        from .c922_calibration_acquisition import acquire_corpus
        from .c922_exact_mode_calibration import C922CalibrationError
        from .overhead_video import OverheadVideoError

        try:
            report = acquire_corpus(args.plan, args.output, dry_run=args.dry_run)
        except (OSError, ValueError, C922CalibrationError, OverheadVideoError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "metrology-transaction-preflight":
        from .metrology_transaction import (
            MetrologyTransactionError,
            preflight_and_write,
        )

        try:
            report = preflight_and_write(args.transaction, args.output)
        except (OSError, ValueError, MetrologyTransactionError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "ready_for_live_capture_sequence" else 1
    if args.command == "d405-apriltag-observe":
        from .d405_apriltag_observation import (
            D405AprilTagObservationError,
            observe_d405_apriltag,
        )

        try:
            report = observe_d405_apriltag(
                source_path=args.source,
                output_path=args.output,
                contract_path=args.contract,
                capture_report_path=args.capture_report,
                selected_frame_output=args.selected_frame_output,
            )
        except (OSError, ValueError, D405AprilTagObservationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "target_observed" else 1
    if args.command == "static-tricam-capture":
        from .static_tricam_capture import (
            StaticTricamCaptureError,
            capture_static_tricam_bundle,
        )

        try:
            report = capture_static_tricam_bundle(
                output_root=args.output,
                operator_acknowledged=args.yes,
                camera_session_token=args.camera_session_token,
                fixed_mount_token=args.fixed_mount_token,
                contract_path=args.contract,
            )
        except (OSError, ValueError, StaticTricamCaptureError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "d405-rgbd-readiness":
        from .d405_rgbd_readiness import (
            D405RGBDReadinessError,
            inventory_d405_rgbd_readiness,
        )

        try:
            report = inventory_d405_rgbd_readiness(
                output_path=args.output,
                enumeration_file=args.enumeration_file,
            )
        except (OSError, ValueError, D405RGBDReadinessError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return (
            0
            if report["status"] == "metric_depth_calibration_enumerated"
            else 1
        )
    if args.command == "workcell-registration":
        from .workcell_registration import (
            WorkcellRegistrationError,
            evaluate_stationary_registration,
            write_survey_worksheet,
        )

        try:
            if args.phase == "worksheet":
                if args.survey is not None or args.manifest is not None:
                    raise WorkcellRegistrationError(
                        "Worksheet phase accepts only --output."
                    )
                report = write_survey_worksheet(args.output)
            else:
                if args.survey is None or args.manifest is None:
                    raise WorkcellRegistrationError(
                        "Evaluate phase requires --survey and --manifest."
                    )
                report = evaluate_stationary_registration(
                    survey_path=args.survey,
                    manifest_path=args.manifest,
                    output_directory=args.output,
                )
        except (OSError, ValueError, WorkcellRegistrationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "workcell-registration-input":
        from .workcell_registration import WorkcellRegistrationError
        from .workcell_registration_acquisition import (
            capture_stationary_bundle,
            finalize_metric_registration_input,
            write_annotation_bundle,
        )

        try:
            if args.phase == "capture":
                report = capture_stationary_bundle(
                    args.output,
                    acknowledgements={
                        "board_and_camera_fixed": args.ack_board_camera_fixed,
                        "board_cleared": args.ack_board_cleared,
                        "a1_h1_a8_markers_visible": args.ack_markers_visible,
                        "focus_locked": args.ack_focus_locked,
                        "no_competing_camera_owner": args.ack_no_camera_owner,
                    },
                    focus_setting=args.focus_setting,
                    dry_run=args.dry_run,
                )
            elif args.phase == "bundle":
                if args.capture_receipt is None:
                    raise WorkcellRegistrationError(
                        "Bundle phase requires --capture-receipt."
                    )
                report = write_annotation_bundle(
                    args.capture_receipt, args.output
                )
            else:
                required = {
                    "capture_receipt_path": args.capture_receipt,
                    "annotator_a_path": args.annotator_a,
                    "annotator_b_path": args.annotator_b,
                    "board_measurement_path": args.board_measurement,
                    "survey_path": args.survey,
                    "intrinsics_path": args.intrinsics,
                    "distortion_path": args.distortion,
                }
                if any(value is None for value in required.values()):
                    raise WorkcellRegistrationError(
                        "Finalize phase requires capture, two annotations, board "
                        "measurement, survey, intrinsics, and distortion."
                    )
                report = finalize_metric_registration_input(
                    **required,
                    output_path=args.output,
                )
        except (OSError, ValueError, WorkcellRegistrationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sysid-capability":
        from .system_identification import (
            mujoco_sysid_capability,
            write_mujoco_sysid_capability,
        )

        report = (
            write_mujoco_sysid_capability(args.output, exercise=args.exercise)
            if args.output is not None
            else mujoco_sysid_capability(exercise=args.exercise)
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        passed = report["compatible"] and (
            not args.exercise or report["official_surface_exercised"]
        )
        return 0 if passed else 1
    if args.command == "sysid-input-report":
        from .system_identification import inspect_recording_catalog_inputs

        report = inspect_recording_catalog_inputs(
            args.catalog,
            repo_root=args.repo_root,
            config_path=args.config,
            inspection_scope=args.inspection_scope,
            output_path=args.output,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["joint_timing_replay_ready"] else 1
    if args.command == "sysid-freeze-split":
        from .system_identification import (
            SystemIdentificationError,
            freeze_episode_split,
        )

        try:
            report = freeze_episode_split(
                args.catalog,
                args.config,
                args.output,
                strategy=args.strategy,
                held_out_column=args.held_out_column,
            )
        except SystemIdentificationError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sysid-fit":
        from .recorded_replay import ReplayContractError
        from .system_identification import (
            SystemIdentificationError,
            run_system_identification,
        )

        try:
            report = run_system_identification(
                args.split,
                config_path=args.config,
                output_directory=args.output,
                backend=args.backend,
            )
        except (ReplayContractError, SystemIdentificationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["calibration_success"] else 1
    if args.command == "sysid-fit-physical-timing":
        from .recorded_replay import ReplayContractError
        from .system_identification import (
            SystemIdentificationError,
            run_physical_timing_actuation_cohort,
        )

        try:
            report = run_physical_timing_actuation_cohort(
                args.cohort,
                config_path=args.config,
                output_directory=args.output,
                backend=args.backend,
            )
        except (OSError, ValueError, ReplayContractError, SystemIdentificationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "diagnostic_fit_complete" else 1
    if args.command == "sysid-admit-physical-timing":
        from .recorded_replay import ReplayContractError
        from .system_identification import SystemIdentificationError
        from .timing_admission import admit_physical_timing_actuation_fit

        try:
            report = admit_physical_timing_actuation_fit(
                args.fit,
                args.cohort,
                config_path=args.config,
                output_path=args.output,
                synthetic_fixture_mode=args.synthetic_fixture,
            )
        except (OSError, ValueError, ReplayContractError, SystemIdentificationError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "twin-candidate-canary":
        from .twin_candidate import (
            TwinCandidateError,
            compose_twin_candidate_and_canary,
        )

        try:
            report = compose_twin_candidate_and_canary(
                p9_admission_path=args.p9_admission,
                p13_transform_path=args.p13_transform,
                p13_board_fit_path=args.p13_board_fit,
                baseline_config_path=args.baseline,
                canary_input_path=args.canary_input,
                output_directory=args.output,
                synthetic_fixture_mode=args.synthetic_fixture,
                simulation_only=args.simulation_only,
                p10_cohort_path=args.p10_cohort,
            )
        except (OSError, ValueError, TwinCandidateError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "canary-contact-preflight":
        from .canary_contact_preflight import (
            CanaryContactError,
            evaluate_canary_contact_preflight,
        )

        try:
            report = evaluate_canary_contact_preflight(
                candidate_path=args.candidate,
                canary_path=args.canary,
                baseline_path=args.baseline,
                p8_intrinsics_path=args.p8_intrinsics,
                p8_distortion_path=args.p8_distortion,
                p9_admission_path=args.p9_admission,
                p13_transform_path=args.p13_transform,
                p13_board_fit_path=args.p13_board_fit,
                policy_path=args.policy,
                output_path=args.output,
                synthetic_fixture_mode=args.synthetic_fixture,
                simulation_only=args.simulation_only,
            )
        except (OSError, ValueError, CanaryContactError) as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["native_contact_audit"]["passed"] else 1
    if args.command == "actuator-external-validate":
        from .actuator_external_validation import (
            ActuatorExternalValidationError,
            run_actuator_external_validation,
        )

        try:
            report = run_actuator_external_validation(args.output)
        except ActuatorExternalValidationError as error:
            print(json.dumps({"error": str(error)}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "source-eval":
        from .pawn_source_evaluator import evaluate_source_episode

        output = args.output or args.episode / "admission_verdict.json"
        report = evaluate_source_episode(args.episode, output_path=output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["strict_success"] else 1
    if args.command == "source-expert":
        from .pawn_source_expert import collect_pawn_source_expert_candidate

        report = collect_pawn_source_expert_candidate(
            args.output,
            render_size=args.render_size,
            expert_profile_path=args.expert_profile,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "source-adapt":
        from .source_episode import adapt_source_episode, sha256_file

        admission = json.loads(args.admission.read_text(encoding="utf-8"))
        rows = adapt_source_episode(
            args.episode,
            adapter=args.adapter,
            admission_verdict=admission,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "adapter": args.adapter,
                    "row_count": len(rows),
                    "output": str(args.output),
                    "output_sha256": sha256_file(args.output),
                    "training_promoted": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "pawn-groot-export":
        from .pawn_groot_dataset import export_pawn_groot_dataset

        report = export_pawn_groot_dataset(
            args.output,
            source_directories=args.source_episode,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "pawn-groot-preflight":
        from .pawn_groot_dataset import preflight_pawn_groot_dataset

        report = preflight_pawn_groot_dataset(
            args.dataset,
            output_path=args.output,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "groot-multisource-export":
        from .groot_multisource_dataset import export_groot_multisource_dataset

        report = export_groot_multisource_dataset(
            args.output,
            nominal_dataset=args.nominal_dataset,
            recovery_dataset=args.recovery_dataset,
            pawn_dataset=args.pawn_dataset,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "groot-multisource-preflight":
        from .groot_multisource_dataset import preflight_groot_multisource_dataset

        report = preflight_groot_multisource_dataset(
            args.dataset,
            output_path=args.output,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "sim-real-bridge":
        from .sim_real_bridge import inspect_sim_real_bridge

        report = inspect_sim_real_bridge(
            physical_root=args.physical_root,
            output_path=args.output,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["comparison_readiness"]["joint_response_calibration_ready"] else 1
    if args.command == "pawn-composability-eval":
        from .pawn_composability_eval import evaluate_composability

        report = evaluate_composability(args.annotations, args.output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "complete_descriptive_evaluation" else 2
    if args.command == "pawn-bg-demo-sim-eval":
        from .pawn_bg_demo_sim import evaluate_demo_catalog

        report = evaluate_demo_catalog(
            catalog_path=args.catalog,
            source_root=args.source_root,
            output_path=args.output,
        )
        print(json.dumps(report["by_variant"], indent=2, sort_keys=True))
        return 0
    if args.command == "pawn-bg-source-fit":
        from .pawn_bg_source_fit import optimize_pawn_bg_source_fit

        report = optimize_pawn_bg_source_fit(
            source_repository_root=args.source_repository_root,
            output_path=args.output,
        )
        summary = {
            "baseline": report["baseline"]["nominal_physics"]["aggregate"],
            "optimization_status": report["optimization_status"],
            "candidate_accepted": report["candidate_accepted"],
            "accepted_adapter": report["accepted_adapter"],
            "best_candidate_adapter": report["best_candidate_adapter"],
            "best_candidate_kinematic": {
                key: value for key, value in report["best_candidate_kinematic"].items()
                if key != "events"
            },
            "final_contact_variants": {
                key: value["aggregate"]
                for key, value in report["final_contact_variants"].items()
            },
            "claim_boundary": report["claim_boundary"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.command == "pawn-bg-source-fit-visuals":
        from .pawn_bg_source_fit_visuals import (
            render_episode_comparison,
            render_score_history,
        )

        comparison = render_episode_comparison(
            source_repository_root=args.source_repository_root,
            source_fit_receipt_path=args.receipt,
            folder_label=args.folder_label,
            output_directory=args.output_directory,
            simulation_camera_mode=args.simulation_camera.replace("-", "_"),
            trajectory_mode=args.trajectory_mode.replace("-", "_"),
        )
        history = render_score_history(
            source_fit_receipt_path=args.receipt,
            output_directory=args.output_directory,
        )
        print(json.dumps({
            "comparison": comparison,
            "score_history": history,
        }, indent=2, sort_keys=True))
        return 0
    if args.command == "camera-overlay":
        from .robot_anchored_overlay import build_robot_anchored_overlay

        report = build_robot_anchored_overlay(
            config_path=args.config,
            recording_directory=args.recording_directory,
            output_directory=args.output_directory,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "studio-assets":
        from .studio_assets import render_studio_assets

        print(
            json.dumps(
                render_studio_assets(args.output_directory),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "groot-export":
        from .groot_chess import export_groot_dataset

        report = export_groot_dataset(
            args.output,
            max_episodes=args.max_episodes,
            control_mode=args.control_mode,
            episode_indices=args.episode_indices,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "groot-expert-eval":
        from .groot_chess import (
            collect_groot_expert_episode,
            load_groot_task_contract,
        )

        task = load_groot_task_contract()
        episode = collect_groot_expert_episode(
            task,
            split=args.split,
            episode_index=args.episode_index,
            render_frames=args.render_frames,
            control_mode=args.control_mode,
        )
        report = {
            "case_id": episode.case_id,
            "instruction": episode.instruction,
            "piece": episode.piece,
            "target_square": episode.target_square,
            "seed": episode.seed,
            "sample_count": int(episode.states.shape[0]),
            "maximum_ik_residual_m": episode.maximum_ik_residual_m,
            "verdict": episode.verdict,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if episode.verdict["success"] else 1
    if args.command == "groot-recovery-export":
        from .groot_chess_recovery import export_recovery_dataset

        report = export_recovery_dataset(
            args.output,
            split=args.split,
            max_episodes=args.max_episodes,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "groot-recovery-expert-eval":
        from .groot_chess_recovery import (
            collect_recovery_expert_episode,
            load_recovery_task_contract,
        )

        task = load_recovery_task_contract()
        episode = collect_recovery_expert_episode(
            task,
            split=args.split,
            episode_index=args.episode_index,
            render_frames=args.render_frames,
        )
        report = {
            "case_id": episode.case_id,
            "instruction": episode.instruction,
            "piece": episode.piece,
            "target_square": episode.target_square,
            "seed": episode.seed,
            "perturbation": episode.perturbation,
            "sample_count": int(episode.states.shape[0]),
            "maximum_ik_residual_m": episode.maximum_ik_residual_m,
            "contact_metrics": episode.contact_metrics,
            "verdict": episode.verdict,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if episode.verdict["success"] else 1
    if args.command == "iphone-3dgs":
        from .iphone_3dgs import PipelineConfig, run_iphone_3dgs

        report = run_iphone_3dgs(
            PipelineConfig(
                video=args.video,
                output=args.output,
                ffmpeg_binary=args.ffmpeg,
                ffprobe_binary=args.ffprobe,
                colmap_binary=args.colmap,
                brush_binary=args.brush,
                keyframes=args.keyframes,
                holdout_fraction=args.holdout_fraction,
                max_resolution=args.max_resolution,
                training_steps=args.training_steps,
                max_splats=args.max_splats,
                seed=args.seed,
            )
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
