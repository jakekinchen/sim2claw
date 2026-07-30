from __future__ import annotations

import json

from sim2claw.observable_spatial_validation_acquisition import (
    build_spatial_validation_acquisition_readiness,
)


def main() -> None:
    print(
        json.dumps(
            build_spatial_validation_acquisition_readiness(),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
