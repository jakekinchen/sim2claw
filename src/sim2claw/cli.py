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

    sail_benchmark = subparsers.add_parser(
        "sail-compile-benchmark",
        help="compile the disjoint public/sealed seeded SAIL benchmark",
    )
    sail_benchmark.add_argument("--config", type=Path, required=True)
    sail_benchmark.add_argument("--output", type=Path, required=True)

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
    if args.command == "source-eval":
        from .pawn_source_evaluator import evaluate_source_episode

        output = args.output or args.episode / "admission_verdict.json"
        report = evaluate_source_episode(args.episode, output_path=output)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["strict_success"] else 1
    if args.command == "source-expert":
        from .pawn_source_expert import collect_pawn_source_expert_candidate

        report = collect_pawn_source_expert_candidate(
            args.output, render_size=args.render_size
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
