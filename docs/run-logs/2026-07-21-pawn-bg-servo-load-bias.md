# 2026-07-21 B--G servo load-bias and fidelity closeout

Commands:

```text
uv run --offline python scripts/run_pawn_bg_servo_load_bias.py
uv run --offline python scripts/run_pawn_bg_fidelity_advancement.py
```

The first command ran the frozen 63-candidate whole-episode CV campaign. It
selected a 1.5-degree shoulder-lift deadband, fold-specific 2.0--2.5-degree
elbow deadbands, and an elbow load-bias coefficient of -1.5. All source action
arrays retained their original float64 bytes, row order, and SHA-256.

The fold-selected pooled result reduces joint RMS from 1.2955577 to 1.2118497
degrees (6.461%) and EE RMS from 12.9364 to 11.3437 mm (12.312%). All four
validation folds improve. The second command replays only the already-selected
fold candidates, binds all 11 paired episode metrics, and performs a
deterministic 10,000-replicate whole-episode bootstrap with seed 21072026. The
joint-RMS relative-improvement 95% interval is 4.398--8.540%; every bootstrap
replicate improves, while 91.62% cross 5%.

Because all 11 episodes come from one retained acquisition session, this
bootstrap quantifies conditional episode variability only. It does not create
independent physical-session evidence.

The selected coefficient is the frozen grid's lower boundary. It is not an
identified physical parameter and the grid was not expanded after the result.

The strict consequence vector does not improve as a grasp result: contact
11/11, lift 1/11 versus 2/11, destination-inside 2/11 versus 0/11, and strict
success 0/11. Mean final target distance improves 38.466%, but the lift
regression prevents grasp or composite promotion.

Artifacts:

- `outputs/pawn_bg_servo_load_bias_v1/servo_load_bias_receipt.json`
- `outputs/pawn_bg_fidelity_advancement_v1/advancement_receipt.json`
- `outputs/pawn_bg_fidelity_advancement_v1/fidelity_advancement_summary.png`

No paid compute, Brev instance, robot motion, camera, serial device, network,
or physical authority was used.

Final focused verification: 4 tests passed in 9.25 seconds, including a live
source-backed regeneration of the advancement closeout. Targeted bytecode
compilation, JSON validation, and whitespace checks also passed. Ruff was not
available in the locked runtime and is not represented as executed.
