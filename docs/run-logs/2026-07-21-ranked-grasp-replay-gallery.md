# Ranked pawn grasp replay gallery

Date: 2026-07-21

## Outcome

Studio now exposes a mobile-first, Three.js replay list for the seven strongest
episodes in the frozen V3 action-replay receipt. The selection retains all four
lift episodes and the three strongest qualified-pinch near misses. Four weaker
episodes are omitted from the visible gallery.

The ordering is transparent and consequence-first: strict success, lift plus
transport, retained-grasp lift, qualified bilateral contact, transport
progress, retention duration, rise, lower slip, lower target distance, and
lower collateral displacement.

| Rank | Move | Relative simulator outcome |
|---:|---|---|
| 1 | C2 to C1 | lift + transport; 60% targetward progress |
| 2 | E2 to E1 | retained-grasp lift; 42 mm rise; 48% progress |
| 3 | D2 to D1 | retained-grasp lift; 48 mm rise; 42% progress |
| 4 | F2 to F1 | retained-grasp lift; 43 mm rise; 10% progress |
| 5 | C1 to C2 | qualified-pinch near miss; 28 mm rise |
| 6 | E1 to E2 | qualified-pinch near miss; 27 mm rise |
| 7 | F1 to F2 | qualified-pinch near miss; 25 mm rise |

Every generated source replay has a 30 Hz MuJoCo body-state trace and a matching
scene manifest. For clean-clone and phone use, Studio ships deterministic 10 Hz
inspection derivatives plus exact phase boundaries and one shared compact scene
manifest. The 5.56 MB tracked bundle binds every source/derivative trace digest,
action hash, parameter digest, rank, metric, and evaluator consequence to the
frozen V3 receipt; the source actions remain unchanged.

## Reproduction

```bash
uv run python scripts/build_ranked_grasp_gallery.py
uv run sim2claw studio --host 0.0.0.0 --port 4173 --read-only --no-open
```

Open `/#/tasks/pawn_bg_ranked_grasp_v3` on the served Studio origin.

## Verification

- 18 focused tests plus 2 subtests passed after adding the tracked bundle.
- All seven catalog entries resolve as Three.js state traces.
- Every served trace revision matches the shared publication scene manifest.
- Static Studio, CSS, JavaScript, catalog, scene, and trace endpoints respond.
- Read-only Studio HTTP serving was exercised end to end.

## Claim boundary

The gallery is retained, action-frozen simulator inspection. No listed episode
is a strict task success. The ordering does not promote the V3 simulator, prove
policy improvement, or establish physical transfer.
