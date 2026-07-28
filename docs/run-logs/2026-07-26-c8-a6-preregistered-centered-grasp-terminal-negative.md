# C8 to A6 preregistered centered-grasp terminal negative

## Outcome

The one-delta simulation experiment stopped terminal-negative at its focused
eight-case gate. The candidate fixed all eight task consequences and both
previously observed contact-failure mechanisms, but it did not satisfy the
preregistered zero-clipping requirement. The already-frozen full required-box
set was therefore not replayed.

This result is simulation diagnostic evidence only. It grants no physical
authority, and no hardware was moved.

## Preregistered change

The prior robust-margin profile was changed in exactly one field:

- prior grasp offset: `[-0.004, -0.0015, 0.0] m`;
- candidate grasp offset: `[-0.004, -0.002, 0.0015] m`;
- delta: `[0.0, -0.0005, 0.0015] m`.

Every other profile value, phase duration, evaluator threshold, and
perturbation vector remained unchanged. The profile is
`configs/tasks/c8_a6_preregistered_centered_grasp_v1.json`, with SHA-256
`4b01e6307fd4a7d49eefb97a466a734cabdae77c48688d3919a9876774194b78`.

## Frozen packet

Ignored episode:

`runs/geometric-pawn-sequence/20260726-c8-a6-centered-grasp-preregistered-v1`

- action shape: `562 x 6`;
- raw little-endian float32 action SHA-256:
  `5b8fc0383ede57e6591f2bc044ad5b5a520c442e9d82ac8994832115f9592e2b`;
- recording receipt SHA-256:
  `52959393afe1cdb7889468444642177a7279a412fac58345f30808d1d0483547`;
- samples SHA-256:
  `c5ed4297f5f8c18c9b31243ea7cd237fd0abb0560b949f9df4d85de0ac2ce80f`;
- admission verdict SHA-256:
  `8854c2b960f1082b83e85168cf3abb969c6c3cabf3ba5033da167fb142102e2f`;
- evaluator canonical payload SHA-256:
  `43c09f3b00ebafa2fa935f81740bdedb3f8a4069dd21d6ad0e3714922d4be987`.

The unchanged CPU/fp32 evaluator passed nominally with exact sample-hold replay:

- final XY error: `5.6582973 mm`;
- maximum rise: `103.3583659 mm`;
- final height error: `1.0107452 mm`;
- final upright cosine: `0.9999999998`;
- final speed: `0.0001635384 m/s`;
- maximum other-pawn displacement: `8.21731e-8 m`;
- wrong-pawn contact: false;
- assistance frames: `0`.

## Focused eight-case gate

The perturbations were read without resampling from
`required_box_heldout_20260731.json`, SHA-256
`d746109b04a4b2ed95834b15e2660893133a8de00388347079256d9d407dd7d3`.
The four prior failures and their four named nearest passing controls were
replayed with the new action SHA.

Focused diagnostic:

`runs/geometric-pawn-sequence/20260726-c8-a6-centered-grasp-preregistered-v1/focused_eight_replay.json`

Its SHA-256 is
`ecc375e6ddf4d95d43387a37fb2b74907772b934e2a4988ccee28f626bc06404`.

| Case | Role | Strict consequence | Final XY | Bilateral through sample 411 | Sample-121 fixed:moving force | Jaw contact after sample 420 | Clipped targets |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `combined_012` | prior failure | pass | `6.157 mm` | yes | `0.964` | `0` | `317` |
| `combined_247` | control | pass | `6.205 mm` | yes | `0.962` | `0` | `0` |
| `combined_384` | prior failure | pass | `5.588 mm` | yes | `0.965` | `0` | `0` |
| `combined_924` | control | pass | `7.119 mm` | yes | `0.961` | `0` | `0` |
| `combined_541` | prior failure | pass | `4.938 mm` | yes | `1.081` | `1` | `317` |
| `combined_722` | control | pass | `5.912 mm` | yes | `0.959` | `0` | `317` |
| `combined_607` | prior failure | pass | `5.339 mm` | yes | `0.911` | `0` | `0` |
| `combined_481` | control | pass | `5.549 mm` | yes | `0.937` | `1` | `0` |

The case-specific preregistered gates passed:

- `combined_384` and `combined_541` retained bilateral jaw contact through
  lower and their sample-121 force ratios were within `[0.8, 1.25]`;
- `combined_012` and `combined_607` finished within `15 mm` and had no jaw
  contact after sample `420`;
- all eight passed every unchanged consequence gate;
- no case contacted a wrong pawn or an unexpected robot body;
- no assistance was applied.

The overall focused gate failed because zero clipping was false. The negative
gripper-zero residuals in `combined_012`, `combined_541`, and `combined_722`
were added to the candidate's already lower-bound closed-jaw target of
`-0.17453 rad`. The actuator-coordinate mapping therefore saturated that
coordinate on `317` action samples in each case. The source action array stayed
byte-identical within every replay, but the perturbation mapping required
actuator-bound clipping.

## Stop condition

The preregistration required all focused checks to pass before opening the full
frozen required-box replay. Zero clipping failed, so:

- no full required-box replay was run;
- no second generator adjustment was tried;
- no threshold or evaluator was changed;
- no new perturbations were sampled;
- no hardware action was performed.

The centered grasp is a strong functionally resolving diagnostic, not an
accepted robustness successor. A future experiment must be separately
preregistered; this result cannot promote itself.

## Nominal reproduction

```bash
uv run sim2claw source-expert \
  --output runs/geometric-pawn-sequence/20260726-c8-a6-centered-grasp-preregistered-v1 \
  --render-size 64 \
  --expert-profile configs/tasks/c8_a6_preregistered_centered_grasp_v1.json

uv run sim2claw source-eval \
  --episode runs/geometric-pawn-sequence/20260726-c8-a6-centered-grasp-preregistered-v1
```
