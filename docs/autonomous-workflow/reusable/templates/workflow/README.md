# {{PROJECT_NAME}} Autonomous Workflow

This directory defines the autonomous Codex workflow for this repo. It is a repo-local operating system: file-backed plans, reviewable execution slices, explicit audit trails, and a thin Manager/Guardian role that gives the user one clean line of communication.

## Documents

1. [Operating Model](./01-operating-model.md) - workflow thesis, role topology, and source-of-truth rules.
2. [Role Contracts](./02-role-contracts.md) - Executor, Reviewer/Planner, Manager/Guardian, and human responsibilities.
3. [Planning System](./03-planning-system.md) - milestone plans, briefs, hot routing, and decision discipline.
4. [Execution Protocol](./04-execution-protocol.md) - slice lifecycle, TDD posture, review gates, and commits.
5. [DevOps and Session Ops](./05-devops-and-session-ops.md) - startup, audits, context, logs, and validation gates.
6. [Manager / Guardian Protocol](./06-manager-guardian-protocol.md) - how the third role protects momentum without becoming a message bus.
7. [Document and Artifact Map](./07-document-and-artifact-map.md) - canonical repo files and what each one owns.
8. [External Pattern Assessment](./08-external-pattern-assessment.md) - record what was adopted, deferred, or rejected from outside scaffolds.
9. [Autonomous Milestones](./09-autonomous-milestones.md) - invariant milestone gates for this project.

## One-Line Strategy

Run the project as a supervised Codex pair: the Executor ships one small verified slice, the Reviewer audits and steers the next slice, and the Manager/Guardian watches the whole loop for false blockers, stale plans, context risk, and optimization opportunities.
