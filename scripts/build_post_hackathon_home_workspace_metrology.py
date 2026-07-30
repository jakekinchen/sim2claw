#!/usr/bin/env python3
"""Build the post-hackathon home-workspace metrology receipt."""

from sim2claw.post_hackathon_home_workspace_metrology import (
    build_metrology_receipt,
)


if __name__ == "__main__":
    receipt = build_metrology_receipt()
    print(receipt["result"])
