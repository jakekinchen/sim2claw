# Dual-Camera Nested Lifecycle Terminal Negative

Date: 2026-07-24

Proof class: `stationary_nested_dual_camera_lifecycle_container_health`

## Scope

This transaction tested one production camera-lifecycle mechanism after the
sealed D405 campaign localized repeatable C922 container gaps to D405 open and
close/finalization boundaries. It changed physical dual-camera recording to:

1. start D405;
2. start C922;
3. retain both through a ten-second common window;
4. stop and finalize C922;
5. stop and finalize D405.

It did not move a robot, open a gateway, replay a simulator, call a provider,
train, promote, change a task score, claim metric depth, or claim synchronized
camera exposures.

## Frozen identities

- preregistration commit: `75bcbd65e0053b93a2d05cf1764306ea30f64569`
- implementation/execution commit:
  `e3affd41b77530634ca3fe991cdb4d1d036590ef`
- implementation tree:
  `fbc147d5a78fe3572ca4ce961ef6c5fb6d821f89`
- contract SHA-256:
  `5e97a27deaf6b874dee070ae1e6db3b81d68e4c8f9a9681ced9484e4b77fa363`
- runner/evaluator SHA-256:
  `89cfd1caf941a1808c220515efa92ffdd3899e24c0d70f264e9fb04f533f0e3c`
- overhead recorder SHA-256:
  `2947f472c03a5a51fc2abc66b56a0a61eccf1db6b8944230b2783de47d2b9a6e`
- teleoperation integration SHA-256:
  `f89d756d8b99a62aef7ba2c0d21051bf6c5c3b634debc9d9507c2201bfc2764f`
- HIL integration SHA-256:
  `fae3573610d8adbab8ccd25bf01b5550376fbd08bbc2c5e1c063070a6df4546f`
- FFmpeg SHA-256:
  `0a96da2735695308d964e25fa6f4a0db2e9d24031390360f4c5ff96a4f8938e5`
- FFprobe SHA-256:
  `68447e67105534f3f43b95c94983ed56fbdd7125e5724cc56499ad538c2b86a7`

The exact C922 and D405 AVFoundation names, model IDs, and unique IDs matched
the preregistration before the session. No competing capture process existed.

## Verification before device access

- focused lifecycle/recorder/timing/D405/teleop/HIL tests: `48 passed`
- Python compilation: passed
- JSON validation: passed
- `git diff --check`: passed
- worktree: clean

The first shell used the user-local Python without pytest and returned
`No module named pytest`; it opened no camera and is excluded from test proof.
The locked `.venv` runtime produced the reported passing results.

## One-session result

Budget:

- attempts: `1 / 1`
- D405 sessions: `1 / 1`
- C922 sessions: `1 / 1`
- retries: `0`
- replacements: `0`
- robot motions: `0`
- simulator replays: `0`
- provider calls: `0`

The common wall-clock window was `10.007981666945852 s`. Both recorder reports
completed with return code zero and stdin-`q` shutdown.

| Stream | Frames | PTS span | Maximum interval | Inferred missing intervals | Evaluator |
| --- | ---: | ---: | ---: | ---: | --- |
| C922 overhead | 314 | 10.433333 s | 0.033334 s | 0 | passed |
| D405 wrist | 63 | 12.8 s | 0.600000 s | 2 | failed |

The D405's only large interval was PTS `11.6 -> 12.2 s`. Its reported
common-window stop offset was `12.055563499918208 s`, and the C922 stop request
occurred at the same wall-clock boundary. This is diagnostic alignment between
container and recorder clocks, not an exposure-time or synchronized-device
measurement.

The independent evaluator returned
`reject_stationary_nested_dual_camera_lifecycle`. No inferred gap was observed
in this C922 container, but a strict D405 gap remained near the reverse
lifecycle boundary. The one-attempt family is exhausted; changing the threshold
or retrying would be post-hoc.

## Content-addressed evidence

- raw campaign:
  `093dd71de8cf79db6e84fa8b1cb1a444552cd7ffc4c849b21b2f98afbd01a8f3`
- raw event:
  `f873b8698cb7a0ac71b548daedb9cde7a6f146e6c2d0b0662dc16b99550b3995`
- C922 MP4:
  `47c4d564aebf6249f1a27a49711ebc66ce0b47091312da947df78028eb004b9c`
- D405 Matroska:
  `0553db5f04327a57ea9eb838b92cd18c0c0f75580fdbdd3eb3dae8c0113d932f`
- evaluation file:
  `bfad64080564a446f6c93b1e7c1b17fc1256a3a6b265aff11e6d72a95ba78f8b`
- evaluation digest:
  `922190e325640a3e86773223f716b2d2f972f342e87cd10b7bf2561bb1a844d2`
- receipt file:
  `d066fa146f4a19042686b932c7d0397f1aa2e7bfe2e163bc43b6b0353b5e17f0`
- receipt digest:
  `4e37b6b1783bc3382bf461928520e3fc0622ce0cd10c3299b39e283737b6df23`

All generated media and evaluation outputs remain ignored. Durable Git history
contains only code, tests, contracts, state, logs, and content digests.

## Post-terminal retry lock and re-verification

Read-only review found that the exact observed runner rejected an existing
output path but could be called with another path. The actual accounting and
raw evidence still prove one session only, but that was insufficient
control-plane enforcement. Closeout therefore adds:

- a separate canonical control wrapper, SHA-256
  `2be071844ff98e8ebef74c281803fd0b3e9de88bf6685e312bb1190eb1796454`;
- a tracked exhausted-family guard, SHA-256
  `8b753d2477d84eabfa4bdf269ed7363f8fa56791741a0ccc6c816eb83e7275ed`;
- direct `execute_hil_packet` start/stop and second-camera-failure cleanup
  tests.

The wrapper checks the terminal guard before delegating to any runner, so both
canonical and arbitrary output paths now fail before device access. The
observed runner/evaluator file was deliberately left byte-identical at
`89cfd1ca...`; it remains reproducible independently of the new control-plane
lock.

The final focused slice is `61 passed`. One no-camera re-evaluation into a new
temporary child directory reproduced evaluation `bfad6408...` and receipt
`d066fa14...` byte-identically. An earlier verification command pointed the
evaluator at the already-created temporary parent directory and was rejected
by the existing-output guard before producing files; it is excluded from proof.

## Decision

This is a useful localization result but not a camera qualification pass. A
future transaction must avoid independent camera lifecycle transitions during
the measurement—through a reviewed native common-session mechanism or an
isolated camera host—before bounded motion qualification. The independently
observed motion-correlated D405 cable/connector/strain-relief risk also remains.

Twin fidelity remains `0 / 6`: geometry/scale missing; kinematics partial;
action/timing partial; contact/compliance missing; actuator/load path partial;
task/EE consequence failed.
