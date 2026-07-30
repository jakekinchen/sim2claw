from __future__ import annotations

import json

from sim2claw.post_hackathon_home_workspace_geometry_camera import (
    build_geometry_camera_receipt,
)


def main() -> None:
    print(
        json.dumps(
            build_geometry_camera_receipt(),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
