#!/usr/bin/env python3
"""Build the frozen metric board-to-left-base readiness receipt."""

from sim2claw.robot_base_to_board_metric_anchor_readiness import (
    build_metric_anchor_readiness_receipt,
)


if __name__ == "__main__":
    receipt = build_metric_anchor_readiness_receipt()
    print(receipt["result"])
