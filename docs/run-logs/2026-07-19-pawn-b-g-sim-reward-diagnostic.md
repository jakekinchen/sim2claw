# B-G pawn simulation reward and demonstration replay diagnostic

Date: 2026-07-19 America/Chicago

## Outcome

The frozen 12-skill B-G product question now has an executable simulation
reward and manipulation gate contract. The current owner-reviewed source
commands were replayed in the current 100 mm sparse-pawn workcell under nominal,
low, midpoint, and high rubber-tip contact settings.

The result is terminal-negative: all 52 episode/variant runs fail to lift or
contact the selected pawn and finish one square (`0.04445 m`) from the target.
This exposes a command/scene compatibility gap before contact-friction
sensitivity becomes relevant. It is not an ACT checkpoint result and does not
measure or seal the sim-to-real gap.

No hardware, camera, serial bus, gateway, network research, held-out physical
data, training, Brev, paid compute, or physical motion was used.

## Frozen identities

- product contract:
  `configs/evaluations/pawn_rank12_bidirectional_v2.json`
- product contract SHA-256:
  `8e5a351421dc222688e3ad0cfc7e0c14023352e3ee7132e02c26290d0a7f96f3`
- language contract SHA-256:
  `8e1b1a863b02ce6f8ff2d446bfceda4202d35eb5e6346eb1988cf759b61eed8c`
- simulation reward contract:
  `configs/evaluations/pawn_bg_sim_reward_v1.json`
- simulation reward contract SHA-256:
  `e702ad7fa3a366bc24c552c4cd0e5df66842d5fe7f6ef824266b8cfb2ee8d0c7`
- physical catalog SHA-256:
  `7eb770b5be222ef970b97e1c1128f604121d324bb573672b9f8ef9b40a36a15e`
- contact-prior canonical SHA-256:
  `e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499`
- deterministic seed: `190719`
- frozen order: B1→B2, B2→B1 through G1→G2, G2→G1

The rubber-tip values are the same explicitly unmeasured prior ensemble used by
the earlier rook sensitivity analysis. Reuse here is marked as a cross-task
parameter diagnostic; the rook policy/evaluator binding is not transferred to
the pawn task. Rubber mass is not modeled. Physical rubber mass is nonzero and
unmeasured but intentionally approximated as zero in dynamics.

## Data used

The diagnostic reads 13 owner-reviewed product-scope physical teleoperation
recordings read-only from the canonical checkout. They contain 5,562 rows of
20 Hz six-joint follower command/actual values and cover all 12 directed B-G
rank-1/rank-2 skills; C2→C1 has two accepted recordings. Folder transitions
are used as the owner-reviewed task labels, while catalog/receipt conflicts
remain preserved.

These rows are human-owned source demonstration candidates, not ACT policy
weights and not admitted ACT training rows. They contain no measured pawn pose,
end-effector pose, contact, grasp, or release trajectory. Their physical-to-sim
joint transform remains provisional.

The strict system-identification input audit verified all 54 catalog assets but
rejected replay/training admission:

- `2,255 / 7,741` measured rows exceed current simulator limits;
- `2,231 / 7,741` command rows exceed current simulator limits;
- maximum measured exceedance: `0.12351556059700508` simulator units;
- maximum command exceedance: `0.11584378366516201` simulator units;
- joint/timing replay ready: `0 / 18` recordings;
- geometry/contact observable readiness: `0 / 18` recordings.

Strict audit receipt SHA-256:
`2e00b2c9e0a02538af7c1c9018e8e62d61aeb2a615cb5c6dd3b26c041ed936c9`.

## Reward and hard gates

The scalar reward is a bounded diagnostic shaped from destination progress,
lift progress, centering, uprightness, settled state, and release, with
penalties for no selected-piece contact, wrong-piece contact, collateral
displacement, and non-finite state. It has no promotion authority.

Hard gates own pass/fail:

- rise at least `0.04 m`;
- whole pawn base inside target: center error at most `0.008425 m`;
- composable center error at most `0.006 m`;
- precision center error reported at `0.003 m`;
- final upright cosine at least `0.95`;
- final linear speed at most `0.02 m/s`;
- selected-piece jaw contact must occur and be released before terminal;
- no robot contact with a wrong piece;
- other-piece displacement at most `0.006 m`;
- finite state throughout.

For learned-policy mode, model-owned actions and zero assistance are additional
gates. Source-demonstration replay can report task consequences only and can
never report policy success.

## Replay method and admissibility

Each recording resets the matching brown pawn to its owner-reviewed folder
source square, initializes the left simulated SO-101 from the first measured
follower state, converts physical degrees/gripper percentage using the existing
provisional adapter, and applies the recorded commands at source timing. The
diagnostic clips commands to MuJoCo actuator limits so it can reveal behavior;
this makes it explicitly non-admissible for policy evaluation or training.

All 13 recordings required clipping in every variant. In the nominal pass,
1,558 of 5,562 command rows were clipped and 1,588 measured-state row checks
were outside current simulator limits (the latter includes the explicit first
initialization check). No clipped trajectory is promoted or admitted.

## Results

| Variant | Episodes | Task successes | Mean reward | Mean final target error | Maximum rise |
|---|---:|---:|---:|---:|---:|
| nominal uncalibrated | 13 | 0 | 0.1000001991 | 0.0444499994 m | 0.0000001403 m |
| rubber-tip low prior | 13 | 0 | 0.1000001991 | 0.0444499994 m | 0.0000001403 m |
| rubber-tip midpoint prior | 13 | 0 | 0.1000001991 | 0.0444499994 m | 0.0000001403 m |
| rubber-tip high prior | 13 | 0 | 0.1000001991 | 0.0444499994 m | 0.0000001403 m |

Every nominal episode remained finite, upright, settled, released, and within
the collateral/wrong-contact limits because no manipulation occurred. Every
episode failed selected-piece contact, minimum lift, whole-base-inside,
composable-center, and precision-center gates. No selected-piece jaw contact
occurred in any nominal episode.

The identical outcome across rubber-tip variants is not evidence that rubber
contact is irrelevant. The added tip geometry was never exercised. The only
supported sensitivity statement is: this replay failure is insensitive to the
declared contact prior because it fails before pawn contact.

Compiled variant identities:

| Variant | Variant SHA-256 | Compiled dynamics SHA-256 |
|---|---|---|
| nominal | `89f3c21e19f8bffc9f8391bb2b7ee089765f698fe38de93ba7fc4cac3f5c3869` | `8fc659cc2b2efbd13d7efbdbcafb26b71f5c794b775ffe94134adc15ee64a2b6` |
| low | `cac9ef7043ba66589c72ff391459902537a79462fb5b3e388b86d08f20cf421d` | `9e5959ca70c5ab4e70cae45249c613e074c5c05e9e19a5a48aa543c88463aaae` |
| midpoint | `fff57bff4ec9857cbcea4e254b26fd06472535ff0c159b11543162ac4f88ca14` | `1429a89a4864c1fc76441ac7866a896b9b642ebb6b0b0ec884814848e3a2bfc8` |
| high | `a47d0055e548211a497e4b876055a91ddae18723c34700ce27ee1a0b18df9ad6` | `bdf2df34e4f8102ce168ad8fb03e419efa954d2cc261c313637253bade15ac1d` |

All variants share inertial/control SHA-256
`16027c4eaefe602d3f4e8b288052dc4e144062cf3d64e55280caf9c522a27fdc`
and total compiled body mass `321.2782842253627 kg`. Body mass, COM, inertia,
joint/DOF, actuator, and nominal dynamics identities remain unchanged except
for the intended zero-mass collision/contact geom arrays.

## Additional simulated expert probe

The existing geometric expert was also probed against the 12 B-G mappings in
the sparse scene without changing its `3 mm` IK admission threshold. It
produced zero episodes. Initial IK residuals ranged from `0.011754 m` to
`0.083800 m`, so all cases failed before action generation. This is a
capability diagnostic, not a policy or training result.

Probe receipt SHA-256:
`8a34bc90f51ad53b3398c9b529157a6998c0d0112804587a03eb62643a48ed03`.

## ACT policy status

No compatible B-G pawn ACT checkpoint exists locally. The only accepted ACT
checkpoint is the separately documented narrow `chess_rook_lift_v1` artifact;
it is not evaluated or relabeled here. Therefore:

- B-G task consequence diagnostic: available and terminal-negative;
- B-G learned ACT policy result: unavailable;
- B-G checkpoint compatibility: false/no compatible checkpoint;
- training readiness from these physical rows: rejected;
- physical or sim-to-real claim: unavailable.

## Receipts and verification

- ignored replay receipt:
  `outputs/pawn_bg_act_v1/pawn_bg_demo_sim_contact_sensitivity_v1.json`
- replay receipt SHA-256:
  `35069882d3870278ee59836b5d70f2c8cc79c9ea85231ac194962a5b54114967`
- focused reward/replay/contact tests: `24 passed, 254 subtests passed`
- full suite: `388 passed, 306 subtests passed` in `20.85 s`
- `uv lock --check`: passed
- source distribution and wheel: built successfully
- `git diff --check`: passed

The full-suite run initially exposed a stale Studio scene revision pin left by
the repository's MuJoCo 3.10.0 upgrade. The deterministic current manifest was
`c17fb371...`; its test still expected the pre-upgrade `ddee05c5...`. The pin
was updated without changing scene construction or runtime physics, and the
full suite then passed.

## Independent proof-wording review

Accepted wording is limited to the reward contract, exact source-command
diagnostic, terminal-negative simulated outcomes, contact-prior non-sensitivity
before contact, and lack of a compatible B-G ACT checkpoint.

Rejected wording includes complete sim-to-real closure, physical calibration,
validated rubber properties, ACT policy success, B-G learned skill, training
admission, physical replay equivalence, language generalization, composability,
transfer, or physical authority. Closing the next gap requires a reviewed
physical-to-sim joint transform plus synchronized measured object/contact
trajectories, followed by a separately frozen train/evaluation split and a
compatible B-G policy checkpoint.
