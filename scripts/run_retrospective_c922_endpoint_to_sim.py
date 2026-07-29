from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.retrospective_c922_endpoint_to_sim import (
    CONTRACT_PATH,
    OUTPUT_DIRECTORY,
    evaluate,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    args = parser.parse_args()
    receipt = evaluate(
        contract_path=args.contract.resolve(),
        output_directory=args.output_directory.resolve(),
    )
    print(json.dumps(receipt["ledger"], indent=2, sort_keys=True))
    print(receipt["verdict"])


if __name__ == "__main__":
    main()
