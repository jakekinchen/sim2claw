# OR80 native full-mesh development timeline

OR80 rendered all 423 frozen development samples with the exact OR78 full-mesh construction and OR79 byte-equivalent native depth rasterizer. It kept the OR73 camera, zero time offset, identity appearance, OR74 metrics and gates, and the four OR72 development episodes unchanged.

Five of six metric gates pass. Pooled mean similarity is `0.803497`, p10 is `0.791074`, motion-union mean is `0.767238`, every episode mean is at least `0.800720`, and every phase mean is at least `0.794044`. Tolerant-edge F1 is `0.297679`, leaving `0.102321` to the `0.40` gate.

The four candidate videos visually expose why the scalar mean alone is insufficient: large neutral regions dominate the linear-pixel score while the board and robot perspective remain substantially displaced. Validation therefore remains closed despite crossing the requested `0.80` mean threshold. The next legitimate mechanism is a development-only geometric camera constraint from the known chessboard lattice, not an appearance transform or screen-space overlay.

All integrity gates pass. The run used 423 3D state renders and matched physical frames, four candidate videos, zero fits, zero replays, zero validation/heldout reads, no hardware, and no paid compute.
