# Decision 0003: GR00T N1.7 Dynamic Chess Boundary

Status: accepted for the first sparse-board VLA campaign

Date: 2026-07-18 America/Chicago

## Decision

Use NVIDIA Isaac GR00T N1.7 as a separate VLA lane. Pin the public code to tag
`n1.7-release`, commit `23ace64f17aa5015259b8609d371eb61a357c776`, and the
base checkpoint to `nvidia/GR00T-N1.7-3B`. Register the simulated SO-101 as
`NEW_EMBODIMENT` with one RGB workcell view, six joint positions, six absolute
joint targets, and natural-language chess commands.

The first curriculum keeps the black rook and black king visible and parks all
other pieces at reset. This follows a measured full-board negative: the existing
side-pinch path could move the target successfully while knocking the black
queen off the board. Sparse-board success is not full-board success.

## Adopted dependencies

| Dependency | Pin/source | Reason | License/notes |
| --- | --- | --- | --- |
| Isaac-GR00T code | NVIDIA commit `23ace64f...` | Official N1.7 data, post-training, policy, and server behavior | Apache-2.0 source; executed remotely, not vendored |
| GR00T N1.7 3B weights | `nvidia/GR00T-N1.7-3B` | Vision-language-action base for custom embodiment post-training | NVIDIA Open Model License; ignored external cache |
| Cosmos Reason2 2B weights | `nvidia/Cosmos-Reason2-2B` as resolved by N1.7 | Required language/vision backbone dependency discovered during model construction | Gated Hugging Face access; human acceptance required before paid compute |
| PyArrow | 23.0.1 from PyPI | Write typed LeRobot v2 parquet episodes locally | Apache-2.0 |
| FFmpeg | host package | Encode synchronized RGB episodes as H.264 MP4 | External executable; version captured in run evidence |
| Brev A100-80GB | `massedcompute_A100_sxm4_80G_DGX` at quoted `$1.656/hour` | Bounded CUDA fine-tuning and policy serving | Paid ephemeral compute; delete after campaign |

## Reward and evaluation

The dense reward combines lift progress, destination proximity, release,
uprightness, and settled state. It can prioritize curriculum/counterexamples but
has no promotion authority. A separate consequence evaluator owns success and
is frozen before training.

## Consequences

- ACT remains the verified narrow state-policy baseline; it is not silently
  relabeled as a VLA.
- Held-out task cases contribute zero training rows.
- Training, open-loop loss, or reward improvement cannot promote a checkpoint.
- This campaign grants no physical camera, serial, gateway, or motion authority.
- The historical `sim-link` repository supplied guidance only; no file or
  implementation was copied.
- A local access preflight must verify both GR00T and Cosmos before future paid
  provisioning. A valid Hugging Face token without gated-model access is a
  blocker, not authorization to accept terms automatically.
