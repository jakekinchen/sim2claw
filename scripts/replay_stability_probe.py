#!/usr/bin/env python3
"""Replay-stability probe for the Honest Evaluation paper (§10 rebuttal).

§10 names "replay sensitivity" as a threat to validity: the stack documents
~1e-6 chaos sensitivity, so how do we know the honest evaluator's verdicts are
properties of the trajectory rather than replay noise? This probe separates the
two claims empirically:

  Mode A (deterministic replay): replay the SAME recorded float32 action trace
    N times, each in a freshly constructed frozen-contract env. If the graded
    metrics are bitwise identical across trials, grading a stored trace is a
    deterministic function — verdict flips can never come from the grader.

  Mode B (perturbed replay): replay the same trace with i.i.d. Gaussian noise
    (default sigma = 1e-6 rad) added to (a) only the first action chunk and
    (b) every action. The spread of outcomes measures the trajectory-
    GENERATION chaos the paper quotes, and locates it outside the grader.

Together: the honest evaluator's replay methodology (grade the stored trace,
never re-run inference) is exactly the design that makes v1-vs-v2 comparisons
trace-to-trace stable, while mode B quantifies why re-inference or context
drift cannot be compared run-to-run. Outputs are JSON, one file per mode.

Usage (from repo root, mujoco 3.10 + numpy 2.2 env):
  PYTHONPATH=src python scripts/replay_stability_probe.py \
      --trials 20 --expert-seed 1102 --output-dir .
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.chess_task import ChessRookLiftEnv, collect_expert_episode, load_task_contract, task_contract_sha256
from sim2claw.manipulation_v2 import (
    _arm_body_ids,
    _piece_bodies,
    _target_speed_mps,
    _target_tilt_deg,
    load_manipulation_contract,
    manipulation_contract_sha256,
)

V2_GATES = {
    "max_nontarget_displacement_m": 0.006,
    "ejection_displacement_m": 0.05,
    "min_target_clearance_m": 0.04,
    "max_target_tilt_deg": 15.0,
    "max_settle_speed_mps": 0.05,
}


def replay_trace(contract: dict, seed: int, offset: tuple[float, float], actions: np.ndarray) -> dict:
    """Replay one action trace with full-scene instrumentation (v2-style)."""
    env = ChessRookLiftEnv(contract, seed=seed, piece_offset_xy_m=offset)
    model, data = env.model, env.data
    pieces = _piece_bodies(model)
    target_body = env.piece_body
    nontarget = {n: b for n, b in pieces.items() if b != target_body}
    nontarget_ids = set(nontarget.values())
    arm_bodies = _arm_body_ids(model, env.arm)
    fixed_pad_body = int(model.geom_bodyid[
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{env.arm}_fixed_jaw_box1")])
    moving_pad_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, f"{env.arm}_moving_jaw_so101_v1")

    initial = {n: data.xpos[b].copy() for n, b in pieces.items()}
    initial_height = float(data.xpos[target_body][2])
    max_disp = {n: 0.0 for n in nontarget}
    max_rise = 0.0
    nontarget_arm_contact = False
    bilateral_grasp = False

    for raw in actions:
        env.step(np.asarray(raw, dtype=np.float64))
        touch_fixed = touch_moving = False
        for c in range(data.ncon):
            contact = data.contact[c]
            bodies = {int(model.geom_bodyid[contact.geom1]), int(model.geom_bodyid[contact.geom2])}
            if bodies & arm_bodies and bodies & nontarget_ids:
                nontarget_arm_contact = True
            if target_body in bodies:
                touch_fixed |= fixed_pad_body in bodies
                touch_moving |= moving_pad_body in bodies
        bilateral_grasp |= touch_fixed and touch_moving
        max_rise = max(max_rise, float(data.xpos[target_body][2]) - initial_height)
        for n, b in nontarget.items():
            disp = float(np.linalg.norm(data.xpos[b] - initial[n]))
            if disp > max_disp[n]:
                max_disp[n] = disp

    worst = max(max_disp, key=max_disp.get)
    ejected = sorted(n for n, d in max_disp.items() if d > V2_GATES["ejection_displacement_m"])
    tilt = _target_tilt_deg(model, data, target_body)
    speed = _target_speed_mps(model, data, target_body)
    final_rise = float(data.xpos[target_body][2]) - initial_height
    metrics = {
        "maximum_target_rise_m": max_rise,
        "final_target_rise_m": final_rise,
        "worst_nontarget_piece": worst,
        "worst_nontarget_displacement_m": max_disp[worst],
        "per_piece_max_displacement_m": dict(sorted(max_disp.items(), key=lambda kv: -kv[1])),
        "nontarget_ejections": ejected,
        "nontarget_arm_contact": nontarget_arm_contact,
        "bilateral_pad_grasp": bilateral_grasp,
        "target_final_tilt_deg": tilt,
        "target_final_speed_mps": speed,
        "gates": {
            "max_nontarget_displacement": max_disp[worst] <= V2_GATES["max_nontarget_displacement_m"],
            "nontarget_ejections": len(ejected) == 0,
            "no_nontarget_arm_contact": not nontarget_arm_contact,
            "target_clearance": max_rise >= V2_GATES["min_target_clearance_m"],
            "target_upright": tilt <= V2_GATES["max_target_tilt_deg"],
            "target_settled": speed <= V2_GATES["max_settle_speed_mps"],
            "bilateral_pad_grasp": bilateral_grasp,
        },
    }
    # bitwise-comparison digest over the full-precision metric vector
    digest_payload = json.dumps(
        [max_rise, final_rise, max_disp, tilt, speed, bilateral_grasp, nontarget_arm_contact],
        sort_keys=True, separators=(",", ":")).encode()
    metrics["metric_digest_sha256"] = hashlib.sha256(digest_payload).hexdigest()
    return metrics


def aggregate(trials: list[dict]) -> dict:
    digests = [t["metric_digest_sha256"] for t in trials]
    keys = ["maximum_target_rise_m", "final_target_rise_m",
            "worst_nontarget_displacement_m", "target_final_tilt_deg"]
    spread = {}
    for k in keys:
        vals = np.asarray([t[k] for t in trials], dtype=np.float64)
        spread[k] = {
            "min": float(vals.min()), "max": float(vals.max()),
            "std": float(vals.std()), "range": float(vals.max() - vals.min()),
        }
    gate_flip = {}
    for g in trials[0]["gates"]:
        outcomes = {t["gates"][g] for t in trials}
        gate_flip[g] = {"outcomes_observed": sorted(outcomes), "stable": len(outcomes) == 1}
    return {
        "n_trials": len(trials),
        "n_distinct_metric_digests": len(set(digests)),
        "bitwise_identical": len(set(digests)) == 1,
        "metric_spread": spread,
        "gate_stability": gate_flip,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--expert-seed", type=int, default=1102,
                    help="training-split seed whose scripted expert generates the trace")
    ap.add_argument("--perturbation-std-rad", type=float, default=1e-6)
    ap.add_argument("--output-dir", type=Path, default=Path("."))
    args = ap.parse_args()

    contract = load_task_contract()
    rows = dict(zip(contract["training_split"]["seeds"],
                    contract["training_split"]["piece_planar_offsets_m"]))
    if args.expert_seed not in rows:
        raise SystemExit(f"--expert-seed must be a training-split seed: {sorted(rows)}")
    offset = tuple(float(v) for v in rows[args.expert_seed])

    print(f"generating scripted-expert trace (seed {args.expert_seed}, offset {offset}) ...")
    episode = collect_expert_episode(contract, seed=args.expert_seed, piece_offset_xy_m=offset)
    actions = episode.actions  # float32, the exact executed trace
    trace_sha = hashlib.sha256(actions.tobytes()).hexdigest()
    print(f"trace: {actions.shape}, sha256 {trace_sha[:16]}..., "
          f"expert max rise {episode.maximum_piece_rise_m*1000:.1f} mm")

    meta = {
        "task_contract_sha256": task_contract_sha256(),
        "manipulation_contract_sha256": manipulation_contract_sha256(),
        "trace_source": "scripted_ik_expert",
        "expert_seed": args.expert_seed,
        "piece_offset_xy_m": list(offset),
        "action_trace_sha256": trace_sha,
        "control_horizon": int(actions.shape[0]),
        "expert_maximum_piece_rise_m": episode.maximum_piece_rise_m,
        "mujoco_version": mujoco.__version__,
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "v2_gate_thresholds": V2_GATES,
        "physical_authority": False,
    }
    load_manipulation_contract()  # fail fast if v2 contract drifted

    # ---- Mode A: exact replay, N trials ----
    print(f"mode A: {args.trials} deterministic replays ...")
    mode_a = [replay_trace(contract, args.expert_seed, offset, actions)
              for _ in range(args.trials)]
    out_a = {"schema_version": "sim2claw.replay_stability_probe.v1", "mode": "A_deterministic_replay",
             "description": "identical float32 action trace replayed in freshly built frozen-contract envs",
             **meta, "aggregate": aggregate(mode_a), "trials": mode_a}
    path_a = args.output_dir / "replay_stability_modeA.json"
    path_a.write_text(json.dumps(out_a, indent=2, sort_keys=True) + "\n")
    agg = out_a["aggregate"]
    print(f"  bitwise identical across trials: {agg['bitwise_identical']} "
          f"({agg['n_distinct_metric_digests']} distinct digests)")

    # ---- Mode B: perturbed replay, N trials per scope ----
    chunk = int(contract["act"]["chunk_size"])
    mode_b_scopes = {}
    for scope in ("first_chunk_only", "all_steps"):
        print(f"mode B [{scope}]: {args.trials} perturbed replays (sigma={args.perturbation_std_rad}) ...")
        trials = []
        for trial in range(args.trials):
            rng = np.random.default_rng(910100 + trial)
            perturbed = actions.astype(np.float64).copy()
            if scope == "first_chunk_only":
                perturbed[:chunk] += rng.normal(0.0, args.perturbation_std_rad, size=perturbed[:chunk].shape)
            else:
                perturbed += rng.normal(0.0, args.perturbation_std_rad, size=perturbed.shape)
            row = replay_trace(contract, args.expert_seed, offset, perturbed)
            row["perturbation_rng_seed"] = 910100 + trial
            trials.append(row)
        mode_b_scopes[scope] = {"aggregate": aggregate(trials), "trials": trials}
        a = mode_b_scopes[scope]["aggregate"]
        print(f"  rise range {a['metric_spread']['maximum_target_rise_m']['range']*1000:.2f} mm, "
              f"worst-collateral range {a['metric_spread']['worst_nontarget_displacement_m']['range']*1000:.2f} mm")

    out_b = {"schema_version": "sim2claw.replay_stability_probe.v1", "mode": "B_perturbed_replay",
             "description": "same trace with i.i.d. Gaussian action noise; quantifies trajectory-generation chaos",
             "perturbation_std_rad": args.perturbation_std_rad,
             **meta, "scopes": mode_b_scopes}
    path_b = args.output_dir / "replay_stability_modeB.json"
    path_b.write_text(json.dumps(out_b, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path_a} and {path_b}")


if __name__ == "__main__":
    main()
