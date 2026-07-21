#!/usr/bin/env python3
"""H2 sweep: does training loss predict closed-loop behavior? (paper §7)

§7 currently rests on three committed recipes (an anecdote). This sweep
upgrades it to a statistic: N independent ACT trainings that differ ONLY in
torch training seed and optimizer-update budget, each evaluated closed-loop on
the frozen held-out scene with BOTH the outcome-only v1 gate set and the
honest v2 collateral instrumentation. Per-run rows stream to
h2_sweep_results.jsonl; h2_sweep_summary.json reports the loss/behavior
correlation (Spearman), pass rates by loss half, and the inversion check.

Methodology notes (deliberate, mirrors the frozen stack without touching it):
  * The training loop replicates src/sim2claw/act_train.py exactly (same
    normalization, windowing, state noise, dropout, AdamW, grad clip), but is
    parameterized by (training_seed, optimizer_updates) instead of the frozen
    contract values. The frozen module stays untouched.
  * Expert data is regenerated from the frozen contract's training split.
    Dataset admission is RECORDED per episode, not enforced: on this machine
    some scripted experts drop the hold (platform contact chaos, cf. the
    replay-stability probe), and silently dropping them would change the
    dataset per machine. The dataset composition is reported in the output.
  * Closed-loop evaluation replicates act_evaluator.py's rollout (chunked
    open-loop inference, cpu/float32, torch seed = held-out seed) with
    manipulation_v2-style full-scene instrumentation in the same rollout.

Usage (repo root; mujoco 3.10 + numpy 2.2 + torch cpu):
  PYTHONPATH=src python scripts/h2_sweep.py \
      --training-seeds 7 55 99 1234 20260717 20260721 31415 2718 \
      --update-budgets 2400 8000 --output-dir .
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import mujoco
import numpy as np
import torch

from sim2claw.act_model import ACTModelConfig, ACTPolicy
from sim2claw.act_train import _normalization, _windows
from sim2claw.chess_task import (
    ChessRookLiftEnv,
    collect_expert_episode,
    load_task_contract,
    task_contract_sha256,
)
from sim2claw.manipulation_v2 import (
    _arm_body_ids,
    _piece_bodies,
    _target_speed_mps,
    _target_tilt_deg,
)

V2_GATES = {
    "max_nontarget_displacement_m": 0.006,
    "ejection_displacement_m": 0.05,
    "min_target_clearance_m": 0.04,
    "max_target_tilt_deg": 15.0,
    "max_settle_speed_mps": 0.05,
}


def _longest_true_run(values: list[bool]) -> int:
    best = run = 0
    for v in values:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def build_dataset(task: dict) -> tuple[list, list[dict]]:
    episodes, report = [], []
    for seed, offset in zip(task["training_split"]["seeds"],
                            task["training_split"]["piece_planar_offsets_m"], strict=True):
        ep = collect_expert_episode(task, seed=int(seed),
                                    piece_offset_xy_m=(float(offset[0]), float(offset[1])))
        final_rise = ep.final_piece_height_m - ep.initial_piece_height_m
        admitted = (ep.maximum_piece_rise_m >= task["evaluator"]["minimum_piece_rise_m"]
                    and final_rise >= task["evaluator"]["minimum_final_piece_rise_m"])
        report.append({"seed": int(seed), "offset": list(map(float, offset)),
                       "maximum_piece_rise_m": round(ep.maximum_piece_rise_m, 5),
                       "final_piece_rise_m": round(final_rise, 5),
                       "v1_admission_on_this_machine": admitted})
        episodes.append(ep)
    return episodes, report


def train_one(task: dict, episodes: list, *, training_seed: int, updates: int) -> tuple[ACTPolicy, dict, dict]:
    act = task["act"]
    torch.manual_seed(training_seed)
    np.random.seed(training_seed)
    device = torch.device("cpu")

    observation_mean, observation_std, action_mean, action_std = _normalization(episodes)
    observations, action_chunks, padding_masks = _windows(
        episodes, chunk_size=int(act["chunk_size"]),
        observation_mean=observation_mean, observation_std=observation_std,
        action_mean=action_mean, action_std=action_std)

    model = ACTPolicy(ACTModelConfig.from_task(task)).to(device=device, dtype=torch.float32)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(act["learning_rate"]),
                                  weight_decay=float(act["weight_decay"]))
    action_weights = torch.ones(action_chunks.shape[-1], device=device)
    action_weights[-1] = float(act["gripper_l1_weight"])
    batch_size = int(act["batch_size"])
    progress_features = int(task["observation"]["unperturbed_progress_feature_dimension"])
    losses: list[float] = []
    model.train()
    for _update in range(1, updates + 1):
        indices = torch.randint(0, observations.shape[0], (batch_size,), device=device)
        observation_batch = observations[indices].clone()
        action_batch = action_chunks[indices]
        mask_batch = padding_masks[indices]
        state_features = observation_batch[:, :-progress_features]
        state_features.add_(torch.randn_like(state_features) * float(act["normalized_state_noise_std"]))
        drop_state = torch.rand(batch_size, device=device) < float(act["state_feature_dropout_probability"])
        state_features[drop_state] = 0.0
        predicted, mean, log_variance = model(observation_batch, action_batch, mask_batch)
        valid = (~mask_batch).unsqueeze(-1)
        weighted_error = torch.abs(predicted - action_batch) * action_weights
        l1 = (weighted_error * valid).sum() / (valid.sum() * action_weights.sum())
        kl = -0.5 * torch.mean(1.0 + log_variance - mean.square() - log_variance.exp())
        loss = l1 + float(act["kl_weight"]) * kl
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
        optimizer.step()
        losses.append(float(loss.detach()))

    statistics = {"observation_mean": observation_mean, "observation_std": observation_std,
                  "action_mean": action_mean, "action_std": action_std}
    loss_report = {"final_loss": losses[-1],
                   "last100_mean_loss": float(np.mean(losses[-100:])),
                   "min_loss": float(np.min(losses))}
    return model, statistics, loss_report


@torch.no_grad()
def evaluate_closed_loop(task: dict, model: ACTPolicy, statistics: dict) -> dict:
    """v1-style chunked rollout on the held-out scene + v2-style instrumentation."""
    evaluator = task["evaluator"]
    torch.set_num_threads(1)
    torch.manual_seed(int(task["held_out_split"]["seeds"][0]))
    model.eval()

    seed = int(task["held_out_split"]["seeds"][0])
    raw_offset = task["held_out_split"]["piece_planar_offsets_m"][0]
    env = ChessRookLiftEnv(task, seed=seed,
                           piece_offset_xy_m=(float(raw_offset[0]), float(raw_offset[1])))
    model_, data = env.model, env.data
    pieces = _piece_bodies(model_)
    target_body = env.piece_body
    nontarget = {n: b for n, b in pieces.items() if b != target_body}
    nontarget_ids = set(nontarget.values())
    arm_bodies = _arm_body_ids(model_, env.arm)
    fixed_pad_body = int(model_.geom_bodyid[
        mujoco.mj_name2id(model_, mujoco.mjtObj.mjOBJ_GEOM, f"{env.arm}_fixed_jaw_box1")])
    moving_pad_body = mujoco.mj_name2id(
        model_, mujoco.mjtObj.mjOBJ_BODY, f"{env.arm}_moving_jaw_so101_v1")

    initial = {n: data.xpos[b].copy() for n, b in pieces.items()}
    initial_height = float(data.xpos[target_body][2])
    max_disp = {n: 0.0 for n in nontarget}
    contacts: list[bool] = []
    heights: list[float] = []
    nontarget_arm_contact = False
    bilateral_grasp = False

    chunk_size = int(task["act"]["chunk_size"])
    n_action_steps = int(task["act"]["n_action_steps"])
    queue: list[np.ndarray] = []
    for control_step in range(env.horizon):
        if not queue:
            observation = torch.from_numpy(env.observation(control_step)).unsqueeze(0)
            normalized = (observation - statistics["observation_mean"]) / statistics["observation_std"]
            predicted = (model.predict_action_chunk(normalized).squeeze(0)
                         * statistics["action_std"] + statistics["action_mean"]).cpu().numpy()
            if predicted.shape != (chunk_size, int(task["action"]["dimension"])):
                raise ValueError("invalid action chunk")
            if not np.isfinite(predicted).all():
                raise ValueError("non-finite actions")
            executed = min(n_action_steps, env.horizon - control_step)
            queue.extend(row.copy() for row in predicted[:executed])
        env.step(np.asarray(queue.pop(0), dtype=np.float64))
        contacts.append(env.jaw_piece_contact())
        heights.append(float(data.xpos[target_body][2]))
        touch_fixed = touch_moving = False
        for c in range(data.ncon):
            contact = data.contact[c]
            bodies = {int(model_.geom_bodyid[contact.geom1]), int(model_.geom_bodyid[contact.geom2])}
            if bodies & arm_bodies and bodies & nontarget_ids:
                nontarget_arm_contact = True
            if target_body in bodies:
                touch_fixed |= fixed_pad_body in bodies
                touch_moving |= moving_pad_body in bodies
        bilateral_grasp |= touch_fixed and touch_moving
        for n, b in nontarget.items():
            disp = float(np.linalg.norm(data.xpos[b] - initial[n]))
            if disp > max_disp[n]:
                max_disp[n] = disp

    heights_arr = np.asarray(heights)
    max_rise = float(heights_arr.max() - initial_height)
    final_rise = float(heights_arr[-1] - initial_height)
    window = int(evaluator["final_contact_window_control_steps"])
    final_contact_fraction = float(np.mean(contacts[-window:]))
    v1_gates = {
        "piece_rise": max_rise >= float(evaluator["minimum_piece_rise_m"]),
        "final_piece_rise": final_rise >= float(evaluator["minimum_final_piece_rise_m"]),
        "consecutive_contact": _longest_true_run(contacts)
            >= int(evaluator["minimum_consecutive_contact_control_steps"]),
        "final_contact_fraction": final_contact_fraction
            >= float(evaluator["minimum_final_contact_fraction"]),
    }
    worst = max(max_disp, key=max_disp.get)
    ejected = sorted(n for n, d in max_disp.items() if d > V2_GATES["ejection_displacement_m"])
    tilt = _target_tilt_deg(model_, data, target_body)
    speed = _target_speed_mps(model_, data, target_body)
    v2_gates = {
        "max_nontarget_displacement": max_disp[worst] <= V2_GATES["max_nontarget_displacement_m"],
        "nontarget_ejections": len(ejected) == 0,
        "no_nontarget_arm_contact": not nontarget_arm_contact,
        "target_clearance": max_rise >= V2_GATES["min_target_clearance_m"],
        "target_upright": tilt <= V2_GATES["max_target_tilt_deg"],
        "target_settled": speed <= V2_GATES["max_settle_speed_mps"],
        "bilateral_pad_grasp": bilateral_grasp,
    }
    success_v1 = all(v1_gates.values())
    return {
        "held_out_seed": seed,
        "maximum_piece_rise_m": round(max_rise, 5),
        "final_piece_rise_m": round(final_rise, 5),
        "longest_contact_run": _longest_true_run(contacts),
        "final_contact_fraction": round(final_contact_fraction, 4),
        "worst_nontarget_piece": worst,
        "worst_nontarget_displacement_m": round(max_disp[worst], 5),
        "nontarget_pieces_over_6mm": {n: round(d, 5) for n, d in
                                      sorted(max_disp.items(), key=lambda kv: -kv[1])
                                      if d > V2_GATES["max_nontarget_displacement_m"]},
        "nontarget_ejections": ejected,
        "target_final_tilt_deg": round(tilt, 2),
        "target_final_speed_mps": round(speed, 4),
        "v1_gates": v1_gates,
        "v2_gates": v2_gates,
        "success_v1": success_v1,
        "success_v2": success_v1 and all(v2_gates.values()),
    }


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    def rank(v):
        order = np.argsort(v)
        ranks = np.empty(len(v))
        sv = np.asarray(v)[order]
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and sv[j + 1] == sv[i]:
                j += 1
            ranks[order[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return ranks
    rx, ry = rank(x), rank(y)
    rx -= rx.mean(); ry -= ry.mean()
    denom = float(np.sqrt((rx ** 2).sum() * (ry ** 2).sum()))
    return None if denom == 0 else float((rx * ry).sum() / denom)


def summarize(rows: list[dict]) -> dict:
    losses = [r["training"]["final_loss"] for r in rows]
    v1 = [r["evaluation"]["success_v1"] for r in rows]
    rises = [r["evaluation"]["maximum_piece_rise_m"] for r in rows]
    collateral = [r["evaluation"]["worst_nontarget_displacement_m"] for r in rows]
    order = np.argsort(losses)
    half = len(rows) // 2
    low_half = set(order[:half].tolist())
    out = {
        "n_runs": len(rows),
        "v1_pass_rate": round(sum(v1) / len(v1), 4),
        "v2_pass_rate": round(sum(r["evaluation"]["success_v2"] for r in rows) / len(rows), 4),
        "spearman_final_loss_vs_max_rise": spearman(losses, rises),
        "spearman_final_loss_vs_v1_success": spearman(losses, [float(s) for s in v1]),
        "spearman_final_loss_vs_worst_collateral": spearman(losses, collateral),
        "v1_pass_rate_lower_loss_half": round(
            sum(v1[i] for i in low_half) / max(1, half), 4),
        "v1_pass_rate_upper_loss_half": round(
            sum(v1[i] for i in range(len(rows)) if i not in low_half) / max(1, len(rows) - half), 4),
        "lowest_loss_run": {
            "training_seed": rows[int(order[0])]["training_seed"],
            "optimizer_updates": rows[int(order[0])]["optimizer_updates"],
            "final_loss": losses[int(order[0])],
            "success_v1": v1[int(order[0])]},
        "collateral_mm": {
            "median": round(float(np.median(collateral)) * 1000, 2),
            "min": round(float(np.min(collateral)) * 1000, 2),
            "max": round(float(np.max(collateral)) * 1000, 2)},
        "runs_with_v1_pass_and_any_v2_collateral_gate_fail": sum(
            1 for r in rows if r["evaluation"]["success_v1"] and not (
                r["evaluation"]["v2_gates"]["max_nontarget_displacement"]
                and r["evaluation"]["v2_gates"]["nontarget_ejections"]
                and r["evaluation"]["v2_gates"]["no_nontarget_arm_contact"])),
    }
    by_budget: dict[int, list[dict]] = {}
    for r in rows:
        by_budget.setdefault(r["optimizer_updates"], []).append(r)
    out["by_update_budget"] = {
        str(k): {
            "n": len(v),
            "v1_pass_rate": round(sum(r["evaluation"]["success_v1"] for r in v) / len(v), 4),
            "mean_final_loss": round(float(np.mean([r["training"]["final_loss"] for r in v])), 6),
            "median_worst_collateral_mm": round(float(np.median(
                [r["evaluation"]["worst_nontarget_displacement_m"] for r in v])) * 1000, 2),
        } for k, v in sorted(by_budget.items())}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--training-seeds", type=int, nargs="+",
                    default=[7, 55, 99, 1234, 20260717, 20260721, 31415, 2718])
    ap.add_argument("--update-budgets", type=int, nargs="+", default=[2400, 8000])
    ap.add_argument("--output-dir", type=Path, default=Path("."))
    args = ap.parse_args()

    task = load_task_contract()
    print("regenerating expert dataset from frozen training split ...")
    episodes, dataset_report = build_dataset(task)
    print(json.dumps(dataset_report, indent=1))

    meta = {
        "schema_version": "sim2claw.h2_sweep_row.v1",
        "task_contract_sha256": task_contract_sha256(),
        "dataset_report": dataset_report,
        "mujoco_version": mujoco.__version__,
        "numpy_version": np.__version__,
        "torch_version": torch.__version__,
        "platform": platform.platform(),
        "physical_authority": False,
    }
    results_path = args.output_dir / "h2_sweep_results.jsonl"
    rows = []
    with results_path.open("w") as f:
        for updates in args.update_budgets:
            for tseed in args.training_seeds:
                t0 = time.monotonic()
                model, statistics, loss_report = train_one(
                    task, episodes, training_seed=tseed, updates=updates)
                train_s = time.monotonic() - t0
                t0 = time.monotonic()
                evaluation = evaluate_closed_loop(task, model, statistics)
                row = {**meta, "training_seed": tseed, "optimizer_updates": updates,
                       "training": loss_report, "evaluation": evaluation,
                       "train_seconds": round(train_s, 1),
                       "eval_seconds": round(time.monotonic() - t0, 1)}
                rows.append(row)
                f.write(json.dumps(row, sort_keys=True) + "\n")
                f.flush()
                print(f"seed {tseed} upd {updates}: loss {loss_report['final_loss']:.5f} "
                      f"v1={evaluation['success_v1']} rise {evaluation['maximum_piece_rise_m']*1000:.1f}mm "
                      f"collateral {evaluation['worst_nontarget_displacement_m']*1000:.1f}mm "
                      f"({train_s:.0f}s train)")

    summary = {"schema_version": "sim2claw.h2_sweep_summary.v1", **meta,
               "training_seeds": args.training_seeds,
               "update_budgets": args.update_budgets,
               "summary": summarize(rows)}
    digest = hashlib.sha256(results_path.read_bytes()).hexdigest()
    summary["results_jsonl_sha256"] = digest
    summary_path = args.output_dir / "h2_sweep_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {results_path} ({digest[:16]}...) and {summary_path}")
    print(json.dumps(summary["summary"], indent=2))


if __name__ == "__main__":
    main()
