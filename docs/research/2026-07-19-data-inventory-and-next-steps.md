# Data Inventory Deep Analysis and Next-Step Plan

Status: cross-cutting analysis of tracked evidence; grants no new authority

Date: 2026-07-19 America/Chicago

## Purpose

This document consolidates every data source the project has produced or
pushed so far — simulation datasets, physical recordings, visual
reconstructions, Brev/GPU campaign evidence, and GitHub Release assets — into
one inventory with counts and proof classes, analyzes what that corpus does and
does not establish, and proposes a prioritized next-step plan. It introduces no
new evidence and changes no frozen contract. Every count below is sourced from
an existing tracked receipt, run log, or decision document.

## 1. Complete data inventory

### 1.1 Simulation datasets

| Dataset | Counts | Geometry | Authority |
| --- | --- | --- | --- |
| Rook/king nominal expert demos | 24 train + 4 sealed held-out episodes, 8,712 frames (GR00T LeRobot v2.1 export) | historical 72 mm scene | scripted-expert simulation evidence only |
| Rook/king recovery/distractor demos | 48 evaluator-passing episodes, 18,888 frames | historical 72 mm scene | scripted-expert simulation evidence only |
| Current 100 mm pawn source | 1 admitted C8→A6 episode, 562 frames (strict v3 evaluator pass) | current 100 mm | the only admitted current-geometry behavior episode |
| Current 100 mm failed probes | 4 complete counterexamples | current 100 mm | failure classification only; zero training rows |
| Multisource GR00T training mixture | 73 unique sources, 96 weighted episodes, 41,088 synchronized frames, 39,648 H16 starts | mixed | consumed by the terminal-negative 1,000-step run |
| ACT rook-lift training set | 8 synthetic seeds + 1 held-out seed | historical | supports the single frozen rook-lift pass |
| B--G product simulation sources | 0 admitted source groups, 0 training rows | current 100 mm | the central data deficit |

The only retained learned weights in project storage are the 957,350-parameter
rook-lift ACT checkpoint (94.88 mm held-out lift). No B--G-compatible
checkpoint exists.

### 1.2 Physical recordings

| Item | Count | Authority |
| --- | ---: | --- |
| Current teleoperated recording directories | 18 | physical read-only source |
| Hash-verified catalog assets | 54/54 | integrity only |
| Command/measured sample rows | 7,741 | not replay-admitted |
| Rows outside current MuJoCo limits | 2,231 command / 2,255 measured | blocks exact replay |
| Replay-eligible episodes | 0/18 | provisional joint transform |
| Review panels / owner-reviewed markers | 36 / 26 | qualitative image-space only |
| Admitted metric pawn base-center poses | 0 | no endpoint authority |
| Product-scope recordings by folder label | 13, covering 12/12 directed skills | candidate routing only |
| Folder/receipt label conflicts | 11 preserved (7 product-scope, owner-corrected append-only) | blocks task-conditioned use |
| Older 72 mm cohort | 5 episodes, 2,186 samples | historical; excluded |

All 18 recordings are leader/follower human teleoperation
(`human_teleoperator` action owner). They are source trajectories, not policy
executions, and none is admitted as training, replay, or metric-endpoint
evidence.

### 1.3 Visual and pushed release data

Two private GitHub Releases exist on `jakekinchen/sim2claw` (verified against
the live repository):

| Release tag | Contents | Proof class |
| --- | --- | --- |
| `physical-replay-evidence-20260719` | Three-camera replay videos (C922 overhead, Logitech side, D405 wrist) of one replayed episode; 243 samples, 233 exact-command, 51 safety-clamped; label conflict `F2→f1` vs `e2→e1` preserved | guarded physical replay diagnostic |
| `iphone-video-3dgs-img5349-20260719` | 334,537-splat Gaussian PLY from `IMG_5349.MOV`, 78.95 MB, SHA-256 bound | monocular relative-scale 3DGS; non-metric |

Tracked hash indexes for both live under `docs/reference/`. No other data has
been pushed; generated datasets, checkpoints, and recordings remain local and
ignored per the containment policy.

### 1.4 Brev / paid-compute campaign evidence

All Brev extraction that is still possible has already happened: **no paid
worker exists** (final authenticated `brev ls --json` returned
`{"workspaces": null}` after the multisource teardown), so there is nothing
left on Brev to pull. What was extracted before teardown is:

| Campaign | Result | Retained evidence |
| --- | --- | --- |
| 2026-07-18 overnight N1.7 chess | Blocked at optimizer step 0 by gated `nvidia/Cosmos-Reason2-2B` (HF 401/403); ~$0.40 spent | spend ledger, defect fixes (PATH/uv, LFS wheel), access-gate preflight script |
| Earlier recovery / reward-guided / placement / flow-consensus campaigns | terminal-negative learned-policy receipts | run logs |
| 2026-07-19 multisource v2 (1,000 steps, A100-80GB, ≤$4.968) | Training completed, loss 0.544; sole C8→A6 dev rollout terminal negative: 0 mm lift, 125.724 mm final XY error, 13/15 gates | compact evidence tarball `groot-n17-multisource-20260719-evidence.tgz`, 367,711 bytes, SHA-256 `0cc871b1...`; four checkpoint manifests; dataset/receipt/loader hashes |

Permanent gaps from that closeout: the ~12.6 GB checkpoint weights were
intentionally not retained, the serving process had no cryptographic
checkpoint handshake, and applied-action/contact/object traces were not in the
compact archive. The result is attributable to the served process only and can
never be upgraded retroactively.

The compact evidence archive currently exists only in owner-local ignored
storage. Unlike the two published releases, it has no GitHub Release backing
its hash-bound index.

Separate lane: NemoClaw workspace `nemoclaw-e3fca7` (`b7kee8ww2`) is STOPPED,
healthy, and owner-reserved for a 20-hour deployment window. It is not a GR00T
worker and its lifecycle belongs exclusively to its originating thread.

### 1.5 Simulator fidelity progression

The B--G event-fit ledger shows train-side spatial RMS improving
309.55 mm → 118.42 mm (committed) → 17.41 mm (working receipts), with the
frozen lift-dominant candidate reaching 23.55 mm and 2/2 contact on held-out —
but 0 lift and 0 full success. Fidelity is converging kinematically; contact
and manipulation consequences are not yet reproduced.

## 2. What the corpus actually establishes

1. **Every learned-policy result is terminal negative except one narrow
   proof.** The rook-lift ACT pass is the only accepted learned result, on a
   frozen non-product task, predating the current mass profile. Four-plus GR00T
   campaigns and the SmolVLA/pi0.5 predecessors all closed negative.
2. **The binding constraint is admitted data, not compute or model class.**
   The product surface (12 directed B--G skills) has zero admitted simulation
   source groups, zero training rows, zero metric endpoint poses, and 0/18
   replay-ready physical episodes. An A100 fine-tune costs under $6 and ~6
   minutes of training; a launch without data answers no product question.
3. **One unique current-geometry source cannot train a policy.** The
   multisource run's mixture was 32.8% one pawn episode repeated 24×. The
   terminal negative is consistent with (and uninformative beyond) that
   deficit.
4. **Optimization loss is demonstrated three times to not predict task
   success** (ACT recipe comparison, GR00T loss-down/evaluator-negative runs,
   predecessor T20.36o). Checkpoint selection must remain rollout-consequence
   based.
5. **Infrastructure and identity gaps, not science, consumed most paid
   attempts** — the gated-model 401, PATH/LFS defects, and the missing runtime
   handshake that weakened the completed run's attribution. The prospective
   attestation gates now in the repository address this for future runs only.
6. **The physical corpus is rich but unadmitted.** 18 recordings covering all
   12 skills by folder label are blocked from every quantitative use by three
   specific gates: no metric pose review, no approved joint transform with
   in-range values, and 11 preserved label conflicts. Repeated nominal-center
   starts additionally cannot identify the endpoint transition matrix even if
   admitted; deliberately varied initial offsets are required.
7. **The learning-factory control plane exists; its scientific spine is the
   open build.** Post-audit buildout closed cards P0--P8 with real component
   chaining and a clean-clone acceptance, and the live physical campaign
   truthfully stops at LF-05 on the same external evidence prerequisites
   listed above.

## 3. Prioritized next steps

Ordered by information gained per unit cost, with owner-gated items separated
from work any contributor can do now.

### Lane A — unblock the physical corpus (owner-dependent, zero GPU cost)

1. Independent metric review of pawn base/contact centers plus a
   held-out-validated pixel-to-board calibration: ≥8 spatially distributed
   correspondences, board-quadrant coverage, ≤1.5 mm held-out RMS, propagated
   uncertainty, dual annotation with append-only adjudication.
2. Append-only reconciliation of the 11 folder/receipt conflicts for replay
   and training use (the 7 qualitative corrections do not transfer).
3. Review and approve the physical-to-simulator joint transform, then resolve
   the out-of-range rows (max exceedance ≈0.12 simulator units) as either
   transform error or genuine limit mismatch. Target: first N>0 of 18
   replay-eligible episodes, enabling exact recorded-action replay and staged
   system identification.

### Lane B — build the B--G simulation data engine (no owner gate, no GPU)

4. Generalize the admitted C8→A6 source expert to the 12 directed B--G
   skills on current geometry with deliberately varied initial pawn offsets,
   target offsets, distractors, and approaches — not repeated nominal
   trajectories. First target: ≥1 admitted source group per directed skill.
5. Execute the governing ACT M7 pipeline: contact-segment extraction,
   object/target-relative retargeting, connecting-motion planning, IK, full
   MuJoCo replay, strict-evaluator admission. Target: 10--20 diverse source
   episodes expanded to 500--2,000 accepted episodes for one grasp family,
   held-out pose cells at zero rows.
6. Continue the simulator fidelity lane toward contact/lift reproduction and
   commit the working-receipt progression rows with frozen identities.

### Lane C — new physical collection protocol (when hardware access returns)

7. Per directed skill: ≥10 independent episodes across ≥3 sessions with
   deliberately spread initial offsets (span ≥4× pose uncertainty), plus
   synchronized end-effector/pawn/contact/grasp/release observables. This is
   the corpus the composability study identifies as the highest-value next
   evidence; the 20-episode claim floor stays disabled pending the coverage
   study.

### Lane D — compute readiness (cheap now, spend later)

8. Resolve `nvidia/Cosmos-Reason2-2B` gated access for the `jakekinchen`
   Hugging Face account now — it is free, currently returns 403, and
   `check_groot_n17_hf_access.sh` fail-closes provisioning until fixed.
9. Hold the no-launch posture of the B--G training gate: a new Brev campaign
   requires the full ten-item paid-run checklist (hash-bound B--G dataset with
   all 12 skills, frozen semantics/held-outs, runtime handshake, evaluator,
   caps, stop rule). Lanes A/B feed exactly those items.
10. Leave the NemoClaw workspace lifecycle to its owning thread.

### Lane E — evidence hygiene (immediate, low effort)

11. Publish the multisource-v2 compact evidence archive
    (`0cc871b1...`, 367 KB) as a private GitHub Release with a tracked hash
    index, matching the pattern of the two existing releases, so the only
    surviving Brev campaign evidence is not solely on one local machine.
12. Close the pending owner decision on repository publication recorded in the
    orchestration ledger (local commits vs push vs PR).

## 4. Sequencing logic

Lane E and step 8 are immediate and independent. Lane B is the critical path
to any future training: it requires no owner review and directly produces the
paid-run gate's missing dataset items. Lane A gates all physical claims
(replay, calibration, endpoint transitions) and only the owner can perform its
reviews. Lane C waits on hardware access and on Lane A's calibration so new
recordings arrive with admissible poses. Paid training (Lane D) comes last, by
design: the next Brev dollar should be spent only when its result can answer a
B--G product question attributable to an exact dataset, checkpoint, runtime,
and evaluator.

## Claim boundary

This analysis aggregates existing receipts and does not admit any episode,
pose, checkpoint, or calibration. Simulation, replay, learned-policy, physical
read-only, and physical task evidence remain separate proof classes, and
nothing here promotes a policy or grants physical authority.
