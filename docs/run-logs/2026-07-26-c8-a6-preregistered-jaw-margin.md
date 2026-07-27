# C8 to A6 preregistered jaw-margin replay

## Outcome

The separately preregistered jaw-margin candidate passed its nominal evaluator
and complete focused eight-case gate, including zero action clipping. This
opened the already-materialized robustness maps exactly once for the new frozen
action packet.

The broader result is strong but not complete: `1,855/1,864` combined variants
passed across four existing maps, while every one of the `78` signed one-axis
endpoints passed. Nine combined variants failed. Therefore this is retained
simulation-only geometric-command evidence, not full-box parity or physical
readiness.

No hardware was addressed or moved.

## Preregistered change

Starting from commit `3c37259`, the centered-grasp profile changed exactly one
motion parameter:

- prior closed-jaw target: `-0.17453 rad`;
- candidate closed-jaw target: `-0.1727003294848389 rad`
  (`radians(-9.895 deg)`);
- centered grasp offset retained: `[-0.004, -0.002, 0.0015] m`.

Every other profile value, phase duration, evaluator threshold, and
perturbation vector remained unchanged. The nominal jaw target has about
`0.1048 deg` of lower-limit margin, leaving a small positive margin after the
frozen worst-case `-0.1 deg` gripper-zero residual.

The profile is
`configs/tasks/c8_a6_preregistered_jaw_margin_v1.json`, SHA-256
`cf09adc340a356a93bf18877ebe8402cc2a4dcfabe991138227cfb2ce7e7a37a`.

## Frozen packet and nominal evaluator

Ignored episode:

`runs/geometric-pawn-sequence/20260726-c8-a6-jaw-margin-preregistered-v1`

- action shape: `562 x 6`;
- raw little-endian float32 action SHA-256:
  `76489fef8f7af0b757db9f05cf4302ebf24bdf160b351462375be7757abaabfd`;
- recording receipt SHA-256:
  `0f25ad1d0045ea051796a6c9f567edded5cf53dc74c6c32a6258ee51a24a6493`;
- samples SHA-256:
  `708d1529f421504ab76cfa3444c124b4e27e5e2dd37595cbd252faa9a2ee40b5`;
- admission verdict SHA-256:
  `ecf55b77cf31a22d84b022830db4fbe5396a95597129389298ae997d5cc37728`;
- evaluator canonical payload SHA-256:
  `6612aa964d9bafff19b55318143e2c7a8d25affe44f3bdf7f1c3d0a8cf27cc84`.

The unchanged CPU/fp32 evaluator passed nominally with exact sample-hold replay:

- final XY error: `3.7048608 mm`;
- maximum rise: `103.1187394 mm`;
- final height error: `1.0107343 mm`;
- final upright cosine: `0.9999999991`;
- final speed: `0.0001440618 m/s`;
- maximum other-pawn displacement: `8.21731e-8 m`;
- wrong-pawn contact: false;
- assistance frames: `0`.

## Focused gate

The exact four prior failures and four named controls were read from the
existing required-box map without resampling. The focused result is:

`runs/geometric-pawn-sequence/20260726-c8-a6-jaw-margin-preregistered-v1/focused_eight_replay.json`

Its SHA-256 is
`a6be2b16772706ae6f4a869362263af11ce1130c0041e6221a57d5e4e269a6c9`.

| Case | Role | Strict consequence | Final XY | Bilateral through sample 411 | Sample-121 fixed:moving force | Jaw contacts after sample 420 | Clipped targets |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `combined_012` | prior failure | pass | `4.528 mm` | yes | `0.958` | `0` | `0` |
| `combined_247` | control | pass | `5.975 mm` | yes | `0.940` | `2` | `0` |
| `combined_384` | prior failure | pass | `6.503 mm` | yes | `0.969` | `0` | `0` |
| `combined_924` | control | pass | `6.051 mm` | yes | `0.955` | `1` | `0` |
| `combined_541` | prior failure | pass | `4.400 mm` | yes | `1.101` | `0` | `0` |
| `combined_722` | control | pass | `5.358 mm` | yes | `1.087` | `0` | `0` |
| `combined_607` | prior failure | pass | `3.630 mm` | yes | `0.873` | `0` | `0` |
| `combined_481` | control | pass | `4.674 mm` | yes | `0.994` | `0` | `0` |

Every preregistered focused check passed:

- eight of eight unchanged consequence evaluations;
- bilateral contact through lower for `combined_384` and `combined_541`;
- sample-121 fixed:moving force ratio in `[0.8, 1.25]` for those cases;
- final XY at most `15 mm` and no jaw contact after sample `420` for
  `combined_012` and `combined_607`;
- zero actuator-target clipping;
- zero assistance, wrong-pawn contact, or unexpected robot contact.

## Existing frozen-map replay

No perturbation was generated or resampled. Each output below consumes the
new action SHA and one previously materialized input map.

| Frozen input | Input SHA-256 | Combined | Signed endpoints | Output SHA-256 |
| --- | --- | ---: | ---: | --- |
| search seed `20260726` | `4f98e24087ebed5e3ddaaa5fe1e0b885368e6ffd37a2f5daa1e211fb365852ea` | `65/66` | `20/20` | `5d0279011207e595c1f50d60e32596db55daa03b452056d16c1a6c29fbf8d51d` |
| validation seed `20260729` | `c93e83b89d6482b4ddcbbf11619bbf7ae2739d322845582ce0e39dcd0b07ae06` | `257/258` | `20/20` | `5cdc7782784658b012bd1bfa2eb398d01e78b8d71bf145896513a981a9c3efbe` |
| held-out seed `20260730` | `47d63e7b9e4d3aa380905a4d22228f47aacd7e615bb87b185ae64bd89ef00071` | `511/514` | `20/20` | `c214279704cf3ba5cb0bb0cfaa2d5e57e53264a18ae9a10f546c5105dd2f213e` |
| required-only held-out seed `20260731` | `d746109b04a4b2ed95834b15e2660893133a8de00388347079256d9d407dd7d3` | `1022/1026` | `18/18` | `78113c8be8c0be4a4d4ee19641643e79c14cd9d56f81503bce14c6f8549ad881` |

The four output paths, in table order, are:

- `frozen_train_20260726_replay.json`;
- `frozen_validation_20260729_replay.json`;
- `frozen_heldout_20260730_replay.json`;
- `frozen_required_20260731_replay.json`.

They live under the ignored episode directory above. Across all four maps:

- combined variants: `1,855/1,864`;
- signed one-axis endpoints: `78/78`;
- nominal rows: `4/4`;
- action clipping: `0`;
- assistance: `0`;
- wrong-pawn contacts: `0`;
- unexpected robot contacts: `0`.

The nine failed combined IDs were:

| Map | Failed IDs | Primary failed gates |
| --- | --- | --- |
| search `20260726` | `combined_044` | final XY, height, upright |
| validation `20260729` | `combined_021` | final XY, upright, speed |
| held-out `20260730` | `combined_145`, `combined_252`, `combined_487` | final XY and upright; `252` also rise |
| required `20260731` | `combined_718`, `combined_814`, `combined_829`, `combined_960` | final XY and upright; `718/814/829` also height; `814` also collateral displacement |

The focused four prior required-box failures all passed. Four different
required-box variants failed, so the required-box pass count remained
`1022/1026`; the failure identity changed rather than the box becoming
complete.

Relative to the earlier robust-margin action, this candidate improved the
validation map from `255/258` to `257/258` and the first held-out map from
`507/514` to `511/514`, while the small search map changed from `66/66` to
`65/66`. It is therefore not universally dominant despite resolving the
targeted failures and eliminating clipping.

## Claim boundary

This result proves that the jaw-limit margin closes the focused clipping defect
without reopening the two targeted contact mechanisms. It does not prove a
fully robust continuous box, learned-policy success, physical transfer,
digital-twin parity, or physical readiness.

No threshold, evaluator, phase duration, non-jaw profile value, or source
action was changed after the packet was frozen. No additional candidate was
tried.

## Nominal reproduction

```bash
uv run sim2claw source-expert \
  --output runs/geometric-pawn-sequence/20260726-c8-a6-jaw-margin-preregistered-v1 \
  --render-size 64 \
  --expert-profile configs/tasks/c8_a6_preregistered_jaw_margin_v1.json

uv run sim2claw source-eval \
  --episode runs/geometric-pawn-sequence/20260726-c8-a6-jaw-margin-preregistered-v1
```
