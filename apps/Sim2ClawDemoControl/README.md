# sim2claw Demo Control

A native four-button macOS controller for the loopback Studio demo:

- **Power On / Off** starts or stops the Studio server and opens or closes the
  `demo_physical` orchestrator session. During a running sequence, Power Off
  waits for the current guarded move to finish and torque to be released.
- **Inverse → Base** runs the six saved return traces.
- **Base → Inverse** runs the six saved forward traces.
- **Loop Back & Forth** runs the fixed five-minute, 12-move cycle.

Physical authority is closed by default. The app refuses to start its Studio
process unless the owner has explicitly set
`SIM2CLAW_ENABLE_PHYSICAL_DEMO=1`; the server then also requires the
`--enable-physical-demo` loopback-only gate. This opt-in does not verify task
success, promote a policy, or authorize unattended operation.

The app stops only the Studio process it launched. It never discovers or kills
an unrelated listener already using port 4173.

Build, test, package, and launch:

```bash
cd apps/Sim2ClawDemoControl
Scripts/compile_and_run.sh
```

The app discovers the containing sim2claw checkout automatically. Override it
with `SIM2CLAW_REPO_ROOT` or override the executable with `SIM2CLAW_UV_PATH`.
