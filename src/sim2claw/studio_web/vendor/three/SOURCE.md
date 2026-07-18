# Three.js browser dependency

- Package: `three`
- Version: `0.185.1`
- Source: `https://registry.npmjs.org/three/-/three-0.185.1.tgz`
- Upstream: `https://github.com/mrdoob/three.js`
- License: MIT (`LICENSE` in this directory)
- Adopted files: `build/three.module.min.js`, its `build/three.core.min.js`
  module dependency, `examples/jsm/controls/OrbitControls.js`, and
  `examples/jsm/loaders/STLLoader.js`
- Local patch: the two add-ons' bare `three` import specifiers point to the
  vendored module so the existing strict Content Security Policy needs no
  inline import map.

Reason: the Studio needs a deterministic, locally served WebGL renderer, orbit
camera controls, and a loader for the existing upstream SO-101 STL assets. The
dependency is presentation-only: MuJoCo remains the physics and pose authority.
No CDN or runtime package installation is required.
