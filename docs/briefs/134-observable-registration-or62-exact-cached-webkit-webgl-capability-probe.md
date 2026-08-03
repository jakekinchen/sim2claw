# OR62 — Exact cached WebKit WebGL capability probe

Decision: `PROBE_ONCE_EXACT_CACHE`

Evidence anchor: `OR61`

System Chrome aborted before the blank page opened. The same installed
Playwright CLI exactly expects WebKit revision `2327`, and that revision is
already present locally. Test this distinct engine once with no download.

## Required outcome

Open the immutable OR61 blank probe with `--browser webkit`. If launch
succeeds, capture a snapshot, read the rendered result, and save one
screenshot. Pass only when the page reports a WebGL context and the screenshot
exists. Close the OR62 session afterward.

## Frozen constraints

- Bind cached CLI version `0.1.17`, Playwright
  `1.62.0-alpha-1783623505000`, WebKit revision `2327`, and the probe page.
- Exactly one launch. No system Chrome, Safari, existing-session attachment,
  network, cache population, install, or setting change.
- No scene mutation, physical composite/texture, candidate video, or target
  claim.

## Terminal rule

Failure closes the final local browser-engine route. Success opens a separate
WebGL scene-replay card; the blank context itself is not visual-target proof.
