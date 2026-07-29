# Fable RP01 Preview Review

Status: `CONTINUE_RP02_FREEZE`

Date: `2026-07-29`

Reviewer: Claude Fable 5, effort `High`, existing project thread

Reviewed branch and commit:
`codex/bidirectional-transfer-goal-loop-20260728` at `dee24a0`

Review mode: read-only repository inspection. Fable changed no files and
opened no camera, gateway, serial, hardware, or paid-compute authority.

## Verdict

Fable independently verified:

- RP01 contract SHA-256
  `ec878defa98e1c46ac6e3184c6fda1553d4bb0a7ae60dc2fc1cfd327fad9d5e4`;
- immutable preview receipt SHA-256
  `e9e99a4ad774a04e5dc031a9b6060df6e32f7ceceb6e56fa40cfba61f481fc1f`;
- fresh preflight binding SHA-256
  `ed5d32b88483b14ffb98271662f9b587c8e10b9607df12b98d525a558a7f56de`;
- freeze commit `dee24a0` remote-equal before the receipt;
- all 117 full-interval poses, calibrated ranges, and zero-contact result;
- the no-op current-anchor setup as the safest valid high-clearance posture;
- the moving-chain distance scope, while fixed links remain in the all-robot
  zero-contact gate; and
- the MuJoCo box-box witness fallback. Raw and witness distances agree at all
  three reported binding minima, so the fallback did not inflate a margin.

Fable also checked the uncorrected canonical scene and found zero contacts
across the interval. Its minimum true clearance there was about `74 mm`.
This is not part of the frozen `120 mm` registered-scene gate, but shows that
the motion remains contact-free if the registration candidate is wrong.

The missing timestamp on the bound preflight is not material because the
freeze commit bounds it and RP02 must take a fresh host-monotonic-timestamped
preflight and rebase before execution.

## RP02 additions

The smallest physical packet must add:

1. a hash-pinned, tested read-conditioned executor for the exact ladder,
   telemetry, hold, cleanup, and `60 s` persistence probe;
2. execution-time fresh preflight with a host-monotonic timestamp, all-joint
   calibrated-range and identity checks, and live rebase;
3. safe stop for any held non-elbow joint drifting more than `2 deg`;
4. safe stop for camera loss or writer failure;
5. exact C922 and Pi identities/formats, active from before the first command
   through cleanup, with hash-bound outputs;
6. binding to the RP01 contract/receipt, executor, calibration, queue/graph,
   non-task ledger, one-execution/no-retry rule, and terminal final-angle
   semantics; and
7. another independent `CONTINUE`, followed by a time-bounded owner physical
   authorization.

Fable accepted the frozen `1 deg` all-joint rebase because RP01 has `30.8 mm`
slack above the `120 mm` gate, but recommended either stating the link-motion
argument or tightening held non-elbow joints to `0.5 deg`. RP02 adopts the
tighter `0.5 deg` held-joint gate.

## Claim boundary

`CONTINUE_RP02_FREEZE` authorizes implementation and review of a physical
packet only. It does not authorize camera access, gateway, serial, torque,
physical motion, pawn contact, a task attempt, mapping approval, policy
ranking, simulator promotion, or transfer.
