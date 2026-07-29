#!/usr/bin/env python3
"""Build the OR7A signed jaw-pawn gap receipt."""

from __future__ import annotations

import json

from sim2claw.observable_jaw_pawn_geometric_gap import (
    build_geometric_gap_receipt,
)


if __name__ == "__main__":
    print(json.dumps(build_geometric_gap_receipt(), indent=2, sort_keys=True))
