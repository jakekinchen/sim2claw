# 2026-07-20 retrospective publication gate

## Scope

Offline-only audit and artifact generation after retirement of the cloud
workspace. No robot, Brev, provider API, training, or physical motion was used.

## Evidence generated

- `runs/publication-gate/retrospective_publication_receipt.json`
- `runs/publication-gate/subscription-pilot/subscription_pilot_manifest.json`

These receipts are ignored because they bind the retained ignored physical
corpus. Their source contracts and deterministic generators are tracked.

## Observed inventory

- Physical episodes: 18
- Strict samples: 7,741
- Catalog-bound assets verified: 54/54
- Endpoint frames verified: 36/36
- Owner-accepted qualitative markers bound: 26/26
- Directed B--G skills represented: 12/12
- Strict sample semantics: 18/18
- Exact simulator replay eligible: 0/18

## Gate outcome

Passed:

- physical source integrity;
- real replay-anchor construction;
- strict sample semantics;
- diagnostic physical tracking posterior;
- descriptive qualitative image-offset fit;
- low-cost subscription-pilot specification freeze.

Blocked:

- metric endpoint calibration;
- exact simulator replay;
- geometry system identification;
- replay-based timing/control system identification;
- contact/object system identification;
- sim-to-real and physical-transfer claims;
- provider execution and spend.

## Verification

- Focused tests: `12 passed`.
- Full repository tests: `544 passed, 328 subtests passed`.
- Repeated receipt digests were byte-identical:
  - subscription-pilot manifest: `8aea5ec9cc28708220aff1ff0beb4a412276532bcec527a96da5ffa457c02efa`
  - publication receipt: `dbf78e330e8a1cdeb4afd8af894915f05a7e19ae612d9d854a6b881abd737959`
- All nine jobs are dry-run specifications with `authorized: false`.
- Subscription attempts: `6`; paid API attempts: `3`; retries: `0`.
- Frozen incremental-cost cap: `USD 1.00`.
- Local non-inference auth checks: Codex is logged in through ChatGPT and
  Claude Code is logged in through a Claude subscription.
- Exact GPT-5.6 Sol and Claude Fable 5 model entitlements remain untested to
  avoid consuming quota before execution authorization.
- `GROQ_API_KEY` is absent from the current process environment.
- Provider calls: `0`
- Physical motion: `0`
- Brev resources created or used: `0`

## Post-gate simulator trace extension

The later train-derived Stage-F board-pitch study adds a lower-error simulator
geometry result without changing the physical/publication blocks above. It
reduced train event RMS from 17.414 to 12.906 mm and reduced the two
already-open evaluator episodes from 23.549 to 16.097 mm. Mapped-encoder mean
source-approach error fell from 8.224 to 4.071 mm on train, with 11/11 episodes
within 10 mm.

The candidate failed the retained train contact/lift gates (contact 9/11 to
6/11; lift 1/11 to 0/11). It is therefore admitted only as the lower-error
geometry/trace hypothesis; Stage D remains the conservative physics-replay
candidate. See `docs/run-logs/2026-07-20-pawn-workcell-fit-v3.md` for receipts,
hashes, exploratory disclosure, and the post-selection confirmation boundary.
