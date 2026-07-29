# Fable RP02A Stall Unblock

Date: `2026-07-29`

Mode: targeted read-only blocker consult in the existing Fable 5 thread.

## Evidence supplied

- V1 stopped before motion on a zero-elapsed changed target.
- V2 changed only the exact anchor/clock lead, passed `42` focused tests,
  and executed without rate limiting or clamping.
- The physical elbow moved from `99.472527` to `94.901099 deg`, then the
  reviewed gateway stopped after `5 s` without measurable progress.
- Plateau telemetry showed elbow `Present_Current` of approximately
  `16--23` raw, `Present_Load` `192`, and temperature `29 C`.
- Torque-off postflight passed; the elbow returned to `103.428571 deg`.
- The frozen route certificate has `0/48` eligible families at `95 deg` and
  two at `93 deg`, one per direction.

## Targeted verdict

Fable selected a no-configuration-write command-space torque mechanism over
seed reconfiguration, EEPROM gain changes, or outcome-informed task-family
redesign.

The mechanism uses a deeper requested elbow setpoint to preserve proportional
torque against gravity while keeping the observed elbow in the already passing
`88--93 deg` task band. It recommended:

- extend the motion-free corridor preview downward to `80 deg`;
- start with a requested floor of `86 deg`;
- allow one prospective deepening to `82 deg` after bounded no-progress;
- keep exact gateway timing and all existing camera, held-joint, stall,
  collision, cleanup, authorization, and one-execution gates;
- stop on elbow current above `150` raw sustained for `1 s` or temperature
  above `45 C`;
- do not write servo gains or any configuration register.

Fable ranked shoulder/pan/wrist seed reconfiguration as fallback two and an
explicitly owner-amended EEPROM write/verify/restore protocol as fallback
three. It found no current evidence justifying a configuration write.

## Independent reconciliation

The repository writer independently re-ran the current calibrated/registered
MuJoCo contact sweep using the exact V2 torque-off posture.

- `[80.0, 99.6] deg` is contact-free.
- The live `103.428571 deg` model posture contains three, not two, baseline
  representation contact pairs:
  `left_lower_arm/left_shoulder`,
  `left_shoulder/left_wrist`, and
  `left_upper_arm/left_wrist`.
- Fable's suggested `104.5 deg` upper preview bound worsens the deepest
  baseline penetration by more than `0.5 mm`, so it is not adopted.
- The prospective preview instead ends at `103.5 deg`; it allows only those
  exact live-anchor pairs above `99.6 deg`, with no more than `0.5 mm`
  additional modeled penetration. Every other pair remains forbidden.

This advisory is not physical authority, task evidence, transfer evidence,
mapping approval, simulator promotion, or permission to weaken any evidence
gate.
