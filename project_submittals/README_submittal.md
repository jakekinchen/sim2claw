# Submission Checklist

## **Due:** July 19th at 11 AM **CST**

**Where to submit:** 👇

### Required

- [ ]  **Project title & Team Name**
  - sin2claw
- [ ]  **Track selected**
  - Recursive Intelligence Track
- [ ]  **2–5 min Loom video** (loom.com). Show the core loop live.
    - [ ]  **YOUR VIDEO MUST BE RECORDED WITH LOOM!**

    Demo Video Instructions

- [ ]  **Repo link** (Make sure it’s public!).
  - https://github.com/jakekinchen/sim2claw
    - <todo> verify repo is public
        - [ ]  Must include a **README** with:
            - [ ]  Quick start (commands to run)
            - [ ]  Tech stack & architecture diagram (simple is fine)
            - [ ]  How to reproduce the demo (env vars, API keys, sample .env)
            - [ ]  Any **datasets/synthetic data** used + provenance
            - [ ]  Known limitations & next steps
- [ ]  **Deployed URL (if any)** or short screen capture of the working app
- [ ]  **Team roster** (names, roles, contacts)
  - Aishwarya Badlani, Data Engineer, aishwarya08badlani@gmail.com
  - Jake Kinchen, Team Lead and Robotics Engineer, jakekinchen@gmail.com
  - Jeff Pape, Software Engineer, jeff.pape@gmail.com
  - Mahata Abhinav, Product Manager, Mahata.abhinav@gmail.com
- [ ]  **Short write-up (150–300 words):** problem → who it helps → solution → impact

**Problem.** Teaching a robot arm a manipulation task like picking up a chess piece usually means one of two bad options: hand-scripting brittle motions that break the moment anything shifts, or hand-teleoperating thousands of individual task instances to train a policy. Both scale badly, and most robot-learning pipelines blur the line between "we demonstrated this" and "the policy actually generalized," so results are hard to trust.

**Who it helps.** Robotics researchers, sim-to-real engineers, and anyone building learned manipulation who needs reproducible, honestly-scoped evidence rather than impressive-looking demos.

**Solution.** sim2claw is a clean-room simulation-to-robot stack. A photo-aligned MuJoCo workcell (measured table, chessboard, 32 dynamic pieces, two articulated SO-101 arms) runs entirely in-process on Apple Silicon. Its governing idea: teleoperate only grasp styles and corrections, then generate task instances combinatorially in simulation via object- and target-relative trajectory retargeting. A frozen ACT (Action Chunking Transformer) policy learns the contact-sensitive skills; a separate CPU/fp32 evaluator on a held-out seed decides pass/fail — a policy can never promote itself. A read-only visualization studio replays every episode with phase-aligned video and receipts.

**Impact.** It reaches a verifiable milestone — a fresh 957K-parameter ACT policy trained locally and lifted a held-out rook 94.88 mm — while rigorously refusing to overclaim: no gateway, no physical-robot authority, no "it generalized" without frozen held-out proof. The payoff is a trustworthy, reproducible foundation for learned manipulation, where each capability is backed by fresh code and its own evidence.

## Pipeline poster

![sim2claw simulation-to-robot data pipeline poster](./sim2claw-pipeline-poster-feedback-loop.png)

The poster adds the evidence feedback loop after receipts and replay:

- **Successful receipts** — accepted demonstrations enter the versioned training dataset; held-out policy passes may advance the frozen milestone.
- **Failed receipts** — kept as counterexamples (never imitation rows); failure reasons are clustered to drive targeted correction and recovery demonstrations.
- Both paths produce a new versioned dataset and receipt, then replay through the same frozen evaluator gates.

## Technical architecture poster

![sim2claw technical architecture poster](./sim2claw-technical-architecture-poster.png)

This poster maps the concrete technologies behind each pipeline stage:

1. **Scene capture & build** — a Polycam scan (glTF + RoomPlan JSON) is converted by a custom glTF-to-OBJ converter and assembled into the `photo_aligned_chess_workcell_v1` MuJoCo 3.10 scene with SO-101 arms from MuJoCo Menagerie, all on a Python 3.12 + `uv` runtime.
2. **Demonstrations** — scripted IK experts (`chess_task`) and a 20 Hz teleop recorder built on LeRobot's SO-101 leader produce `samples.jsonl` plus a `recording_receipt.json`.
3. **Policy training** — an ACT conditional-VAE Transformer trains in PyTorch 2.11 on Apple MPS, emitting `checkpoint.pt` and a training receipt; a parallel GR00T N1.7 lane exports LeRobot v2.1 Parquet + MP4 datasets (PyArrow) for fine-tuning on NVIDIA A100 / CUDA 12.8.
4. **Independent evaluation** — a separately owned CPU/fp32 evaluator applies frozen gates from `configs/tasks/*.json` and writes a per-gate pass/fail `evaluation_receipt.json`.
5. **Receipts & Studio** — every artifact carries a versioned JSON receipt (`sim2claw.*.v1` schemas), replayable as FFmpeg-encoded MP4s in the read-only Studio (vanilla JS + Python HTTP server).

Throughout, training never grades itself, and `physical_gateway` remains the only reviewed path to robot hardware.

## Scene extraction figure

![sim2claw physical scene extraction to sim scene generation](./sim2claw-scene-extraction-figure.png)

This figure shows the photo-aligned workcell path: Polycam capture → glTF / RoomPlan JSON / overhead photo → OBJ/MTL mesh and measured layout → MuJoCo procedural build with physics properties and SO-101 arms → photo-aligned simulation.
