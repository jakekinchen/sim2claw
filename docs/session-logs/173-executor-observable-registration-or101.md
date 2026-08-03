# Executor session 173: OR101

- Started from admitted active card `OR101`; agent profile and executor context passed.
- Parsed the eleven immutable OR97 occupancy maps and exactly reproduced every physical/candidate dynamic outside-board pixel count without decoding video, rendering, fitting, or selecting transform values.
- The physical dynamic masks contain a median `2.0333x` as many occupied pixels as the candidate in all eleven episodes, but their median bounding-box diagonal ratio is only `0.9761`, below the frozen `1.2` scale threshold. The mismatch is denser internal motion/articulation, not a globally smaller bounding footprint.
- Mean dynamic occupancy F1 remains `0.569456 < 0.6`, so the frozen decision tree selects robot articulation and timing rather than another camera-ray depth-scale transform.
- All `7/7` gates pass. This is mechanism attribution only, with no same-video, kinematic, physics, transfer, or promotion claim.
