# Two-level presentation architecture

Date: 2026-07-19 America/Chicago

## Communication decision

The project now has two deliberately different audience views instead of one
diagram trying to carry every implementation detail:

1. The simple view explains one product loop: capture, build the twin, teach,
   and prove/improve.
2. The technical view expands that loop into three reviewable engines: scene
   generation, robot learning, and LLM orchestration, joined by an evidence
   plane and evaluator-owned gates.

The simple view is the opening/submission image. The technical view is the
follow-up for engineering reviewers. The older feedback-loop and technical
architecture posters are retired from current-facing use because their pixels
contain obsolete `GROOT` spelling and, in the feedback poster, a fabricated
illustrative score.

## Generated assets

Both final PNGs began with the built-in OpenAI image-generation tool. The
simple overview was a new generation. The technical overview was a new
generation followed by targeted image edits using only the immediately prior
generated version as the edit source. The visual direction was a
warm off-white technical-paper background, industrial metrology styling, dark
navy typography, restrained teal/orange accents, large audience-facing copy,
and minimal arrows.

| Final asset | Dimensions | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `project_submittals/sim2claw-simple-overview.png` | 1680×900 | 1,771,606 | `7f528a93ade52fbb44f8b3a7cf1b04fa550a06341393da01940da22240d92028` |
| `project_submittals/sim2claw-technical-overview.png` | 1680×900 | 1,896,859 | `ceb99f49368a6535c2deedb9e111368b4b67800edf167c5752644c7bf450b980` |

Built-in generation sources retained by Codex:

- simple final:
  `/Users/kelly/.codex/generated_images/019f78b1-e920-7160-8b51-548c33d19e19/exec-3a46fa98-c93f-4e3a-b95e-836f7d7f0944.png`
- technical clean-label edit source:
  `/Users/kelly/.codex/generated_images/019f78b1-e920-7160-8b51-548c33d19e19/exec-cb822c4d-2344-4345-b1d6-f0230cfd88d9.png`

The generated technical edit supplied one continuous native off-white label
area with no character boxes. Because repeated generative edits substituted
letter O glyphs, the final label was deterministically typeset over that one
clean patch as two lines: `ACT / GR00T` and `training`. The command used
ImageMagick 7.1.2-16, macOS `Menlo.ttc` for the first line (2,156,036 bytes,
SHA-256 `dc256e0b39c2a6fec947129d421fef41b8b429f58f9b6e5d1b148c87f775c1f6`),
and `DIN Condensed Bold.ttf` for the second line (212,040 bytes, SHA-256
`36958182a424e1e8a1307b2636a615a6323ce1bbfadda136735ab4fb3bd26ceb`).
The actual numeral-zero glyphs are visibly slashed and have no boxes, outlines,
borders, or glyph tiles. Both 1672×941 generation results were then normalized
to exactly 1680×900. The final saved PNGs were reopened and inspected at
original resolution after resizing; macOS Vision OCR reads the saved technical
label as `ACT / GR00T`, and the dimensions and hashes above were computed from
those saved files.

The scene-generation lane received one final deterministic semantic edit after
owner review. `Versioned JSON scene proposal` now reaches the reviewed scene
through an explicitly labeled `VIA AGENTIC CODING + REVIEW` step, and the
result is labeled `REVIEWED MUJOCO + THREE.JS SCENE`. This connector describes
an authored and reviewed workflow, not deterministic JSON compilation or
automatic promotion into either geometry layer. The edit used ImageMagick
7.1.2-16 and macOS `Arial Narrow Bold.ttf` (184,420 bytes, SHA-256
`fcf34b330033e26c06e9bd466bea5a3e4b2f39272972275369beb7d8b257ed57`).
The actual saved PNG was reopened at 1680×900; macOS Vision OCR recognizes
`VIA AGENTIC CODING + REVIEW`, `REVIEWED MUJOCO + THREE.JS SCENE`, and
`ACT / GR00T`.

## Prompt record

The simple prompt requested exactly four large moments connected by one flow:
`CAPTURE`, `BUILD THE TWIN`, `TEACH`, and `PROVE & IMPROVE`, with the takeaway
`One loop. Three engines: simulation generation, robot learning, and
LLM-guided improvement.`

The technical prompt requested exactly three system zones:
`SCENE GENERATION`, `ROBOT LEARNING`, and `LLM ORCHESTRATION`, plus a
`SHARED EVIDENCE PLANE`. A targeted edit removed fabricated evaluator metrics
and replaced them with the neutral contract `Pass / fail by frozen gate` and
`Receipt + deterministic replay`. A second targeted edit removed fictional
scene/dataset version identifiers. The final typography correction renders the
NVIDIA model name as the five-character sequence `G`, `R`, `0`, `0`, `T` in one
clean unboxed line, with `training` below. The final deterministic scene-lane
edit added the agentic-coding and review mediation described above without
changing the other two system lanes.

Both prompts explicitly prohibited Polycam, RoomPlan, dense code, microscopic
labels, unverified metrics, and watermarks.

## Submission proof-state reconciliation

The submission copy now records the terminal Brev result without conflating
training completion with policy success:

- training completed 1000/1000 steps;
- the sole frozen C8→A6 development rollout was terminal negative;
- measured result: 0 mm lift, 125.724 mm final XY error, and 13/15 gates;
- held-outs remained sealed;
- checkpoint weights were not retained.

This is a completed negative experiment, not GR00T learned-policy evidence.

## Claim boundary

- Video and 3DGS provide visual context.
- LLM analysis may propose semantics, hierarchy, approximate geometry, data,
  or recovery changes.
- In the technical overview, `via agentic coding + review` means an agent may
  use that proposal as an authoring aid; it does not mean the JSON is compiled
  or deterministically converted into geometry.
- Studio displays the proposal hierarchy beside geometry built independently
  from the accepted MuJoCo manifest; JSON drives neither layer.
- Reviewed MuJoCo geometry owns accepted simulation state.
- The frozen evaluator owns policy pass/fail evidence.
- Physical motion remains behind the reviewed, operator-gated gateway.

No benchmark, `GOAL.md`, or project-state field was changed for this
presentation closeout.
