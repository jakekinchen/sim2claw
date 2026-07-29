# Executor log 065 — proxy-collision V2 quarantine and V3 freeze

V2 produced `104` files totaling `125545280` bytes, then raised before writing
its summary receipt because the compact adapter lacked `dumps`. No outcome
file was parsed. The directory is retained under aggregate SHA-256
`8f9b470d...` as non-admissible audit material.

V3 supplies only the serializer pass-through and binds the V2 closeout.
Focused tests: `2 passed`; compilation and `git diff --check` passed. V3 output
is absent. No physical surface was opened.
