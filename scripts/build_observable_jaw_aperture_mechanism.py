#!/usr/bin/env python3
"""Build the OR5 jaw-aperture mechanism declaration receipt."""

from __future__ import annotations

import json

from sim2claw.observable_jaw_aperture_mechanism import build_mechanism_receipt


if __name__ == "__main__":
    print(json.dumps(build_mechanism_receipt(), indent=2, sort_keys=True))
