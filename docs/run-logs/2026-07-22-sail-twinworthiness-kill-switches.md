# SAIL TwinWorthiness Kill-Switch Run Log

Date: 2026-07-22

Milestone: P1-14

The operational capability contract extends, but does not mutate, the frozen
P1-01 TwinWorthiness schema. Its contract SHA-256 is
`c03cf1b3115b79f60992286b92676d46bd8c938d2ab63fb10b1f143d4ef986f8`;
the envelope schema SHA-256 is
`1259016e7c9ad40b82ab9c348d25f9d966675532094ba8ca8f087c9c08053ba3`.
The deterministic campaign config SHA-256 is
`930896ea0f6e88e6399ad4733ef8a9d40fb9423ace1d071f37a42907467e524b`.

The current exact-scope envelope wraps retained certificate
`86799523c2b93aaa8cc08871f5d75f2ea5dedc2299f75d868cb2dbfcf54e4a3f`
at level `TW-REPLAY`. Envelope SHA-256 is
`aed30c62f08cd069ba946009be4290a1b96ba083134240c37d94f31cf37956f9`;
its canonical digest is
`eb38b8538a40bc8af5d3e99f2a5c6deda9cbb8ce967403ad271cf67442421537`.
Only diagnostics is allowed. Data generation fails TW-G2; policy selection,
physical canary, and motion fail TW-G2 through TW-G4, with physical paths also
requiring separate owner, gateway, workcell, protocol, and motion authority.

The report SHA-256 is
`db5f568fefbaf69d48507da480296301de3d147a76c79a7bf6c0fba29591357a`
with canonical digest
`a4502d0372c996575266b53097ded16dbbaba8ec687153d24c82f79ee55db56c`.
All seven negative scenarios deny capability. Synthetic selection and physical
certificates make every downstream software branch reachable while explicitly
carrying no real twin, data, policy, hardware, or transfer claim. GOLD-17,
GOLD-18, and GOLD-19 pass. Receipt SHA-256 is
`031f8b09f4f6555c0f0034aa3d10c11cbad0f7e5337c90d33ba25a5728c099b8`
with digest
`fd63f006eff36ea91428526fa702b650996fc1ead94daf71e52c050ddd8e3bc9`.

Focused validation passed 180 tests. The full real-component LF-00 through
LF-13 fixture passed in 122.41 seconds after its exact twin identity was
resolved and an evaluator-owned synthetic `TW-SELECTION` envelope was issued.
The final repository gate passed 757 tests plus 328 subtests with three
expected skips in 1,275.26 seconds. The canonical project contract binds the
final P1-14 `project_state.json` hash. No provider, training campaign,
hardware, Brev, new physical observation, or paid compute was used.
