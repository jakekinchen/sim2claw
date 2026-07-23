"""Handshake wrapper that lets the parent lease a test child before exec."""

from __future__ import annotations

import argparse
import os
import select
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sim2claw-dev-loop-worker")
    parser.add_argument("--gate-fd", type=int, required=True)
    parser.add_argument("--gate-timeout-seconds", type=float, default=30.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        return 2
    ready, _, _ = select.select([args.gate_fd], [], [], args.gate_timeout_seconds)
    if not ready:
        return 125
    token = os.read(args.gate_fd, 1)
    os.close(args.gate_fd)
    if token != b"1":
        return 126
    os.execvp(command[0], command)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
