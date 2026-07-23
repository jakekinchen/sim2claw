# sim2claw Demo Control

A native four-button macOS controller for the loopback Studio demo:

- **Power On / Off** starts or stops the Studio server and opens or closes the
  `demo_physical` orchestrator session. During a running sequence, Power Off
  waits for the current guarded move to finish and torque to be released.
- **Inverse → Base** runs the six saved return traces.
- **Base → Inverse** runs the six saved forward traces.
- **Loop Back & Forth** runs the fixed five-minute, 12-move cycle.

Build, test, package, and launch:

```bash
cd apps/Sim2ClawDemoControl
Scripts/compile_and_run.sh
```

The app discovers the containing sim2claw checkout automatically. Override it
with `SIM2CLAW_REPO_ROOT` or override the executable with `SIM2CLAW_UV_PATH`.
