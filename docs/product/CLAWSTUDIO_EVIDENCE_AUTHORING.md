# ClawStudio: Evidence-Gated Scene Authoring for Physical AI

Status: proposed product direction; implementation not yet started

Date: 2026-07-22 America/Chicago

This document authorizes no robot motion, new physical capture, paid training,
simulator promotion, or physical-transfer claim. It defines a product direction
and a dependency-ordered implementation plan.

## Decision

Extend sim2claw from a fixed, evidence-rich workcell into an editable robotics
scene-authoring system, but do not compete as a generic text-to-3D generator.
The product wedge is narrower and more valuable:

> Turn text, images, video, scans, measurements, and robot traces into an
> editable workcell whose geometry, physics, tasks, uncertainty, and claim
> boundaries are inspectable, testable, and independently certifiable.

The working product name is **ClawStudio**.

The concise positioning is:

> **Gizmo makes simulation-ready worlds. ClawStudio makes task-proven twins.**

The more precise claim is:

> ClawStudio is an evidence-gated authoring agent for robotics. It proposes and
> edits structured scenes, compiles them into executable simulators, runs
> embodiment- and task-specific probes, identifies unsupported assumptions, and
> refuses to promote a scene beyond the evidence that supports it.

## Competitive baseline

The public Gizmo beta establishes a strong baseline for AI-native robotics scene
authoring: prompt or reference input, structured and editable geometry,
articulation, physics metadata, a browser editor, browser preview, an API, and
exports to USD, MJCF, SDF, and GLB.

ClawStudio should not try to match that breadth first. A catalog of thousands of
assets, general organic asset generation, precision CAD, and simultaneous
support for every simulator would bury the project's existing advantage.

The unoccupied product surface is the layer between **a scene that compiles**
and **a twin that deserves to influence robotics decisions**:

- Which dimensions were measured, visually estimated, generated, or inherited?
- Which frame transforms are metric and which are merely plausible?
- Which collision and contact assumptions matter to the declared task?
- Does the scene preserve behavior under the target robot, sensor, controller,
  and evaluator?
- What real or simulated observation would most efficiently resolve an
  ambiguity?
- Which certificates become invalid after a scene edit?
- When should the system abstain instead of exporting a confident-looking twin?

sim2claw already contains the foundations for this answer: a repo-native MuJoCo
workcell, a visual 3DGS reference, a proposed semantic scene hierarchy, strict
proof classes, immutable receipts, action-frozen replay, SAIL mechanism beliefs,
TwinWorthiness gates, and an evaluator-gated policy/data factory.

## Product principles

### 1. Structure is necessary but not sufficient

Every scene remains a structured object graph with editable transforms,
geometry, materials, articulation, collision, physical properties, sensors,
semantic regions, robot spawns, and task affordances. A baked visual mesh is not
the source of truth.

### 2. Every important field carries evidence

A numerical value must not silently become a fact because an agent emitted it.
Every authoring field that can affect simulation or task behavior binds to an
evidence record with:

- source identity and content hash;
- acquisition or generation method;
- units and coordinate frame;
- authority class;
- uncertainty or explicit absence of metric support;
- reviewer and review status;
- downstream certificates that depend on it.

### 3. Authoring is task- and embodiment-grounded

A robotics scene is not complete merely because it looks correct or remains
stable under gravity. The authoring contract includes the target robot,
controller assumptions, sensors, reset distribution, task objects, semantic
regions, and evaluator-owned consequences.

### 4. The agent proposes; deterministic systems compile and judge

The agent may propose objects, relations, geometry, joints, physics,
measurements, scene edits, and discriminating probes. Typed validators,
simulator compilation, deterministic probes, and separately owned evaluators
admit or reject those proposals.

### 5. Certificates are explicit and invalidatable

ClawStudio never exposes one undifferentiated "simulation ready" badge. It emits
narrow certificates with dependency sets. Editing a depended-on field
invalidates the certificate until its tests rerun.

### 6. Appearance, geometry, physics, and authority remain separate

A Gaussian Splat, generated mesh, or browser projection may supply appearance
and visual registration context. It does not silently establish metric scale,
collision geometry, contact parameters, task coordinates, or robot authority.

### 7. The first product is local, reproducible, and MuJoCo-first

The initial product should preserve the repository's local-first, hash-bound,
clean-clone workflow. MuJoCo and the current SO-101 tabletop workcell are the
first executable backend and golden fixture. Export interfaces should be
backend-neutral, but USD and SDF are later milestones rather than MVP blockers.

## Core artifact: `WorkcellSpec.v1`

`WorkcellSpec.v1` becomes the editable source of truth for an authored workcell.
It is not a replacement for retained evidence, evaluator contracts, or SAIL
artifacts. It links those systems through stable identities.

The top-level contract should include:

```text
WorkcellSpec.v1
  metadata
  coordinate_systems
  assets
  entities
  relations
  robot_spawns
  sensors
  semantic_regions
  task_bindings
  global_physics
  source_registry
  field_evidence
  variants
  compiler_profiles
  certificate_index
  edit_ledger
```

### Entities

Each entity exposes a stable ID, semantic role, parent, transform, visual
representation, collision representation, rigid-body properties, articulation,
affordances, and backend-specific extensions only when unavoidable.

### Field-level evidence

Evidence should be keyed by JSON Pointer so the scene remains readable while
individual values remain auditable:

```json
{
  "field_evidence": {
    "/entities/chess_board/transform/translation": {
      "status": "estimated",
      "source_ids": ["iphone_video", "roomplan_capture"],
      "units": "m",
      "frame": "table",
      "uncertainty": {
        "kind": "bounded_interval",
        "value": [0.015, 0.030]
      },
      "review_status": "unreviewed",
      "authority": ["visualization", "simulation_candidate"]
    }
  }
}
```

Initial evidence statuses:

- `generated`
- `observed_nonmetric`
- `visually_estimated`
- `measured`
- `reviewed`
- `evaluator_accepted`
- `unknown`

Initial authority classes:

- `visualization`
- `simulation_candidate`
- `task_evaluation`
- `synthetic_data_generation`
- `physical_transfer`
- `physical_control`

The default is the least authority. No status implies a stronger authority.

### Scene variants

A scene may contain bounded variants or posterior particles for unresolved
mechanisms. Variants must state whether they represent domain randomization,
uncertainty, a competing model structure, or an unreviewed hypothesis. A
successful rollout in one variant cannot promote the base scene.

### Edit ledger

Every agent or manual edit appends:

- natural-language instruction or UI operation;
- typed patch;
- before and after hashes;
- fields and entities touched;
- validator results;
- certificates invalidated;
- reviewer state;
- rollback target.

The scene history is therefore an auditable sequence of structural changes, not
an opaque autosave stream.

## Certificate ladder

The MVP should expose the following independent certificates:

1. **SchemaValid** — the typed scene graph and all references validate.
2. **FrameConsistent** — units, handedness, up axis, frame ownership, and
   transforms are explicit and internally coherent.
3. **BackendCompiles** — the selected backend compiles from a clean runtime.
4. **DynamicsSmoke** — the scene settles and bounded joint/contact probes remain
   finite and stable.
5. **TaskReady** — the declared robot, reset, sensors, regions, and evaluator can
   execute without missing identities or unsupported authority.
6. **ReplayPredictive** — action-frozen held-out trajectory and event criteria
   pass for the declared evidence slice.
7. **TwinWorthy** — the existing evaluator-owned TwinWorthiness contract passes
   for its exact task and policy scope.
8. **SyntheticDataAuthorized** — the twin may generate candidate training rows
   for the declared lane.
9. **PhysicalTransferEligible** — a separately owned physical-transfer gate has
   passed. This is never implied by the earlier certificates.

Each certificate binds exact scene, compiler, robot, controller, task,
evaluator, dataset, and runtime identities.

## Product interface

ClawStudio should add an **Author** workspace beside the current evidence-first
Replay, Library, and Robots views.

```text
+--------------------------------------------------------------------------------+
| ClawStudio | Author | Replay | Library | Robots | certificates | live boundary |
+----------------------+--------------------------------------+--------------------+
| Agent / scene tree   | 3D workcell                          | Evidence inspector |
|                      | - structured geometry                | - selected field   |
| prompt / edits       | - 3DGS appearance overlay            | - source + hash    |
| entity hierarchy     | - robot and sensor frames            | - uncertainty      |
| unresolved items     | - task regions and affordances       | - authority        |
|                      |                                      | - affected certs   |
+----------------------+--------------------------------------+--------------------+
| Tests and certificates | edit diff | probe proposal | compile / evaluate        |
+--------------------------------------------------------------------------------+
```

The decisive interaction is not only "make the drawer deeper." It is:

> "Move the board closer to the left arm, preserve the camera registration,
> rerun the pawn task probes, and tell me which prior certificates no longer
> hold."

The system responds with a typed diff, a visual preview, invalidated
certificates, a bounded test plan, and an abstention when the evidence cannot
support the requested claim.

## Agent loop

The authoring agent follows this governed loop:

```text
prompt / images / video / scan / existing spec
  -> semantic and structural proposal
  -> WorkcellSpec candidate with field-level evidence
  -> schema, frame, unit, and dependency validation
  -> deterministic backend compilation
  -> embodiment- and task-specific smoke probes
  -> residual / failure routing
  -> ranked edit or measurement proposal
  -> human review or bounded automatic patch
  -> certificate rerun
  -> accepted spec, rejected candidate, or explicit abstention
```

When real traces exist, SAIL owns the deeper loop:

```text
authored scene
  -> action-frozen replay
  -> residual field and mechanism belief graph
  -> bounded structural or parameter intervention
  -> predictive TwinWorthiness evaluation
  -> synthetic-data and policy factory only after admission
```

## Killer demonstration

The first public demonstration should use the existing SO-101 chess workcell.

1. Upload the retained iPhone video or select its hash-bound release and ask:
   "Reconstruct this two-arm tabletop workcell and create the pawn-transfer task."
2. Show the Gaussian Splat as appearance context while the agent proposes an
   editable semantic scene graph.
3. Display which fields are observed, estimated, measured, reviewed, or unknown.
4. Ask the operator for one high-information metric measurement rather than a
   long manual modeling session.
5. Compile the scene into MuJoCo and render it in the same Studio.
6. Run deterministic robot, camera, contact, and task probes.
7. Surface the exact unsupported assumptions or mismatches, such as camera pose,
   board registration, gripper collision, or contact parameters.
8. Apply one reviewed edit and visibly invalidate and rerun dependent
   certificates.
9. Run the action-frozen replay and TwinWorthiness gate.
10. End with either a narrowly certified task twin or an honest abstention plus
    the next most informative measurement.

This demonstration proves a stronger capability than attractive scene export:
ClawStudio can explain why a workcell should or should not be trusted for a
specific robot task.

## MVP scope

The MVP is deliberately narrow:

- one backend: MuJoCo;
- one robot family: SO-101;
- one workcell class: tabletop manipulation;
- one golden fixture: the current chess workcell;
- primitives and reviewed existing robot assets before general asset generation;
- JSON patch and direct manipulation before a broad natural-language editor;
- current 3DGS appearance pathway as visual context only;
- current evaluator, SAIL, and Studio contracts reused rather than replaced.

The MVP does not require:

- a general asset marketplace;
- photorealistic or organic text-to-3D generation;
- browser physics as metric authority;
- Isaac Sim, Gazebo, or ROS export;
- autonomous physical probing;
- a successful learned physical policy.

## Dependency-ordered implementation

### A0 — Freeze the authoring contract

- Add the `WorkcellSpec.v1` JSON Schema.
- Define evidence statuses, authority classes, JSON-Pointer evidence binding,
  patch format, certificate records, and invalidation rules.
- Convert the current accepted workcell and the LLM hierarchy proposal into a
  golden spec without changing their claim boundaries.
- Add positive and negative fixtures for units, frames, missing evidence,
  dangling references, and authority escalation.

Gate: the golden fixture validates deterministically and no proposal-only field
is promoted beyond its current status.

### A1 — Deterministic MuJoCo compiler

- Compile `WorkcellSpec.v1` into the current repo-native MuJoCo representation.
- Preserve stable entity and joint identities.
- Emit a compile manifest binding every generated body, geom, joint, camera,
  sensor, and task region back to its source field.
- Add clean-runtime compile, settle, render, and finite-state tests.

Gate: round-tripping the golden workcell preserves the accepted scene summary
and existing task/evaluator identities.

### A2 — Scene diff and certificate invalidation

- Add typed create, update, move, reparent, articulate, and delete operations.
- Produce deterministic before/after diffs and rollback targets.
- Map field dependencies to certificate invalidation.
- Require explicit review for edits that raise authority or touch physical
  control assumptions.

Gate: a board-transform edit invalidates only the certificates that depend on
that transform and reruns reproducibly.

### A3 — Studio Author workspace

- Add the scene tree, structured viewport, 3DGS overlay, evidence inspector,
  unresolved-field list, edit diff, and certificate rail.
- Keep the current Replay product dominant for evidence review; Author is a
  separate route, not a replacement.
- Make every visual layer disclose its proof class and authority.

Gate: an operator can inspect any compiled MuJoCo object and trace it to the
exact spec field and evidence source.

### A4 — Governed agent editing

- Give the agent read-only inspection and typed patch proposal tools first.
- Validate, preview, and explain every patch before application.
- Add bounded automatic application only for fields whose policies permit it.
- Record model, prompt, tool calls, patch, and result hashes in the edit ledger.

Gate: the agent can execute a natural-language scene edit without directly
editing MuJoCo XML or silently widening authority.

### A5 — Task compiler and probe library

- Bind task objects, reset distributions, semantic regions, robot spawns,
  sensors, and evaluator contracts to the scene.
- Add priced deterministic probes for frames, reachability, camera visibility,
  articulation, collision, grasp/contact, and object response.
- Let the agent rank the next probe by expected information gain while the
  evaluator owns the verdict.

Gate: the scene can be accepted or rejected for one frozen pawn task with an
explicit reason and complete receipts.

### A6 — Evidence-gated scan-to-twin loop

- Ingest video, images, 3DGS, calibration observations, and measurements into the
  source registry.
- Preserve appearance and nonmetric observations while requesting the smallest
  useful set of metric anchors.
- Connect authoring failures to SAIL residual routing and TwinWorthiness.

Gate: one scan-derived candidate advances from visual proposal to a narrowly
certified task twin, or abstains with a predeclared blocking measurement.

### A7 — Export adapters

- Define a backend-neutral compiler interface and add USD and SDF only after the
  MuJoCo contract is stable.
- Compare articulation, transforms, mass/inertia, collision, and task entities
  across exported backends.
- Never describe cross-backend compilation as behavioral equivalence without a
  separate evaluator.

Gate: exported packages compile in their target backend and preserve a traceable
mapping to the same `WorkcellSpec.v1` source.

## First engineering issue

The first implementation issue should be:

> **A0: Define `WorkcellSpec.v1` and convert the current chess workcell into the
> golden authoring fixture.**

Acceptance criteria:

- a checked-in JSON Schema;
- one accepted-workcell fixture and one proposal-only fixture;
- deterministic validation with useful error paths;
- field evidence keyed by JSON Pointer;
- fail-closed authority validation;
- certificate dependency and invalidation records;
- tests proving that the existing LLM hierarchy remains visual/proposal-only;
- no change to current MuJoCo behavior, evaluator thresholds, evidence, or
  physical authority.

## Success metrics

The product should be measured on more than scene-generation latency or visual
appeal:

- time from input evidence to first compiling scene;
- fraction of task-relevant fields with explicit evidence and units;
- fraction of agent edits that validate and preserve unaffected certificates;
- compile and deterministic rerun rate;
- task-readiness pass rate and reason distribution;
- held-out replay residual and event prediction;
- policy consequence and ranking predictivity after TwinWorthiness admission;
- measurements saved by active probe selection;
- invalid-claim and silent-authority-escalation rate;
- operator time required to repair a rejected candidate.

The north-star metric is:

> **Time to a narrowly certified task twin, with zero silent authority
> escalation.**

## Product boundary

ClawStudio is not "Gizmo with more buttons." It is the inspectable bridge from
scene authoring to trusted robot learning:

```text
world proposal
  -> editable structured workcell
  -> evidence and uncertainty
  -> deterministic compilation
  -> task probes and replay
  -> evaluator-owned certificates
  -> admitted data and policy improvement
```

That is the version worth building because it compounds the project's existing
technical advantage instead of restarting as a generic 3D generation company.
