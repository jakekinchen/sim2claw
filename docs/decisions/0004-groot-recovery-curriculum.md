# Decision 0004: GR00T Recovery Curriculum and Geometric Expert

Status: accepted for the recovery challenger campaign

Date: 2026-07-18 America/Chicago

## Decision

Keep the frozen `chess_pick_place_groot_v1` task byte-for-byte unchanged and
train the second NVIDIA candidate from a separately versioned recovery task.
The v2 task contains 48 training episodes and 24 zero-training-row held-out
episodes across nominal, pose-error, distractor-proximity, and declared
contact-recovery families.

Use a deterministic geometric expert to author demonstrations. The expert
plans explicit stand-off, advance, capture, vertical lift, transport, release,
and retreat primitives. Contact-recovery rows inject one bounded 3--4.5 mm
pre-lift target displacement while the jaws are open, then require the robot
trajectory to clear, reacquire, and establish target contact after the fault.
The injection is recorded separately from robot assistance; assistance remains
zero.

Place nearby distractors tangent to the pickup-to-destination path with an
inward board component. This keeps the perturbation on the playable surface
instead of placing a piece on the board frame or directly in the transport
lane. Freeze only combinations whose scripted consequence passes the same
6 mm maximum non-target displacement gate used by v1.

When a destination lies within 140 mm of another active piece, offset the
commanded release point by 4 mm away from that piece while continuing to score
against the original square center. This uses geometric clearance without
weakening the 15 mm placement gate.

## Evaluator boundary

The separate CPU/fp32 consequence evaluator owns acceptance. In addition to
the v1 lift, placement, upright, settled, clearance, action-ownership, and
assistance gates, v2 rejects:

- first jaw contact with a non-target piece;
- any later wrong-piece jaw contact;
- more than 6 mm displacement of any non-target piece;
- an undeclared or missing fault injection; and
- a recovery rollout without target contact after its declared fault.

Training loss, dense reward, expert acceptance, and open-loop action error do
not promote a checkpoint.

## Consequences

- The recovery dataset is newly generated and does not copy machine 1 data.
- Failed scripted trajectories remain counterexamples and contribute no
  imitation rows.
- Phase labels are evaluator evidence only and are not policy inputs.
- The expert may read exact simulation state; the learned policy remains
  restricted to its declared RGB, language, and proprioceptive modalities.
- This work is simulation evidence and grants no physical authority.
