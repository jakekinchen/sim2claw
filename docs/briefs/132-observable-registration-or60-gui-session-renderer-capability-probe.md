# OR60 — GUI-session renderer capability probe

Decision: `PROBE_ONCE_READ_ONLY`

Evidence anchor: `OR59`; runtime boundary: `OR57`

MuJoCo's installed macOS renderer requires a logged-in GUI context. Plain CGL,
the installed `mjpython` trampoline, and the Linux fallback are closed. Test
whether the approved Computer Use service can expose an existing Terminal
surface without typing or changing state.

## Required outcome

Request Terminal app state once. If the Computer Use service itself cannot
start, request app enumeration once to distinguish an app-name problem from a
global service failure. Pass only if Terminal state is observable.

## Frozen constraints

- Use the fully read Computer Use skill and its plugin-owned runtime only.
- At most one Terminal-state request and one app-enumeration request.
- Do not click, type, launch commands, accept permissions, change settings, or
  transmit data.
- Do not start a renderer, install dependencies, start Colima, or emit a
  candidate video.

## Terminal rule

If both calls return `Sky Computer Use service startup request failed`, close
the native GUI-session lane. The next safe capability probe is an already
installed WebGL/browser replay surface with no downloads.
