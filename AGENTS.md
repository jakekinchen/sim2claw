# sim2claw Clean-Room Operating Rules

- Prior-project material is consulted read-only in the archive repository
  (`jakekinchen/sim2claw-imported-archive` @ `798491e`) or the local read-only
  checkout `/Users/kelly/Developer/sim-link`; freshly authored maps live at
  `docs/reference/ARCHIVE_INDEX.md` and `docs/reference/PRIOR_RESULTS_SUMMARY.md`.
  No file is copied into this repository, and nothing in the archive grants
  authority or proves a capability here.
- Do not copy implementation, scripts, configurations, generated artifacts,
  receipts, datasets, checkpoints, caches, virtual environments, or outputs
  from `sim2claw-imported-archive`.
- Build each component manually from reviewed requirements and upstream public
  dependencies. Record the source and reason for every adopted dependency.
- Keep fixture, synthetic, simulation, replay, learned-policy, physical
  read-only, and physical task evidence as separate proof classes.
- Freeze held-out scenes, seeds, and evaluator behavior before training.
  Training code never promotes itself.
- Prefer one explicit project runtime when the implementation begins. Mac MPS
  and NVIDIA CUDA may train differently; selection must use a separately owned
  CPU/fp32 evaluator.
- Use one reviewed gateway as the only future robot path. Documentation, shell
  access, and historical receipts never imply camera, serial, servo, or motion
  authority.
- Keep generated data, checkpoints, credentials, caches, observations,
  `outputs/`, and `runs/` out of Git.
- Any paid or Brev-backed compute must have a bounded task and must be stopped
  or deleted as soon as that task completes.
