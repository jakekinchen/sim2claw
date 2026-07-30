from __future__ import annotations

import json

from sim2claw.observable_body_joint_zero_offset_mechanism import (
    build_body_joint_mechanism_receipt,
)


def main() -> None:
    print(
        json.dumps(
            build_body_joint_mechanism_receipt(),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
