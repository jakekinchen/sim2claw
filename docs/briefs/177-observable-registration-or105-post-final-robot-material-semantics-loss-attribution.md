# OR105 — Post-final robot material-semantics loss attribution

OR104's bounded shared articulation correction improved the outside-board edge
metric but failed its development gate. Its frozen montage also reveals that
the renderer depicts both robots as uniformly neutral gray, unlike the distinct
structural and servo materials visible in the physical scene.

OR105 tests a narrower source-level mechanism before touching pixels again. It
maps every robot mesh geom in the frozen renderer scene manifest back to the
reviewed, hash-bound upstream SO-101 XML and compares material-class diversity.
The audit passes only if all robot visual meshes map, the renderer has collapsed
them to one RGBA class, and upstream preserves at least distinct dark-servo and
non-servo structural classes.

No footage or candidate video is decoded, no render or fit is performed, and
no color value is selected. A pass authorizes only a bounded two-class material
palette calibration card. It does not establish the physical palette, same-video
match, kinematic or physics fidelity, transfer, or simulator promotion.
