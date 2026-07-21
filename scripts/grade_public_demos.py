#!/usr/bin/env python3
"""Grade public manipulation demonstrations with scene-integrity gates.

Prevalence study for the Honest Evaluation paper (§6.3 at field scale):
what fraction of public demonstration episodes move non-target objects past
physically grounded bounds?

Architecture:
  * CORE (pure NumPy): given per-timestep world positions of every scene body
    and the target body's name, compute per-episode collateral metrics and the
    two headline gates:
        max_nontarget_displacement <= disp_gate   (default 6 mm, sim2claw v2)
        nontarget_ejections == 0    at eject_gate (default 50 mm)
    Thresholds are CLI-tunable because chess-scale bounds are not canonical
    for other scenes (paper §10); we report a sweep, not one number.
  * ADAPTER robomimic: rebuilds each episode's MuJoCo env from the HDF5's
    stored model XML, steps through the flat `states` array, and records every
    body's world position. Requires robosuite + robomimic (your machine/Brev,
    not needed for --selftest).
  * DOWNLOAD: fetches robomimic low_dim datasets from the Hugging Face mirror
    via huggingface_hub (public, no token).

Usage on your machine:
  pip install "robosuite<1.5" robomimic huggingface_hub h5py mujoco numpy
  python grade_public_demos.py --download lift can square
  python grade_public_demos.py --grade datasets/lift_ph_low_dim.hdf5 --target-hint cube
  python grade_public_demos.py --selftest        # no robosuite needed

Output: grade_results_<name>.json  (per-episode metrics + threshold sweep).
Send those JSONs back for analysis and paper tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------- CORE ----

DEFAULT_DISP_GATES_M = [0.002, 0.006, 0.010, 0.025, 0.050]  # sweep, 6 mm = paper gate
DEFAULT_EJECT_GATE_M = 0.05


def grade_episode(
    body_positions: dict[str, np.ndarray],  # name -> (T, 3) world positions
    target_bodies: set[str],
    ignore_bodies: set[str] | None = None,
    disp_gates_m: list[float] = DEFAULT_DISP_GATES_M,
    eject_gate_m: float = DEFAULT_EJECT_GATE_M,
    baseline_frame: int = 0,
) -> dict:
    """Pure-numpy collateral grading of one episode.

    baseline_frame: displacement is measured against this frame, and only
    frames >= it are graded. Public datasets whose first state is not settled
    (objects still dropping into place) pollute a mm-scale gate; grading from
    a few frames in ("settled baseline") removes that bias.
    """
    ignore = ignore_bodies or set()
    nontarget = {
        n: p for n, p in body_positions.items()
        if n not in target_bodies and n not in ignore
    }
    if not nontarget:
        # single-object scenes (e.g. robomimic lift) have no bystanders: the
        # collateral gates are vacuous, not violated. Flag it so the summary
        # can report coverage honestly instead of crashing mid-dataset.
        return {
            "n_nontarget_bodies": 0,
            "vacuous": True,
            "worst_nontarget_body": None,
            "worst_nontarget_displacement_m": None,
            "per_body_max_displacement_m": {},
            "ejected_bodies_at_%.0fmm" % (eject_gate_m * 1000): [],
            "gates": {
                "disp_gate_%.0fmm_pass" % (g * 1000): True for g in disp_gates_m
            } | {"ejection_gate_pass": True},
        }
    max_disp = {}
    for name, pos in nontarget.items():
        pos = np.asarray(pos, dtype=np.float64)[baseline_frame:]
        if len(pos) == 0:
            raise ValueError(f"baseline_frame {baseline_frame} beyond episode length")
        max_disp[name] = float(np.linalg.norm(pos - pos[0], axis=1).max())
    worst = max(max_disp, key=max_disp.get)
    ejected = sorted(n for n, d in max_disp.items() if d > eject_gate_m)
    return {
        "n_nontarget_bodies": len(nontarget),
        "worst_nontarget_body": worst,
        "worst_nontarget_displacement_m": round(max_disp[worst], 6),
        "per_body_max_displacement_m": {n: round(d, 6) for n, d in sorted(max_disp.items(), key=lambda kv: -kv[1])},
        "ejected_bodies_at_%.0fmm" % (eject_gate_m * 1000): ejected,
        "gates": {
            "disp_gate_%.0fmm_pass" % (g * 1000): max_disp[worst] <= g for g in disp_gates_m
        } | {"ejection_gate_pass": len(ejected) == 0},
    }


def summarize(episodes: list[dict], disp_gates_m: list[float]) -> dict:
    n_total = len(episodes)
    vacuous = [e for e in episodes if e.get("vacuous")]
    episodes = [e for e in episodes if not e.get("vacuous")]
    n = len(episodes)
    out = {"n_episodes": n_total, "n_vacuous_episodes": len(vacuous)}
    if n == 0:
        out["note"] = "all episodes vacuous (no non-target bodies in scene)"
        return out
    for g in disp_gates_m:
        key = "disp_gate_%.0fmm_pass" % (g * 1000)
        out["violation_rate_at_%.0fmm" % (g * 1000)] = round(
            sum(1 for e in episodes if not e["gates"][key]) / n, 4
        )
    out["ejection_rate"] = round(
        sum(1 for e in episodes if not e["gates"]["ejection_gate_pass"]) / n, 4
    )
    disps = [e["worst_nontarget_displacement_m"] for e in episodes]
    out["worst_displacement_m"] = {
        "median": round(float(np.median(disps)), 6),
        "p90": round(float(np.percentile(disps, 90)), 6),
        "max": round(float(np.max(disps)), 6),
    }
    return out


# ------------------------------------------------- robomimic ADAPTER -------

# robomimic v0.3 low_dim HDF5 layout:
#   data/demo_i/states  (T, D) flat mujoco states
#   data.attrs["env_args"] json  |  data/demo_i.attrs["model_file"] xml
def iter_robomimic_episodes(hdf5_path: Path, target_hint: str):
    import h5py
    import robosuite  # noqa: F401  (env rebuild)
    import robomimic.utils.obs_utils as ObsUtils
    from robomimic.utils.env_utils import create_env_from_metadata
    from robomimic.utils.file_utils import get_env_metadata_from_dataset

    # robomimic requires a global obs-modality registry before any env.reset();
    # we never consume observations (we read sim state directly), so a minimal
    # low_dim spec is enough to keep EnvRobosuite.get_observation() happy.
    ObsUtils.initialize_obs_utils_with_obs_specs(
        obs_modality_specs={"obs": {"low_dim": ["robot0_eef_pos"], "rgb": []}}
    )

    env_meta = get_env_metadata_from_dataset(dataset_path=str(hdf5_path))
    env = create_env_from_metadata(env_meta=env_meta, render=False, render_offscreen=False)
    sim = env.env.sim  # underlying mujoco sim
    with h5py.File(hdf5_path, "r") as f:
        demos = sorted(f["data"].keys(), key=lambda s: int(s.split("_")[1]))
        for demo in demos:
            states = f[f"data/{demo}/states"][()]
            model_xml = f[f"data/{demo}"].attrs.get("model_file", None)
            if model_xml is not None:
                env.reset()
                env.reset_to({"model": model_xml, "states": states[0]})
                sim = env.env.sim
            body_names = [sim.model.body_id2name(i) for i in range(sim.model.nbody)]
            positions = {n: [] for n in body_names if n and n != "world"}
            for s in states:
                sim.set_state_from_flattened(s)
                sim.forward()
                for n in positions:
                    positions[n].append(sim.data.get_body_xpos(n).copy())
            positions = {n: np.asarray(v) for n, v in positions.items()}
            targets = {n for n in positions if target_hint.lower() in n.lower()}
            # robot/table/fixed frames move with the arm or never move: keep the
            # arm OUT of collateral (arm motion is not damage; contact gates
            # need a contact-level adapter, phase 2)
            ignore = {n for n in positions if any(
                k in n.lower() for k in ("robot", "gripper", "table", "mount", "base", "controller", "peg")
            )}
            yield demo, positions, targets, ignore


def grade_robomimic(hdf5_path: Path, target_hint: str, disp_gates, eject_gate, limit=None,
                    baseline_frame: int = 0) -> dict:
    episodes = []
    for demo, positions, targets, ignore in iter_robomimic_episodes(hdf5_path, target_hint):
        if not targets:
            raise ValueError(f"--target-hint '{target_hint}' matched no bodies; bodies: {sorted(positions)[:20]}")
        row = grade_episode(positions, targets, ignore, disp_gates, eject_gate,
                            baseline_frame=baseline_frame)
        row["episode"] = demo
        episodes.append(row)
        if row.get("vacuous"):
            print(f"{demo}: vacuous (no non-target bodies)")
        else:
            print(f"{demo}: worst={row['worst_nontarget_displacement_m']*1000:.2f}mm "
                  f"({row['worst_nontarget_body']}) 6mm_pass={row['gates']['disp_gate_6mm_pass']}")
        if limit and len(episodes) >= limit:
            break
    return {
        "dataset": str(hdf5_path),
        "target_hint": target_hint,
        "baseline_frame": baseline_frame,
        "summary": summarize(episodes, disp_gates),
        "episodes": episodes,
    }


# ------------------------------------------------------------ DOWNLOAD -----

ROBOMIMIC_HF = {  # public mirrors of robomimic proficient-human low_dim data
    "lift": ("amandlek/robomimic", "v0.1/lift/ph/low_dim_v141.hdf5"),
    "can": ("amandlek/robomimic", "v0.1/can/ph/low_dim_v141.hdf5"),
    "square": ("amandlek/robomimic", "v0.1/square/ph/low_dim_v141.hdf5"),
    "tool_hang": ("amandlek/robomimic", "v0.1/tool_hang/ph/low_dim_v141.hdf5"),
}


def download(names: list[str], dest: Path) -> None:
    from huggingface_hub import hf_hub_download

    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        repo, path = ROBOMIMIC_HF[name]
        print(f"downloading {name} from {repo}:{path} ...")
        try:
            local = hf_hub_download(repo_id=repo, filename=path, repo_type="dataset",
                                    local_dir=dest)
            print(f"  -> {local}")
        except Exception as exc:  # mirror paths drift; fall back to robomimic's own downloader
            print(f"  HF mirror failed ({exc}).")
            print(f"  Fallback: python -m robomimic.scripts.download_datasets "
                  f"--tasks {name} --dataset_types ph --hdf5_types low_dim "
                  f"--download_dir {dest}")


# ------------------------------------------------------------- SELFTEST ----

def selftest() -> None:
    """Validate the core with a real MuJoCo scene: a scripted pusher shoves the
    target and clips a bystander; a second run doesn't. No robosuite needed."""
    import mujoco

    xml = """
    <mujoco>
      <option timestep="0.002"/>
      <worldbody>
        <geom name="floor" type="plane" size="2 2 .1"/>
        <body name="target_cube" pos="0 0 .03">
          <freejoint/><geom type="box" size=".025 .025 .025" mass="0.1"/>
        </body>
        <body name="bystander_a" pos="0.08 0 .03">
          <freejoint/><geom type="box" size=".025 .025 .025" mass="0.1"/>
        </body>
        <body name="bystander_b" pos="0.5 0.5 .03">
          <freejoint/><geom type="box" size=".025 .025 .025" mass="0.1"/>
        </body>
        <body name="pusher" pos="-0.2 0 .03" mocap="true">
          <geom type="sphere" size=".03" density="0"/>
        </body>
      </worldbody>
    </mujoco>"""
    model = mujoco.MjModel.from_xml_string(xml)

    def run(pusher_dy: float) -> dict[str, np.ndarray]:
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        names = ["target_cube", "bystander_a", "bystander_b"]
        ids = {n: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, n) for n in names}
        # settle free bodies BEFORE baselining displacement — spawn poses drift
        # a few mm under gravity, which would pollute a 6 mm gate. (Same rule
        # applies to any dataset whose first state is not a settled state.)
        data.mocap_pos[0] = [-0.2, pusher_dy, 0.03]
        for _ in range(300):
            mujoco.mj_step(model, data)
        pos = {n: [] for n in names}
        for t in range(600):
            data.mocap_pos[0] = [-0.2 + 0.0008 * t, pusher_dy, 0.03]
            mujoco.mj_step(model, data)
            for n in names:
                pos[n].append(data.xpos[ids[n]].copy())
        return {n: np.asarray(v) for n, v in pos.items()}

    # Run 1: pusher drives straight through target INTO bystander_a's lane
    dirty = grade_episode(run(pusher_dy=0.0), {"target_cube"})
    # Run 2: pusher offset in y — moves target's lane only obliquely
    clean = grade_episode(run(pusher_dy=0.3), {"target_cube"})

    print("dirty run:", json.dumps(dirty["gates"], indent=2))
    print("  worst:", dirty["worst_nontarget_body"], dirty["worst_nontarget_displacement_m"], "m")
    print("clean run:", json.dumps(clean["gates"], indent=2))
    assert not dirty["gates"]["disp_gate_6mm_pass"], "dirty run should violate the 6 mm gate"
    assert dirty["worst_nontarget_body"] == "bystander_a"
    assert clean["gates"]["disp_gate_6mm_pass"], "clean run should pass the 6 mm gate"
    assert clean["gates"]["ejection_gate_pass"]
    print("\nSELFTEST PASSED: core gate math validated against live MuJoCo physics.")


# ---------------------------------------------------------------- CLI ------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", nargs="+", choices=sorted(ROBOMIMIC_HF), help="fetch datasets")
    ap.add_argument("--dest", type=Path, default=Path("datasets"))
    ap.add_argument("--grade", type=Path, help="robomimic low_dim HDF5 to grade")
    ap.add_argument("--target-hint", default="cube", help="substring identifying target body/bodies")
    ap.add_argument("--disp-gates-mm", type=float, nargs="+", default=[g * 1000 for g in DEFAULT_DISP_GATES_M])
    ap.add_argument("--eject-gate-mm", type=float, default=DEFAULT_EJECT_GATE_M * 1000)
    ap.add_argument("--limit", type=int, help="grade only first N episodes (smoke run)")
    ap.add_argument("--baseline-frame", type=int, default=10,
                    help="measure displacement from this frame on (settled baseline); "
                         "0 = raw first state")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.download:
        download(args.download, args.dest)
    if args.grade:
        gates = [g / 1000 for g in args.disp_gates_mm]
        result = grade_robomimic(args.grade, args.target_hint, gates, args.eject_gate_mm / 1000, args.limit,
                                 baseline_frame=args.baseline_frame)
        out = Path(f"grade_results_{args.grade.stem}.json")
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"\nSummary → {out}")
        print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
