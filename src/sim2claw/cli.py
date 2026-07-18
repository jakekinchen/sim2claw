from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .alignment import compare_alignment
from .capture import fetch_capture
from .doctor import doctor_json, format_doctor, run_doctor
from .paths import DEFAULT_OUTPUT_ROOT, STUDIO_ASSET_ROOT
from .render import render_scene
from .scene import scene_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sim2claw")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="fail-closed runtime preflight")
    doctor.add_argument("--target", choices=("auto", "mac", "nvidia"), default="auto")
    doctor.add_argument("--render-probe", action="store_true")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    subparsers.add_parser(
        "fetch-polycam", help="fetch and verify the owner-provided capture reference"
    )

    render = subparsers.add_parser("render", help="compile, settle, and render the scene")
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

    studio = subparsers.add_parser(
        "studio",
        help="open the browser evidence studio and loopback-only ACT source recorder",
    )
    studio.add_argument("--host", default="127.0.0.1")
    studio.add_argument("--port", type=int, default=4173)
    studio.add_argument("--no-open", action="store_true")

    subparsers.add_parser(
        "teleop-preflight",
        help="inspect SO-101 buses, calibrations, and recorder mode gates",
    )
    subparsers.add_parser(
        "physical-gateway-preflight",
        help="open both identified buses torque-off and verify physical gateway state",
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
    if args.command == "studio":
        from .studio_server import serve_studio

        serve_studio(
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
        )
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
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
