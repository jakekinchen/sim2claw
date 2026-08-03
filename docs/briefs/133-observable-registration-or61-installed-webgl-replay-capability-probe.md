# OR61 — Installed WebGL replay capability probe

Decision: `PROBE_NO_DOWNLOAD`

Evidence anchor: `OR60`

All native MuJoCo renderer routes are closed. Inventory the machine and
repository for an already installed Playwright/browser/WebGL path. A browser
or package download is forbidden because the host is below `1 GiB` free and a
download would widen the frozen environment.

## Required outcome

Verify `npx`, Playwright CLI/package presence, browser binaries, Playwright
browser caches, and existing repository WebGL/Three.js assets. Only if a
complete installed path exists, launch one local blank page and record WebGL
vendor/renderer plus screenshot capability.

## Frozen constraints

- Follow the fully read Playwright skill, but do not invoke its `npx` wrapper
  unless `@playwright/cli` and a compatible browser are already local.
- No network, `npm`/`npx` cache population, package install, browser install,
  Homebrew, Colima, or system-setting change.
- No scene change, physical composite/texture, candidate video, or target
  claim.

## Terminal rule

Pass only with an actual local WebGL context and screenshot. Otherwise close
the WebGL lane and continue with renderer-independent scene-specification work
derived from OR59.
