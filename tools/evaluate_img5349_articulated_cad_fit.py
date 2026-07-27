#!/usr/bin/env python3
"""Reproduce the bounded IMG_5349 articulated-CAD surface diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.img5349_articulated_cad_fit import evaluate_contract, load_contract


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT / "configs/evaluations/img5349_articulated_cad_fit_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_contract(load_contract(args.contract), repo_root=ROOT)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
