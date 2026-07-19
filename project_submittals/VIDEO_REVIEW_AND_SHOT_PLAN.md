# Demo Video Review & Improved Shot Plan

Review of `sim2claw-full-demo.mp4` (3:21, 1080p30) against the submission
checklist and the 3-minute Loom script in `README_submittal.md`.

## Verdict in one paragraph

The current cut has strong raw material — real robot footage, the 3DGS orbit,
the simulator-accuracy chart, and clean section titles — but it is a **silent
slideshow**, and the checklist explicitly requires a **Loom recording with
narration that shows the core loop live**. Roughly 60% of the runtime is
static poster imagery, and the final 80 seconds sit on a single unchanging
"Evidence Wall" layout. The two headline numbers (94.88 mm held-out rook
lift, 94.4% simulator error reduction) appear only as caption text; the
project's biggest differentiators — the independent evaluator receipts, the
honest GR00T negative result, and the Recursive Intelligence (agent-built)
angle — never appear at all.

## Current video timeline (observed)

| Time | Section title card | Content | Issue |
|---|---|---|---|
| 0:00–0:10 | sim2claw | Pipeline poster (static) | Fine as a hook visual, but no narration hook |
| 0:10–0:28 | SCENE EXTRACTION | Scene-extraction figure (static) | Held ~18 s with no motion or voice; also this figure is flagged in `README_submittal.md` as the *older* figure not to be used as current-architecture evidence |
| 0:30–0:48 | WORKCELL ORBIT | 3DGS orbit clip, portrait, letterboxed | Blurry frames, portrait crop wastes 2/3 of the screen; the Studio Calibration orbit (landscape, with the "334,537 splats" badge) is the stronger asset |
| 0:50–1:08 | TECHNICAL DEPTH | Runtime architecture card (static) | 18 s static; card text is unreadable at a glance and is never narrated |
| 1:10–1:15 | TECHNICAL EXECUTION | Real footage: team teleoperating | Great footage — too short |
| 1:15–1:38 | COMPLETENESS | Real robot arm over chessboard | Good; unclear to a judge whether this is autonomous, replay, or teleop (proof-class labeling is the project's whole thesis) |
| 1:40–1:48 | HELD-OUT RESULT | Static sim render, "94.88 mm rook lift" caption | The flagship result shown as a still image — show the motion + the `evaluation_receipt.json` |
| 1:50–1:58 | SIMULATOR ACCURACY | Error-progression chart, "94.4%" | One of the best slides; deserves narration |
| 2:00–3:21 | EVIDENCE WALL | 4-up grid (source / 2 replay views / autonomous pick) | 80+ s (40% of runtime) on one layout with small tiles and large black areas; no explanation of what passes/fails |

## Gaps vs. the submission checklist

1. **No audio.** The MP4 contains no audio stream at all. The Loom script
   specifies screen + microphone; at ~140 wpm the script is written to carry
   the entire story. This is the single highest-impact fix.
2. **Must be recorded with Loom.** The checklist bolds this. An edited MP4
   with title cards may not qualify. Safest path: play the edited b-roll
   timeline in a window and record it *through Loom* with live narration
   (or do the live Studio demo per the script).
3. **"Show the core loop live."** Nothing in the cut is live: no Studio
   interaction, no terminal command, no receipt JSON, no README. The script
   already choreographs this (queue the ACT rook-lift eval in Studio, orbit
   the splat in Calibration, toggle 3D-inspect vs Recorded).
4. **Track story missing.** The submission is in the **Recursive Intelligence
   Track**, but the video never mentions the agent-built workflow, the
   learning factory, or the "training never grades itself" recursion. That is
   the judging hook for this track.
5. **GR00T honest-negative missing.** The pre-record notes *require* the
   precise framing (1000/1000 steps, 0 mm lift, 125.724 mm XY error, 13/15
   gates, held-outs sealed). It is also the project's most memorable
   credibility beat: "we report our failures with the same rigor."
6. **Proof-class labels.** The robot b-roll must keep its evidence class
   visible (source teleop / gateway replay / autonomous pick under review) —
   the Evidence Wall labels do this; the Completeness section does not.
7. **Length.** 3:21 is inside the 2–5 min submission window but over the
   script's 2:50–3:10 target. Cutting the Evidence Wall to ~25 s pays for
   every addition above.

## Improved 3:00 shot plan

Keep the existing title-card style. Narration below is timed at ~140 wpm.
Sections marked ★ reuse footage already in the current cut.

| Time | Visual | Narration beat |
|---|---|---|
| 0:00–0:15 | ★ Pipeline poster → quick cut to real robot over board | Hook (verbatim from script): brittle scripts vs. thousands of demos; impressive demos ≠ generalization; sim2claw generates experience in sim and produces trustworthy evidence. |
| 0:15–0:40 | **Live Studio Calibration orbit** (landscape, "334,537 splats" badge visible) → MuJoCo workcell render | iPhone video → Robo Scanner → verified 3DGS; splat is visual calibration only; reviewed MuJoCo workcell owns geometry, contact, and two SO-101 arms. |
| 0:40–1:00 | ★ Team teleop footage + 20 Hz recorder; brief scene-extraction figure as an overlay, not a held slide | Teleoperate grasp *styles*, not every task instance; generate instances combinatorially in sim. LeRobot SO-101 leader/follower. |
| 1:00–1:20 | ACT training terminal/receipt → **live rook-lift replay in Studio, 3D-inspect ↔ Recorded toggle** | 957K-param ACT trains locally on Apple MPS. Training cannot promote itself: a separate CPU/fp32 evaluator, frozen gates, held-out seed. |
| 1:20–1:35 | Zoom into `evaluation_receipt.json` gates while replay loops | **94.88 mm held-out rook lift** — the number comes from the receipt, not from eyeballing a video. |
| 1:35–1:55 | ★ Simulator-accuracy chart (animate the line or cursor along stages) | Eight sim revisions drove event-fit error **309.6 → 17.4 mm (94.4%)**; failures feed back as targeted corrections, never silently relabeled as successes. |
| 1:55–2:15 | GR00T slide: "1000/1000 steps · 0 mm lift · 125.724 mm XY · 13/15 gates" | The honest negative, exactly as scripted. "A completed negative experiment, not learned-policy success." |
| 2:15–2:35 | ★ Evidence Wall (tightened: full-screen each tile ~5 s instead of static 4-up), proof-class labels on screen | Source episode → gateway replay (side + wrist) → autonomous pick under review. Every artifact ships with hashes, receipts, deterministic replay. |
| 2:35–2:50 | Autonomous-workflow visual (executor/reviewer/manager loop or `.factory/` ledger scroll) | Recursive Intelligence: the stack itself was built by an audited AI agent loop, and the learning factory recursively improves the dataset — with an evaluator that the trainer can never touch. |
| 2:50–3:00 | ★ Close on poster + repo URL | Close (verbatim from script): "…simulation-to-robot engineering that users — and judges — can trust." |

## Recording workflow suggestion

1. Assemble the b-roll timeline above (reuse the current cut's footage; swap
   the portrait orbit for a landscape Studio screen capture).
2. Open the timeline full-screen; start a **Loom screen + mic** recording;
   narrate the script live while the timeline plays. This satisfies the
   "recorded with Loom" rule while keeping edited visuals.
3. Alternative that is even more "live": follow the script's pre-record
   checklist (Studio running, eval queued, Calibration loaded) and demo
   Studio directly in Loom, using the edited footage only for the teleop and
   Evidence Wall beats.
4. Keep final length 2:50–3:10. Record at 1080p. Do a single full rehearsal
   pass against a timer before the real take.
