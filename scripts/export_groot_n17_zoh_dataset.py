#!/usr/bin/env python3
"""Export the frozen 20 Hz zero-order-hold GR00T chess dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.groot_chess import (
    export_groot_dataset,
    groot_zoh_dataset_contract_sha256,
    load_groot_zoh_dataset_contract,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_groot_zoh_dataset_contract()
    receipt = export_groot_dataset(
        args.output,
        split=str(contract["split"]),
        control_mode=str(contract["control_execution"]["mode"]),
        episode_indices=[int(index) for index in contract["source_episode_indices"]],
    )
    if receipt["zoh_dataset_contract_sha256"] != (groot_zoh_dataset_contract_sha256()):
        raise RuntimeError("exported receipt references the wrong ZOH contract")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
