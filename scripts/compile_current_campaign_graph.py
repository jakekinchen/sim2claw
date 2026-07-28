#!/usr/bin/env python3
"""Compile the current bidirectional campaign into the shared SAIL graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.current_campaign_graph import (
    compile_current_campaign_graph,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    graph = compile_current_campaign_graph(
        args.config,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "campaign_id": graph["campaign_id"],
                "graph_digest": graph["graph_digest"],
                "nodes": graph["counts"]["nodes"],
                "edges": graph["counts"]["edges"],
                "active_pointer": graph["active_pointer"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
