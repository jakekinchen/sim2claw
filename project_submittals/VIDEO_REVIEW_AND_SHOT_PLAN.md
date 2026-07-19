# Demo Video Review & Rubric-Mapped Shot Plan

Review of `sim2claw-full-demo.mp4` (3:21, 1080p30) against (a) the submission
checklist and Loom script in `README_submittal.md`, and (b) the official
judging criteria for the **Recursive Intelligence Track**.

## Verdict in one paragraph

The current cut has strong raw material — real robot footage, the 3DGS orbit,
the simulator-accuracy chart, clean section titles that already mirror the
rubric headings — but it is a **silent slideshow**, and the checklist requires
a **narrated Loom recording that shows the core loop live**. Worse for
scoring: the track is judged primarily on **demonstrated improvement between
first run and last run**, and that story currently occupies about eight
unexplained seconds (the accuracy chart). The final 80 seconds sit on one
static "Evidence Wall" layout. The fix is less about polish and more about
restructuring the video as a before/after arc with narration.

## The track, in rubric terms

> "An agent that measurably gets smarter the more it runs… captures what it
> learns, compounds it into a persistent knowledge base… demonstrably
> improves at its task over successive runs. Judged on the performance delta
> between first run and last run, bonus credit for a clear learning
> mechanism."

sim2claw's honest mapping to that:

- **The task:** manipulate chess pieces with a low-cost SO-101 arm via a
  simulation twin.
- **First run:** simulator event-fit error **309.6 mm**, 0/11 contact, no
  policy could lift anything.
- **Learning mechanism (the compounding knowledge base):** versioned datasets
  + JSON receipts + frozen evaluation gates + a counterexample library.
  Failed runs are never deleted or relabeled — they become targeted
  correction data. The learning factory loop (twin calibration → curriculum →
  training → counterexample mining → evaluation → promotion) compounds this
  across revisions. The dev process itself is recursive too: an audited
  executor/reviewer agent loop built the repo in reviewable slices
  (`.factory/` ledgers are the episodic memory).
- **Last run:** simulator error **17.4 mm (94.4% reduction over 8
  revisions)**; a fresh 957K-param ACT policy **passes a frozen held-out exam
  with a 94.88 mm rook lift**, graded by an evaluator the trainer cannot
  touch.
- **The differentiator vs. other teams:** the improvement is *provable*, not
  anecdotal — every delta is backed by a receipt, and the exam never gets
  easier ("optimized for fast iteration without weakening the exam").

This before/after arc must be the spine of the video, stated in the first 20
seconds and paid off at the end.

## Rubric map — where each point is won or lost

| Rubric line | Pts | Current cut (silent) | New cut must show/say |
|---|---|---|---|
| **Completeness** — core workflow runs without crashing | 15 | "COMPLETENESS" section shows the arm running, but a judge can't tell what workflow completed or what proof class it is | One continuous pass through the loop, live in Studio: capture → twin → demo → train → independent exam → receipt. Narrate "end to end, no crash, receipt written" |
| **Technical Depth** — real engineering, not a wrapper | 15 | Architecture card held 18 s, text unreadable, unnarrated | Narrated 20 s over the technical overview: custom 957K-param conditional-VAE ACT, MuJoCo 3.10 twin, COLMAP/Brush 3DGS pipeline, 20 Hz LeRobot teleop recorder, separate CPU/fp32 evaluator. Say "≈75 modules, every artifact hash-bound" |
| **Sponsor stack used meaningfully** | 15 | NVIDIA logos appear on one static slide | Show the GR00T N1.7 lane concretely: LeRobot v2.1 Parquet export (8,712 frames), Brev A100 run completing 1000/1000 steps, Nemotron orchestration / NemoClaw runtime cards. Screen-record the actual run logs/receipts, not just the diagram |
| **The "Why"** — articulate why this stack | 15 | Impossible — no audio | One scripted beat per tool: "GR00T for RGB/language generalization as the challenger lane; Brev A100s because the 3B model can't train locally; MuJoCo for contact-rich physics; LeRobot for reproducible SO-101 interfaces." The honest GR00T negative (0 mm lift, 125.724 mm XY, 13/15 gates, held-outs sealed) *demonstrates meaningful use* — we ran it to a graded verdict, not a logo slide |
| **Insight Quality** — non-obvious, useful output | 10 | "evidence, not vibes" tagline carries this alone | Say the thesis: "demos don't prove generalization; separating trainer from examiner does." Show a receipt JSON with per-gate thresholds — the non-obvious artifact |
| **Usability** — could a real user act on it tomorrow | 10 | Never addressed | 10 s: `git clone` → `uv run sim2claw studio` → read-only Studio in a browser. "A researcher reproduces the exam tonight" |
| **Creativity** — novel combination | 10 | Implied by pipeline poster only | Name the combo out loud: iPhone 3DGS + LLM scene proposal (display-only) + MuJoCo authority + combinatorial retargeting from teleoperated grasp *styles* + adversarially separated evaluator |
| **Performance** — speed or scale | 10 | Never addressed | "Teleoperate a handful of grasp styles → generate task instances combinatorially in sim" is the scale claim; 957K params trains locally on a laptop (MPS) in hours; 334,537-splat capture from one phone video; A100 runs are bounded and torn down |

**Estimated score of the current silent cut: roughly 40–50/100** (completeness
and depth partially land on visuals alone; both sponsor "why," usability,
and the improvement delta score near zero without narration).

## Gaps vs. the submission checklist (unchanged from v1 review)

1. **No audio.** The MP4 has no audio stream. Highest-impact fix.
2. **Must be recorded with Loom** (checklist bolds this). Play the edited
   b-roll full-screen and record it *through* Loom with live narration.
3. **"Show the core loop live."** No Studio interaction, terminal, or
   receipt appears in the current cut.
4. **Proof-class labels** must stay visible on robot footage (source teleop /
   gateway replay / autonomous-pick-under-review).
5. **Length**: keep 2:50–3:10 (checklist window is 2–5 min).

## Improved 3:00 shot plan (rubric-weighted)

★ = reuses footage already in the current cut. Narration ~140 wpm.

| Time | Visual | Narration beat | Rubric target |
|---|---|---|---|
| 0:00–0:20 | ★ Real robot over board, then a stark split card: "Revision 1: 309.6 mm error · 0 lift" vs "Revision 8: 17.4 mm · 94.88 mm held-out lift — same frozen exam" | Hook: "On its first run, our system couldn't touch a chess piece. Eight audited revisions later it passes a frozen held-out exam it was never allowed to grade. sim2claw is a robot-learning loop that gets measurably smarter every cycle — and can prove it." | Track thesis (first vs last run) |
| 0:20–0:45 | **Live Studio Calibration orbit** (landscape, "334,537 splats" badge) → MuJoCo workcell | Capture: iPhone video → Robo Scanner → verified 3DGS; reviewed MuJoCo twin owns geometry, contact, two SO-101 arms; LLM scene proposal is display-only — simulation state is the authority. | Depth + Creativity |
| 0:45–1:05 | ★ Team teleop footage; 20 Hz recorder receipt on screen | Teleoperate grasp *styles*, not thousands of task instances; generate instances combinatorially by object- and target-relative retargeting. That's the scale mechanism. | Performance + Depth |
| 1:05–1:30 | Training terminal → **live Studio rook-lift replay, 3D-inspect ↔ Recorded toggle** → zoom into `evaluation_receipt.json` gates | 957K-param ACT trains locally on Apple Silicon. Training cannot promote itself: a separate CPU/fp32 evaluator, thresholds frozen before evaluation, held-out seed. **94.88 mm lift — the number comes from the receipt, not from eyeballing video.** | Completeness + Insight |
| 1:30–1:55 | ★ Simulator-accuracy chart, cursor stepping through the 7 stages 309.6 → 17.4 mm | The learning mechanism: every failure becomes a counterexample in a versioned dataset; the factory loop recalibrates the twin and re-sits the *same* exam. 94.4% error reduction across 8 revisions — improvement without ever weakening the test. | **Track delta + learning mechanism (bonus credit)** |
| 1:55–2:20 | GR00T lane: Brev A100 run log "1000/1000 steps", LeRobot Parquet export, then the negative-verdict receipt "0 mm lift · 125.724 mm XY · 13/15 gates" | Why this stack: GR00T N1.7 as the RGB/language challenger lane, trained on Brev A100s from our LeRobot v2.1 export; MuJoCo for contact physics; LeRobot for reproducible SO-101 hardware. GR00T's rollout was terminal negative — and we report it with the same rigor, because a negative with receipts is reusable evidence. | **Sponsor stack + "Why" (30 pts)** |
| 2:20–2:40 | ★ Evidence Wall, tightened: each tile full-screen ~5 s with proof-class labels | Source episode → gateway replay (side, wrist) → autonomous pick under review. Recorded physical sources stay unqualified until calibration exists; the hardware path stays behind one reviewed gateway. | Completeness + Insight |
| 2:40–2:52 | Terminal: `git clone` → `uv run sim2claw studio` → browser Studio; brief `.factory/` ledger scroll | Anyone can clone the public repo, bootstrap with `uv`, and re-run the exam tonight. The repo itself was built the same way — an audited executor/reviewer agent loop, in reviewable slices. | Usability + track recursion |
| 2:52–3:02 | ★ Close on poster + repo URL | "sim2claw gets smarter every run and hands you the receipts. Evidence, not vibes — engineering you can trust, and grade." | Close |

## Recording workflow

1. Assemble the b-roll timeline (reuse current footage; swap the portrait
   orbit for a landscape Studio capture; capture the live Studio segments
   fresh).
2. Full-screen the timeline; record **through Loom with screen + mic**,
   narrating live. Satisfies the Loom rule while keeping edited visuals.
3. Rehearse once against a timer; target 2:50–3:10 at 1080p.

## Open items

- Confirm the sponsor(s) to name in the 30-pt sponsor beat (assumed NVIDIA:
  GR00T N1.7, Nemotron, NemoClaw, Brev — plus Hugging Face LeRobot).
- Confirm whether the submission deadline (July 19, 11 AM CST) was extended.
- Decide who narrates and whether Studio can be run live for fresh captures.
