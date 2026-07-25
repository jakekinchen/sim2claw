# Inspect Robots offline integration

Date: 2026-07-24

Branch implementation commit:
`0ade935f750c8a59b6d48ebcf05b446fc9d24823`

## Capability

Sim2Claw now has one optional, hardware-free Inspect Robots vertical slice. A
tracked deterministic fixture is exposed as an Inspect Robots Task, replay
Policy, and simulated Embodiment. The upstream runner performs compatibility
checking and writes its schema-v1 EvalLog; Sim2Claw then reloads the artifact
through the upstream API and validates the embedded Sim2Claw provenance.

The log retains:

- `top` / `overhead_workspace` and `wrist` / `wrist_gripper_upward` references;
- six-joint position and velocity observations in canonical SO-101 order;
- requested and applied vectors, per-action hashes, sequence hashes, and exact
  identity labels;
- `synthetic_deterministic_replay_compatibility`;
- `evaluator_admission:false`;
- `physical_authority:false`;
- the guarded `sim2claw.so101_physical_gateway.v2` identity with
  `gateway_invoked:false`.

No pixel payload is fabricated. No camera, simulator, serial device, servo,
gateway, provider, training, paid compute, or Brev resource was opened.

## Reproduction

```bash
uv run --extra inspect-robots sim2claw inspect-robots-offline \
  --output-dir runs/inspect_robots_offline
```

The final clean-HEAD confirmation used the same command with output directory
`runs/inspect_robots_offline/20260724-final`.

- EvalLog:
  `runs/inspect_robots_offline/20260724-final/sim2claw-offline-replay_47a4d039.json`
- EvalLog SHA-256:
  `5810921887a848c3d2cbfb0a208dd329ec6b3dd4533a0cfda56ab517dbb8302f`
- fixture SHA-256:
  `8987fcc02b5e3b425166013e07ae955251421e62ce3dc4aa401241b29ad5b23d`
- embedded Git commit:
  `0ade935f750c8a59b6d48ebcf05b446fc9d24823`
- result: schema v1, success, 3 transitions, exact requested/applied sequence,
  both camera roles, admission false, authority false, gateway not invoked

The generated EvalLog remains ignored by `.gitignore`.

## Verification

- `uv run --extra inspect-robots pytest -q
  tests/test_inspect_robots_adapter.py`:
  4 passed.
- Adapter plus exact recorder/Studio/video regression bracket:
  58 passed and 2 subtests passed in 6.57 seconds.
- Python compile check passed.
- `git diff --check` passed.
- Ruff is not installed in this worktree, so no Ruff result is claimed.

The behavior tests include an intentionally different applied action and prove
that requested/applied divergence survives EvalLog serialization. They also
prove that physical authority or evaluator admission in the offline fixture is
rejected before an output directory is created.

## Proof and adoption boundary

This result is synthetic compatibility proof only. Episode length checks
transport completeness; it is not task success. Twin fidelity remains 0/6 and
the strict task score remains 0/11.

Recommendation: keep Inspect Robots as an optional experimental harness for
offline/simulation comparisons, but do not make it Sim2Claw's main
task-policy-embodiment harness yet. The upstream API is alpha, and Sim2Claw
currently has to place its lossless step provenance in trial metadata.
Reconsider after API stability and one reviewed experiment proves lossless
recorder/Studio and evaluator-admission integration without weakening the
existing gateway or proof-class boundaries.
