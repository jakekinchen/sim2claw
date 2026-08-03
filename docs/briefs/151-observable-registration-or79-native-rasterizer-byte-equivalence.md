# OR79 native rasterizer byte equivalence

OR79 established a proof-preserving compiled acceleration seam for the accepted OR78 renderer. It prepared the same 824,944-triangle stream from the same scene, development trace, frozen OR73 camera, source meshes, primitive tessellation, colors, and lighting. It read no physical video.

The ordinary `clang -O2 -std=c11` raster core produced zero pixel mismatches against both the Python result and the accepted OR78 reference. The encoded PNG hash is identical: `a079217...`. Depth updates are exactly `243,348` and occluded fragments are exactly `18,780` in both implementations.

The native raster stage took `0.0356 s` versus `22.0645 s` for the Python loop, a measured `620.1x` speedup. All `13/13` gates pass. This admits the exact accelerated seam for a frozen full-development timeline, but proves no temporal, visual-threshold, physics, validation, held-out, or transfer claim by itself.
