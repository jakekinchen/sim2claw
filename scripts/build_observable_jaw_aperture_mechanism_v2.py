#!/usr/bin/env python3
"""Build the OR5 aggregate-rank jaw mechanism receipt."""

from __future__ import annotations

import json

from sim2claw.observable_jaw_aperture_mechanism_v2 import (
    build_mechanism_v2_receipt,
)


if __name__ == "__main__":
    print(json.dumps(build_mechanism_v2_receipt(), indent=2, sort_keys=True))
