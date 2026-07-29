#!/usr/bin/env python3
"""Run the write-once OR7 exact-action jaw-aperture replay."""

from __future__ import annotations

import json

from sim2claw.observable_jaw_aperture_replay import (
    run_aperture_replay_once,
)


if __name__ == "__main__":
    print(json.dumps(run_aperture_replay_once(), indent=2, sort_keys=True))
