# Session 083 — Realized-Action C5 Contact Negative

Date: `2026-07-29`

Decision: `TERMINAL_C5_NEGATIVE_ACTIVATE_C6`

## Result

The frozen fit and validation cohorts contain zero episodes with per-sample
contact state, metric object pose path, metric robot/jaw pose path, known
applied force, metric contact deformation, or metric object orientation path.
All five preregistered candidate dimensions are therefore ineligible.

No jaw geometry, contact height, friction, compliance/damping, mass/CoM, or
grasp abstraction was fit. Motor current and observed grasp markers were not
relabelled as force/contact. The current MuJoCo defaults remain an unvalidated
diagnostic baseline.

## Evidence

Generated ignored receipt:

- file: `outputs/realized_action_contact_identifiability_v1/receipt.json`;
- file SHA-256:
  `e676ab052a00ae30009d22c6f842a1ed7c71b99cd1a4987fb683fa4503c5d1c9`;
- artifact SHA-256:
  `6a904ef2231f634a65661778afd59ec5e901204386d7dfeee85a05d574961692`.

Two builds were byte-identical.

## Boundary

C6 may run once against the baseline to expose its outcome, but cannot promote
that outcome through a validated contact model. C6 is active.
