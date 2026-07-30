from __future__ import annotations

import json

from sim2claw.observable_registration_studio_publication import (
    compile_observable_registration_publication,
)


def main() -> None:
    print(
        json.dumps(
            compile_observable_registration_publication(),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
