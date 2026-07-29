# Executor log 063 — contact-witness result and proxy-collision freeze

The immutable witness completed over four exact actions and two unchanged
plant paths. First contact precedes rise on all eight paths. Six first contacts
hit the pawn upper sphere near `50.3--50.5 mm`; the other two hit the neck near
`32.7 mm`. Peak rise spans `4.1626--14.4543 mm`.

The witness's `support_contact_steps` field counts matching contact records,
not unique substeps. Its closeout excludes that field from all decisions. The
first-contact row, motion/rise row, pair, position, height, normal, force, and
peak-rise fields are unaffected.

The frozen challenger changes one model-semantic switch: three high-detail
left-jaw collision meshes become non-colliding, while named jaw primitives
remain active. No parameter is fit. All action and evaluator inputs are bound
to the preserved baseline.

Focused tests before execution: `6 passed`; Python compilation and
`git diff --check` passed. The immutable challenger output remains absent. No
camera, gateway, serial, torque, physical motion, or task attempt occurred.
