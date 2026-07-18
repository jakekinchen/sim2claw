# Prior Results Summary — What the Predecessor Actually Proved

One-page honest record of the sim-link/SceneSmith project and its first
sim2claw fork, written fresh for this clean-room repo. Every claim below was
backed in the predecessor by signed, replayable artifacts; none of it
transfers authority here. The success oracle throughout was strict-v2: a
policy only wins if it simultaneously satisfies every predicate — correct
antipodal pad contact without any assistance, the declared phase sequence, a
25 mm lift held stably for the required duration, and an honest release — as
judged by a frozen evaluator that training code never touches.

## Capability ladder outcome

- **Gate A (train/inference parity): verified.** Round-trip tests pinned down
  dataset statistics, normalization, chunk interpretation, joint order,
  gripper representation, and postprocessing, so later failures could not
  hide in preprocessing drift.
- **Gate B (one-batch memorization): passed once, by T20.35x.** That single
  pass proved the data → processor → training → checkpoint → reload → decode
  path can optimize to a target (worst joint error ~0.045 rad under the
  uniform gate). Under the later frozen consequence amendment (`463477dc...`)
  it held on only 3 of 5 seeds, missing solely on grasp-phase gripper cells
  by at most ~4.4 millirad. Gate B's diagnostic job was declared complete;
  the ladder then stopped re-proving it.
- **R2 ACT (T20.43c-R2): clean terminal negative, one predicate short.** The
  full 10,000-update ACT campaign on R0 (7 checkpoints, 14 dual-cadence
  rollouts) learned strict grasp, unassisted lift of 37.7–45.7 mm,
  unsupported stable hold, and lower at every late chunk-50 checkpoint — and
  failed Gate C only on final release contact clearance. Receding-10 was
  qualitatively worse (grasp lost, 0.5 mm lift), fixing chunk-50 as the
  working execution semantics.
- **F0c (fork): first Gate C pass, in 500 updates.** After F0/F0a/F0b
  localized the release failure (release timing ~17–20 frames late, hidden
  velocity aliasing between lift and lower, cadence alone falsified), the
  fork ran one preregistered continuation from the immutable R2 update-10000
  checkpoint with release-oversampled, physical-L1-weighted training. It
  reproduced the update-0 comparator, trained 500 local-MPS updates in ~400
  seconds, passed strict-v2 at the first scheduled evaluation, and stopped.
  Accepted checkpoint tree `8ecf7bb9...`; final receipt `9e957708...`. This
  is a nominal-task simulation result only — robustness, promotion, serving,
  and any physical claim remained open at handoff.

Supporting boundaries: the R0 dataset (129 episodes / 31,366 frames / 59,904
windows, all strict-v2 successes from a geometry-derived scripted expert; 11
held-out cases frozen with zero training rows) was verified twice — once
natively and once regenerated with no mismatches from a 66 MB portable
capsule (W1/W2 receipts). SmolVLA is a clean 5,000-update negative (best
partial 18.06 mm
lift). A localhost policy-server → MuJoCo transport replay passed (W5);
clean-clone portability stood honestly at 1 of 3 machines (W3). An RGB camera
readiness check ended in a terminal infrastructure failure, and no physical
motion, hardware, or promotion claim was ever made.

## F1 economics: pi0.5 fine-tuning is cheap

One ABEJA-parity full fine-tune of `pi05_base` on R0 ran on a Brev A100-80GB:
5,000 steps in about 3.3 hours for **$5.53** at the displayed rate, with
on-instance dual-cadence rollouts at five checkpoints. Result: terminal
negative (best partial: step-1,000 chunk-50, 37.52 mm lift, failing only
strict grasp hold; quality peaked near step 1,000 before overfitting). The
teardown was receipted — deletion confirmed and an authenticated inventory
showing zero remaining resources. Lesson: a full VLA fine-tune costs less
than lunch, so external compute is an iteration lane, not a reserved shot —
provided every run carries a spend ledger and a receipted teardown.

## Three scar-tissue lessons

1. **Infrastructure killed more experiments than science did.** Three one-use
   training slots died to evidence-path plumbing — a renderer child venv
   missing MuJoCo, a renderer entrypoint, a mirror that rejected the new
   trace schema — plus two fork F0c attempts lost to checkpoint-config
   typing before any tensor was read. Zero of these were model results.
   Countermeasures: one pinned interpreter for everything, and a rehearsal
   run before consuming any one-use marker that exercises every artifact
   schema and entrypoint the real run will emit — not a nearby older
   artifact. Infrastructure failures earn a replacement slot by default
   rather than being misfiled as scientific negatives.
2. **Source objective does not predict forward accuracy.** The T20.36o bridge
   passed every training-objective gate while failing all 25 forward
   chunk-start probes. Loss went down while behavior went nowhere,
   repeatedly. Judge candidates by closed-loop rollouts against the frozen
   evaluator; never select by loss, and never let an open-loop gate block a
   rollout.
3. **Smooth-but-timid mode averaging.** The smoothest, best-tracking SmolVLA
   checkpoint grasped the least, and contact behavior was non-monotonic
   across checkpoints (present at update 1,000, gone by 2,500). Evaluate
   several checkpoints, select on rollout consequence metrics, and when a
   policy plateaus smooth, reweight the decisive phase (via the margin
   receipts) rather than adding steps.

## Doctrine

The project's compute-and-model doctrine, in its canonical six-clause form:
agents for improvement, MPS for fast hypotheses, NVIDIA for foundation
models, corrections from the expert, state for reliable transfer, pixels for
generalization. Beneath it sit three non-negotiables that survived every
simplification: held-out scenes and seeds get frozen before any optimizer
touches data; no claim exists without a signed artifact someone else can
replay; and the evaluator belongs to a different owner than the trainer.
