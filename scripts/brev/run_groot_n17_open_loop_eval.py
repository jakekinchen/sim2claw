#!/usr/bin/env python3
"""Run NVIDIA's open-loop evaluator with an explicit diagnostic RNG seed."""

from __future__ import annotations

import argparse
import os
import random
import sys

import numpy as np
import torch


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--diagnostic-seed",
        type=int,
        default=int(os.environ.get("GROOT_EVAL_SEED", "0")),
    )
    args, remaining = parser.parse_known_args()
    if args.diagnostic_seed < 0:
        parser.error("diagnostic seed must be non-negative")

    random.seed(args.diagnostic_seed)
    np.random.seed(args.diagnostic_seed)
    torch.manual_seed(args.diagnostic_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.diagnostic_seed)

    from gr00t.eval.open_loop_eval import ArgsConfig, main as nvidia_main
    import tyro

    print(f"sim2claw diagnostic inference seed: {args.diagnostic_seed}")
    sys.argv = [sys.argv[0], *remaining]
    nvidia_main(tyro.cli(ArgsConfig))


if __name__ == "__main__":
    main()
