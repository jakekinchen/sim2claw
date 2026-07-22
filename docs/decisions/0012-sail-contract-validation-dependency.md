# Decision 0012 - Use JSON Schema for SAIL contracts

Status: accepted

Date: 2026-07-21

## Decision

Adopt `jsonschema==4.26.0` as a direct runtime dependency for Draft 2020-12
validation of the five SAIL v1 contracts.

## Source

- Upstream project: <https://github.com/python-jsonschema/jsonschema>
- Package index: <https://pypi.org/project/jsonschema/4.26.0/>

## Reason

The program needs standards-compliant rejection of malformed, incomplete, and
authority-violating evidence before fitting or certification. Reusing the
established upstream validator is smaller and safer than implementing a partial
JSON Schema engine in this repository. The dependency validates authored
contracts only; it does not grant evidence, evaluator, training, provider, or
hardware authority.

## Rejected alternatives

- Hand-written per-contract shape checks: easy to drift from the tracked
  schemas and likely to implement only a subset of Draft 2020-12.
- A database or probabilistic-programming framework: unnecessary for typed
  validation and contrary to the v1 dependency boundary.
