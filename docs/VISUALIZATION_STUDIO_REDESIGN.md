# Visualization Studio Redesign

Status: implemented and refined

Date: 2026-07-18 America/Chicago

## Product thesis

The subject is a read-only robotics evidence studio for researchers and
operators reviewing simulation episodes. Its single job is to make one episode
immediately legible and replayable while keeping tasks, sibling episodes, live
processes, and robot context one deliberate action away.

The replay is the product. Counts, process state, proof metadata, and robot
descriptions support it; they do not compete with it.

## Design principles

1. **One dominant surface.** The selected episode and its temporal structure
   own the first screen.
2. **Progressive disclosure.** Show the decision-making minimum first. Open
   episode evidence, live-process detail, library groups, and robot context only
   when requested.
3. **Content before chrome.** Actual episode media is the default thumbnail.
   A deterministic phase portrait is only a fallback, never a replacement
   for recorded evidence.
4. **Motion means time.** Safety orange is reserved for playback, progress,
   and live processes. Ambient decoration does not move.
5. **Proof stays explicit.** Evaluator result, proof class, and physical-
   authority boundary remain visible without repeating them on every card.
6. **Quiet by default, informative on demand.** An idle process rail collapses
   to a status control. A running process earns space and can reveal details.

## Visual system

### Color tokens

| Token | Value | Use |
| --- | --- | --- |
| Ceramic | `#ecefed` | application ground |
| Chalk | `#f8f9f6` | primary surfaces |
| Carbon | `#151816` | stage, text, deep contrast |
| Graphite | `#6b716d` | secondary text and rules |
| Motion orange | `#ff5a1f` | playhead, playback, live work only |
| Verdict green | `#0b6847` | accepted evaluator results only |

Failure uses a restrained red and warnings use amber, but neither becomes a
brand accent.

### Typography

- **Barlow Semi Condensed:** episode titles, task identities, view titles.
- **IBM Plex Mono:** timecode, metrics, phase names, proof metadata.
- **System sans fallback:** explanatory prose only if the web fonts fail.

The minimum rendered utility size is 11px. Hierarchy comes from size, weight,
spacing, and contrast instead of shrinking most of the interface into labels.

### Signature

The timeline and each fallback thumbnail share an episode-specific phase
portrait: a restrained path derived from episode identity and real phase
durations.
In the stage timeline, the orange playhead travels through labeled semantic
phases. The portrait is explicitly visual indexing, not a measured robot
trajectory.

## Information architecture

### Desktop monitor

```text
+-----------------------------------------------------------------------+
| sim2claw | Replay Library Robots | project | pass ratio | live        |
+---------------------+-------------------------------------------------+
| Task filter         | Episode title                         PASS       |
| Search              |                                                 |
|                     |                 REPLAY STAGE                    |
| Compact episode     |                                                 |
| navigator           +-------------------------------------------------+
|                     | play | semantic filmstrip + playhead | speed    |
|                     +-------------------------------------------------+
|                     | selected metrics | Evidence details            |
+---------------------+-------------------------------------------------+
```

- The navigator is approximately 300px. The stage receives the remaining
  width and never shares the hero row with an empty live panel. Its height is
  capped so the stage, filmstrip, and metrics fit inside one laptop viewport.
- Live work opens in a right-side drawer. When idle it is one compact header
  control.
- Episode evidence opens in a secondary inspector below or beside the stage.

### Views and filter states

- **Replay:** the default workbench: task-grouped navigator, stage, filmstrip,
  performance metrics, and optional evidence/process drawers.
- **Library:** grouped by task. The first eight episodes are visible; larger
  groups disclose the rest with “Show all.” Cards prioritize distinct media,
  evaluator result, duration, and instruction. Tasks are filters and group
  headers here, not a redundant fourth destination.
- **Robots:** embodiment sheets with one visual, simulation status, side/model,
  scene-wide replay coverage, and a single authority notice.

### Mobile

```text
+-------------------------------+
| wordmark      live / offline   |
+-------------------------------+
| title + verdict               |
| REPLAY STAGE (16:10)          |
| playback + semantic timeline  |
| essential metrics             |
| [Browse task episodes]        |
| [Evidence details]            |
+-------------------------------+
| Replay   Library   Robots      |
+-------------------------------+
```

The replay remains first. Browsing and metadata become explicit disclosures;
the interface never begins with context-free KPI counts or a multi-thousand-
pixel wall of cards. Touch controls are at least 44px.

## Implementation slices

1. Replace the long-page shell with Replay, Library, and Robots route views.
2. Convert the task shelf into a compact, searchable episode navigator.
3. Replace the native-looking scrubber presentation with a semantic filmstrip,
   labeled phases, hover preview, and honest step labels.
4. Preload frame episodes and keep media thumbnails above deterministic
   fallbacks.
5. Add live-process and episode-evidence drawers with stable focus behavior;
   derive bounded client-side process history from the existing polling data.
6. Group the episode library by task and collapse large groups by default.
7. Rebuild robots as concise embodiment sheets.
8. Apply the responsive system, reduced-motion behavior, and keyboard paths.
9. Replace stale workcell posters with versioned current-scene overview and
   per-arm cameras; keep them inspection-only so evaluator inputs remain frozen.

## Acceptance criteria

- The selected replay is the largest and highest-contrast element at desktop
  and mobile widths.
- No idle live panel consumes hero-screen width.
- Replay, Library, and Robots are distinct views, not scroll anchors; tasks are
  filters within Replay and Library.
- Every episode card displays real media when available; fallbacks differ by
  episode and are visually subordinate to evidence.
- Phase names are visible and the active phase follows playback.
- Video stepping is labeled in seconds; frame stepping is labeled in frames.
- The evaluator verdict remains visible on mobile.
- Large episode groups are collapsed by default and can be expanded.
- Utility text is at least 11px and touch targets are at least 44px.
- Keyboard replay, visible focus, reduced motion, and read-only authority
  messaging remain intact.
- The board-reaching arm is visually centered along the board length in the
  current-scene overview, and per-arm posters are distinct.

## Dependency record

The redesign vendors the Latin 400/600 WOFF2 assets from
`@fontsource/barlow-semi-condensed@5.2.7` and
`@fontsource/ibm-plex-mono@5.2.7`. Both are SIL OFL 1.1 and were adopted only
for local, deterministic typography; the studio keeps no Node runtime
dependency. License texts are stored in `studio_web/assets/fonts/licenses/`.
