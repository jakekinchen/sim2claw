# Manager Log 001 - groot n17 brev budget

**Date:** 2026-07-18

## Trigger

User authorized an overnight Brev campaign with an absolute $50 maximum.

## Evidence Read

Authenticated empty inventory, GPU search pricing, official N1.7 hardware
recommendations, prior A100/EGL teardown evidence, and project cost rules.

## Diagnosis

One A100-80GB is the lowest-risk fine-tuning target already proven in this
workflow. At `$1.656/hour`, 00:32--08:30 CDT projects to `$13.248`; a second
instance is unnecessary and would complicate the hard cap.

## Intervention

Freeze one worker, no fallback provider chain, no automatic retry instance,
08:30 CDT wall-clock cutoff, `$50` absolute cutoff, and deletion immediately
after selected artifacts are preserved.

## User-Facing Impact

Expected overnight spend is about $13.25 raw compute and conservatively under
$20 including setup/transfer time, not the full authorized amount.

## Follow-Up

Log provision/delete timestamps and recompute exact projected spend before each
training extension. Poll authenticated inventory after deletion settles.
