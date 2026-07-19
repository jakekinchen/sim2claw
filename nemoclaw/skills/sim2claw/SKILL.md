---
name: sim2claw
description: Operate the bounded Sim2Claw B-G pawn project and report evidence without inflating claims.
---

# Sim2Claw project skill

1. Change to `/sandbox/sim2claw` and read `nemoclaw/AGENTS.md`.
2. Inspect the project with:
   `uv run sim2claw project-inspect --project configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json`
3. Check the most recent bounded result with:
   `uv run sim2claw pipeline-status --project configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json`
4. Run only the requested stage with:
   `uv run sim2claw pipeline-stage --project configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json --stage <stage>`
5. Read the resulting
   `runs/nemoclaw/projects/<project_id>/runs/*/stage_result.json` before
   summarizing.

Pipeline status is project-scoped and hash-bound. Treat a schema, project ID,
evaluator, stage, status, or result-digest mismatch as a hard failure; never
substitute another project's latest result.

The project, bundle, pipeline result/status, and deployment receipt must carry
the same exact five-field authority contract from `nemoclaw/AGENTS.md`. Treat
missing, extra, mistyped, or nonzero/true values as a hard failure.

Available stages are `inspect`, `calibrate-sim`, `evaluate-skills`,
`train-candidates`, and `compare-candidates`. Do not bypass a blocked stage.
Do not describe source recordings as admitted data, retrospective evaluation as
held-out proof, or a training artifact as a promoted policy. The complete
authority contract is always fail-closed in this deployment.
