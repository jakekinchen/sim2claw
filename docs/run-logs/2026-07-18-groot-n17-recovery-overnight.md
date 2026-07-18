# GR00T N1.7 Recovery and Robustness Overnight Campaign

Date: 2026-07-18 America/Chicago

## Lane identity

- Branch: `codex/gr00t-n17-recovery-overnight`.
- Isolated worktree: `/Users/kelly/Developer/sim2claw-recovery`.
- Starting `origin/main`: `42e0704bbfe8a29e8d629b441e7cccf980e983de`.
- Machine 1 boundary: the existing `chess_pick_place_groot_v1` contract,
  dataset, baseline run, and checkpoints remain owned by the nominal lane.
- Machine 2 worker: `sim2claw-gr00t-recovery-0718` (`u9709tq27`).
- Worker type: `massedcompute_A100_sxm4_80G_DGX` at the previously quoted
  `$1.656/hour`.

## Frozen identities

- v1 contract SHA-256:
  `473915817b3a8474f796df53e199df92031d17fad152599a1d43ccecd3f15683`.
- v2 recovery contract SHA-256:
  `2a258c068098c175eb5ea63beaaff8730b32a3217c65f60d7d6b99f78db39c6a`.
- NVIDIA source: `23ace64f17aa5015259b8609d371eb61a357c776`.
- Base model: `nvidia/GR00T-N1.7-3B`, revision
  `2fc962b973bccdd5d8ce4f67cc63b264d6886495`.
- Proof class: simulation synthetic demonstrations and learned-policy
  evaluation only; no physical authority.

## Worker preflight

The dedicated second worker passed setup with:

- NVIDIA A100-SXM4-80GB, 81,920 MiB, compute capability 8.0;
- driver 580.126.09, CUDA 12.8, and Torch 2.7.1+cu128;
- GR00T import from the exact pinned source revision; and
- FFmpeg 4.4.2.

Local access probes returned HTTP 200 for the account, GR00T base model, and
Cosmos dependency before provisioning. The existing local Hugging Face token
was transferred to the worker through a protected file and never printed or
placed in Git.

## Recovery contract result

The v2 matrix contains 48 training rows and 24 held-out rows. Both splits cover
nominal, pose-error, distractor-proximity, and contact-recovery families; the
held-out rows have disjoint seeds and perturbation signatures and explicitly
contribute zero training rows.

The contact curriculum uses one declared 3--4.5 mm pre-lift displacement while
the jaws are open. The expert then clears, recomputes the target geometry,
reacquires, closes, and must produce post-fault target contact. Nearby pieces
are placed tangent to the transport path with an inward-board component so the
test measures manipulation clearance rather than an invalid reset on the board
frame.

A complete CPU/fp32 no-render sweep accepted all 48 training consequences and
all 24 held-out consequences. Every accepted row had zero assistance. Failed
candidate geometries encountered while designing the frozen matrix were kept
out of imitation data.

The new unit tests include deterministic negative fixtures for spills,
wrong-piece jaw contact, failed capture, dragging, and late toppling. The
focused recovery suite passed four tests, including both pieces and every
failure family.

## Dataset and training ledger

This section is updated only at stable evidence boundaries.

| Stage | State | Evidence |
| --- | --- | --- |
| Training demonstration sweep | PASS | 48/48 frozen consequences accepted |
| Held-out expert feasibility | PASS | 24/24 frozen consequences accepted; zero training rows |
| LeRobot v2 training export | PASS | 48 episodes, 18,888 frames, 102 files; receipt SHA-256 `fba7697d1f4f95aad46998dd3ab2db79cbde629b91c8e5a228f59d4e214a967d` |
| Official NVIDIA loader | PASS | 48 episodes; episode 0 has 363 rows and the expected language, state, action, and `video.front` columns |
| Held-out diagnostic export | PASS | 24 zero-training-row episodes, 9,444 frames, 54 files; receipt SHA-256 `f849460fe89bee251355ea105a4e1553076da70e5105fb51186a8ba641cd816b` |
| Held-out NVIDIA loader | PASS | 24 episodes; 363-row non-contact and 485-row recovery trajectories; expected modalities |
| Clean-base candidate A | RUNNING | PID 16012; checkpoint-4000 complete and training resumed; finite loss history and no exit marker |
| Recovery policy runner | PREFLIGHT PASS | compiled locally/remotely and imported in the pinned GR00T environment; fixed action horizon 16 |
| Evaluator checkpoint sweep | NOT RUN | checkpoints 1000--4000 available; waits for training exit and checkpoint-5000 |
| Paid worker teardown | NOT DUE | worker remains bounded to the active verified run |

Candidate A started at approximately 04:10 America/Chicago from the pinned
clean base and exact validated dataset. It saves every 1,000 steps, retains at
most five checkpoints, and is guarded by a 21,600-second hard timeout. The
initial live check observed 77 percent GPU utilization at 44 C. The run remains
diagnostic until a separately owned evaluator accepts a saved checkpoint.

Checkpoint boundary metrics remained finite through step 4,000: loss was
0.8382 at step 1,000, 0.7580 at step 2,000, 0.6113 at step 3,000, and 0.5534 at
step 4,000. These values establish optimizer health only and have no promotion
authority.

The learned-policy recovery runner uses the frozen 16-action horizon. In
contact-recovery cases, the declared fault occurs after the frozen stand-off
and advance durations at physics step 800, which is both a sample boundary and
a new action-chunk query boundary. Fault injection remains separate from robot
assistance, and every robot action after the fault remains model-owned.

An attempted dataset replay on the Brev/Linux MuJoCo stack failed episode 0
while lowering to the piece, despite the same consequence passing the frozen
CPU/fp32 evaluator used to establish dataset authority. That attempt is
quarantined at
`/home/shadeform/sim2claw/datasets/chess_pick_place_groot_recovery_v2.failed-linux-physics`
and is not training data or positive evidence. The earlier missing-model attempt
is likewise quarantined under the `.failed-missing-model` suffix.

## Authority boundary

The expert feasibility sweep and dataset acceptance do not establish learned
policy performance. Training loss and open-loop action error remain diagnostic.
Only separately invoked closed-loop consequence receipts may select a
checkpoint. Generated datasets, weights, videos, logs, caches, and credentials
remain outside Git.
