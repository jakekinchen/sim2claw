# Decision 0013 - Keep Inspect Robots as an optional offline harness

Status: accepted experimental integration

Date: 2026-07-24

## Source

- Official upstream: <https://github.com/robocurve/inspect-robots>
- Adopted release/tag: `v0.22.0`
- Exact upstream commit:
  `8bdc2a42b74dd5aa1c073bfa9dfa2a11605db75f`
- Package index: <https://pypi.org/project/inspect-robots/0.22.0/>
- PyPI source-distribution SHA-256:
  `f6563e46ff7eaf497a1f4b96697de36a673c4b0a449df53e6be35abbde9be332`
- License: MIT

The public repository and the published artifact were inspected read-only.
No upstream implementation, fixture, or generated artifact was copied into
Sim2Claw.

## Decision

Pin `inspect-robots==0.22.0` behind the `inspect-robots` optional dependency.
Use only its public Task, Policy, Embodiment, Observation/Action, rollout, JSON
sink, and EvalLog interfaces. Sim2Claw supplies a small deterministic replay
policy and simulated embodiment that preserve its own canonical two-camera,
joint-order, action-identity, proof, admission, and gateway-authority facts in
upstream-supported trial metadata.

The upstream runner owns component compatibility, rollout, scoring, and
schema-v1 EvalLog serialization. Sim2Claw owns validation of the embedded
Sim2Claw provenance. No physical gateway class is constructed and no camera,
serial, servo, simulator, provider, training, or paid-compute path is opened.

## Reason

This is the narrowest runnable seam that tests whether Inspect Robots can carry
Sim2Claw task-policy-embodiment evidence without replacing existing task,
action, recorder, gateway, or evaluator contracts. Pinning is required because
the upstream project labels itself alpha and explicitly recommends exact
versions while its API evolves.

## Promotion boundary

The result is synthetic deterministic replay compatibility only:

- `evaluator_admission:false`
- `physical_authority:false`
- task success is not scored or claimed
- camera values are references, not captured pixels
- episode length is a transport check, not a robotics metric

Keep the dependency optional and do not make Inspect Robots the main Sim2Claw
harness yet. Reconsider only after its alpha API demonstrates release stability
and a reviewed experiment shows lossless step-level recorder/Studio provenance
and evaluator admission without packing Sim2Claw facts into trial metadata.
