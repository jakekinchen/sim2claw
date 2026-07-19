# Spark browser dependency

- Package: `@sparkjsdev/spark`
- Version: `2.1.0`
- Source: `https://registry.npmjs.org/@sparkjsdev/spark/-/spark-2.1.0.tgz`
- Integrity: `sha512-BRw+MuMzx0B3K8fDLQygt2OHEhYUV+41RX7btq9pZ3rCVrq42o57jW34VAIvC7JO/84DJh/1AutACV9ym6BfVg==`
- Tarball SHA-256: `ff10ab3e50fe95e243eb88fad7fa5262fab99d2e2771c927161da61ec254b13d`
- Verified upstream tag: `https://github.com/sparkjsdev/spark/tree/v2.1.0`
- Published package metadata repository field:
  `git+https://github.com/sparkjs-dev/spark.git` (the hyphenated GitHub URL
  returned 404 during adoption review, so it is recorded but not treated as
  the fetch authority)
- Upstream license: `https://raw.githubusercontent.com/sparkjsdev/spark/v2.1.0/LICENSE`
- License: MIT (`LICENSE` in this directory)
- Upstream license SHA-256: `51829693e5dccd9ca1daa093991faac3aaa93238eb8fd5f5cb4130af85791d64`
- Adopted file: `dist/spark.module.js`
- Upstream adopted-file SHA-256: `c0355a962f68a6de9b13df69f05b1aba3614d9aec43a4504975daeb349126a8a`
- Locally patched adopted-file SHA-256: `9a5b64184f6e035cc31b558a5135e46f6f83218e9ebea7a0c545a86119ea37bf`
- Byte-preservation note: two upstream whitespace-only lines are intentionally
  retained so this hash stays exact; `.gitattributes` exempts only this vendored
  file from Git's whitespace diagnostic.
- Local patch: bare Three.js and `Pass.js` imports point to Studio's existing
  pinned, locally served Three.js 0.185.1 files.

Adoption reason: Studio needs an offline, deterministic WebGL2 renderer for the
exact owner-provided Gaussian PLY. Spark supports the PLY's Gaussian-splat
representation while sharing the existing Three.js render surface. Spark is
presentation-only. It can place and orbit the visual reconstruction beside a
simulation coordinate frame, but it does not grant metric scale, collision
geometry, task-coordinate, evaluator, gateway, or robot authority.
