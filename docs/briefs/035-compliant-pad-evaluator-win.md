# Brief 035: compliant-pad evaluator win

## Required outcome

Earn an evaluator-owned grasp-retention win without changing the recorded C2
action sequence or weakening any gate. A C2 winner must retain bilateral
contact through source index 401, remain within 0.5 degrees of the physical
loaded aperture, preserve lift-and-transport, and reduce post-grasp slip by at
least 10%. It must then pass the declared three-sentinel regression gate before
any all-eleven evaluation or simulator-promotion claim.

## Mechanism

Replace the decorative rigid rubber sleeve with three independently moving
contact segments on each finger. Each segment is attached to its jaw by a
bounded slide joint along the local contact normal and has an explicit spring,
damper, travel limit, and small modeled mass. The family tests 1--3 mm travel,
500--2,000 N/m segment stiffness, and two bounded load-force responses. These
are simulator sensitivity priors, not physical rubber calibration.

The underlying rigid jaw primitives are collision-disabled in this family so
the evaluator cannot credit a result in which rigid plastic carries the pawn.
The existing experimental contact-triggered command hold is disabled because
it mutates the simulator actuator transfer rather than modeling the cap.

## Execution gates

1. Freeze the source bindings, 18 candidates, acceptance vector, budgets, and
   stop rules before opening a C2 result.
2. Unit-test body, joint, range, stiffness, damping, mass, and legacy no-op
   behavior.
3. Run or safely resume all 18 C2 replays and reject any action/hash drift.
4. Advance at most four actual C2 passes to the three named sentinels.
5. Freeze at most one composite for all-eleven retrospective regression.
6. Publish receipts and a clear physical-versus-simulator claim boundary.

## Non-authority

No new physical observation, robot motion, policy training, paid compute,
physical parameter identification, or physical-transfer claim is authorized.
