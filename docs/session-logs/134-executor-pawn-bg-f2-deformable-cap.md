# OR134 executor log

OR134 stopped at its rigid identity control. The exact retained F2-to-F1
action remained byte-identical (`440x6`, `float64`, SHA-256
`ff5845e886aa7f6e65ffa978f758ccb2777fcaac8a71bd51cd02171f61ebdb34`),
but the current runner did not reproduce the retained `0.91` dynamics.

The historical result at implementation SHA-256
`6425cbdc787d179ec4a76d42d8dd1272b9b2dc398ffccb219edaed4bbb941905`
and repository commit `7eaf1cfe6322ade504b66ff6af7c4fe66d5811e7`
finished `0.007662688216 m` from F1, rose `0.042395539952 m`, established
qualified bilateral contact, and stayed upright. It still was not a strict
transfer success because the final center missed the `0.006 m` precision gate
and retained carry was false.

The OR134 rigid control instead finished `0.164522288251 m` from F1, rose only
`0.015010064376 m`, never established qualified bilateral contact, and did not
stay upright. Its complete `9,932`-step trace SHA-256 is
`f315783560f849d300bc2f6344a408328ccd7853539d3dc71f536af3e8f3a229`;
the independent verdict SHA-256 is
`92ac3fdb7a1646a244a83e0fb81fadf1b2ab81a67bdf1127148a999aabf1333e`.

Exactly one rigid candidate and zero flex candidates ran. The failed baseline
does not test deformable fingertips and does not support changing MuJoCo's
contact cone. The historical scene used the elliptic cone, Newton solver,
implicitfast integrator, 10 solver iterations, 20 line-search iterations,
zero no-slip iterations, friction impratio 10, and a post-multiplier timestep
of `0.00225 s`.

Terminal status:
`TERMINAL_RIGID_CONTROL_IDENTITY_REPRODUCTION_FAILED_NO_FLEX_EXECUTED`.
Only a new owner-authorized compatibility identity may proceed: first reproduce
the historical rigid control under a fully frozen runtime/model signature;
only then run the unchanged five-member flex family.
