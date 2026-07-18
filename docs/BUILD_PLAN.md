# Manual Build Plan

The build proceeds from requirements to fresh implementation. No phase imports
implementation from `sim2claw-imported-archive`.

## Current implementation state — 2026-07-17

The owner-directed Polycam chess-table request advanced the repository through
the runtime foundation and the photo-aligned portion of Phase 2:

- Phase 1 runtime bootstrap, lock, Mac doctor, and NVIDIA/EGL fail-closed
  contract are implemented.
- A fresh table-and-chess MuJoCo scene with two articulated SO-101 arms
  compiles, settles, and renders on Mac.
- The correction photo's major workcell elements are represented, with every
  non-RoomPlan transform labeled as a visual estimate.
- Phase 3 evaluator behavior, seeds, and held-out scenes remain unimplemented.

## Phase 0 — Documentation boundary

Preserve the available documents with exact byte identities, mark them as
inert reference history, and define fresh active rules and goals. This phase is
complete when the new repository contains documentation only.

## Phase 1 — Runtime foundation

Select Python, MuJoCo, LeRobot, PyTorch, and supporting upstream pins. Document
Mac and NVIDIA host requirements. Implement a new bootstrap that creates one
runtime and a doctor that reports exact dependency and accelerator state.

Gate: a clean clone can create the runtime, and unsupported hosts fail closed.

## Phase 2 — Simulator foundation

Create a minimal SO-101 workcell from reviewed upstream robot geometry and a
new repo-native scene definition. Keep rollout and rendering in process. Add a
small simulator command that compiles, steps, and renders without camera,
network, optimizer, or hardware access.

Gate: fresh Mac proof plus a contract-tested NVIDIA/EGL preflight.

## Phase 3 — Task and evaluator contracts

Define the first task through registry data, freeze training and held-out
seeds, and implement a separately invoked CPU/fp32 evaluator. Do this before
training code exists.

Gate: disjoint seeds, deterministic verdict fixtures, and cross-host-identical
evaluator output.

## Phase 4 — Data and learning lanes

Add short state episodes and one state-RL baseline. Add ACT only after the
dataset and evaluator contracts are stable. Introduce PI0.5 on NVIDIA as a
separate bounded experiment; do not let VLA work block the first end-to-end
simulator path.

Gate: immutable run receipts, separately owned evaluation decisions, and
replayable counterexamples.

## Phase 5 — Gateway

Design one versioned observation/action/acknowledgement protocol. Prove it
locally between a real policy-server process and a MuJoCo client before any
remote bind or robot adapter exists.

Gate: exact transport replay with no policy-quality or hardware overclaim.

## Phase 6 — Physical prerequisites

Only after simulation selection and gateway proof: calibration, estimator
inputs, shadow mode, explicit owner authority, and a bounded canary. No
reference document can skip this phase.

## Implemented slices

1. Runtime foundation: dependency decision record, project manifest, lock,
   clean bootstrap, fail-closed host doctor, and tests.
2. Scene foundation: verified Polycam acquisition/conversion, measured table,
   estimated/configurable chessboard, 32 dynamic pieces, compile/step/render
   command, and scan-reference overlay.
3. Photo-aligned robot slice: pinned public SO-101 model, two independently
   controlled instances, edge mounts, fiducial/background props, portrait
   camera, and compile/step/render contract tests.

## Next reviewed slice

Freeze the first chess-manipulation task, held-out scenes and seeds, then add a
separately owned CPU/fp32 evaluator before any training code.
