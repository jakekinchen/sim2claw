# C8 to A6 action-frozen robust-margin candidate

## Outcome

A new simulation-only geometric C8-to-A6 packet passes the unchanged,
separately owned CPU/fp32 evaluator and is materially more robust than the
previous nominal packet.

The selected profile changes geometry generation, then freezes the resulting
actions:

- pawn neck target: `0.0385 m`;
- grasp offset: `[-0.004, -0.0015, 0.0] m`;
- closed jaw target: `-0.17453 rad`;
- lift clearance: `0.09 m`;
- release clearance: `0.003 m`;
- partial-release target before extraction: `0.8 rad`.

The profile is frozen in
`configs/tasks/c8_a6_robust_margin_profile_v1.json`. It grants no physical
authority.

## Exact packet identity

Canonical ignored episode:

`runs/geometric-pawn-sequence/20260726-c8-a6-robust-margin-v1`

- action shape: `562 x 6`;
- encoding: little-endian float32, C order;
- raw action SHA-256:
  `9ed420b12c66ddbc2440f213033310366f307ec97a51114c14bd35b1f1d7e78c`;
- recording receipt SHA-256:
  `d35a5b6d0af6b58afc15cf6b4a7fefc794163ef5f7a2b5b2198652ecb05212c3`;
- samples SHA-256:
  `bf67b9519618b391ee40d7c895969b81eff9f130ffe72d6eb6d93ecaf95e8858`;
- admission verdict SHA-256:
  `195fd3a4b59b2217f11d10f5d0b4cfe25e368e5185b5fde264a1f8af4d02db20`;
- evaluator canonical payload SHA-256:
  `8d3f2ccf4d29d69a3449d9ba97aea808ff930da4abf81acb0264e5524e025e94`;
- profile file SHA-256:
  `5f6b48bd53674fa04493d3a353750cf9247d094e93b9f0efcb0084a615f9db01`.

No action was assisted, adapted, or clipped.

## Nominal evaluator result

Every unchanged evaluator gate passed, including exact final privileged-state
replay:

- maximum rise: `0.1019225319 m`;
- final XY error: `0.0052517413 m` (limit `0.015 m`);
- final height error: `0.0010107905 m` (limit `0.005 m`);
- final upright cosine: `0.9999999980` (minimum `0.95`);
- final speed: `0.0001146729 m/s` (limit `0.02 m/s`);
- gripper clearance: `0.1155390769 m` (minimum `0.035 m`);
- maximum other-pawn displacement: `8.21731e-8 m`;
- wrong-pawn contact: false;
- final jaw/pawn contact: false;
- assistance frames: `0`;
- exact sample-hold replay: true.

## Preregistered robustness box

The practical required box was fixed before candidate selection:

- board x: `+-0.5 mm`;
- board y: `+-0.5 mm`;
- board yaw: `+-0.1 deg`;
- each of the six joint-zero coordinates: `+-0.1 deg`.

Board z `+-0.5 mm` was also tested as a stricter diagnostic, although it was
not part of the required box.

Every robustness replay consumed the same action SHA above. A perturbation was
applied only through the joint-coordinate or workcell model. The frozen
consequence gates were reused without changing thresholds. Perturbed runs
cannot satisfy nominal privileged-state equality and therefore remain
diagnostic-only; they grant no source admission.

Results:

| Split | Box | Result | Wrong-pawn contact |
| --- | --- | ---: | ---: |
| Search seed `20260726` | required plus board z | `66/66` combined; `20/20` signed axes | `0` |
| Validation seed `20260729` | required plus board z | `255/258` combined; `20/20` signed axes | `0` |
| Final held-out seed `20260730` | required plus board z | `507/514` combined; `20/20` signed axes | `0` |
| Final held-out seed `20260731` | required box | `1022/1026` combined; `18/18` signed axes | `0` |
| Materialized canonical packet | required box | `2/2` all-sign corners; `18/18` signed axes | `0` |

The final required-box map is:

`runs/geometric-pawn-sequence/20260726-margin-release-rel3-open80-v1/required_box_heldout_20260731.json`

Its SHA-256 is
`d746109b04a4b2ed95834b15e2660893133a8de00388347079256d9d407dd7d3`.
All four failures missed final XY; two also toppled. All four lifted the target
and none contacted a wrong pawn or another unexpected robot body.

## Transfer conclusion

This candidate establishes a nonzero, practically sized one-axis and
all-sign-corner robustness result. It is a major improvement over the prior
packet, whose identity-connected tolerance collapsed near micrometre-scale
registration errors.

It does **not** establish a completely robust continuous multidimensional box:
four of 1,026 final held-out required-box samples failed. Therefore it is a
plausible transfer candidate, not a physically transfer-ready or parity-complete
candidate. Physical hardware was untouched, and no physical command is
authorized by this result.

## Reproduction

```bash
uv run sim2claw source-expert \
  --output runs/geometric-pawn-sequence/20260726-c8-a6-robust-margin-v1 \
  --render-size 64 \
  --expert-profile configs/tasks/c8_a6_robust_margin_profile_v1.json

uv run sim2claw source-eval \
  --episode runs/geometric-pawn-sequence/20260726-c8-a6-robust-margin-v1
```

Focused repository verification:

```text
10 passed, 2 subtests passed
```

This is simulation geometric-command evidence only. It is not learned-policy,
physical task, calibration-approval, or digital-twin parity evidence.
