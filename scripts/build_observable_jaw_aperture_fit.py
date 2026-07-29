#!/usr/bin/env python3
"""Build the OR6 jaw aperture fit and validation receipt."""

from __future__ import annotations

import json

from sim2claw.observable_jaw_aperture_fit import build_aperture_fit_receipt


if __name__ == "__main__":
    print(json.dumps(build_aperture_fit_receipt(), indent=2, sort_keys=True))
