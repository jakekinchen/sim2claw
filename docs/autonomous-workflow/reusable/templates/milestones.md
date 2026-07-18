# Autonomous Milestones

This file defines invariant milestones for autonomous work on this project.

Milestones are required outcomes, not detailed subtasks. The Executor and Reviewer choose the implementation slices needed to satisfy the next milestone.

## Overall Goal

<Describe the final world-state and golden path.>

## Milestone Rules

- Milestones are invariant outcomes, not task lists.
- Agents choose implementation slices needed to satisfy the next milestone.
- The Reviewer may not mark a milestone complete without running or recording its verification gate.
- The Manager challenges work that optimizes beyond the current milestone before the gate is satisfied.
- If a milestone gate proves wrong or incomplete, update this file.

## M0 - <Milestone Name>

**Required outcome:** <finished state>

**Why this is invariant:** <why the project cannot be done without it>

**Verification gate:**

```bash
<commands>
```

**Completion evidence:**

- <observable proof>
- <observable proof>
