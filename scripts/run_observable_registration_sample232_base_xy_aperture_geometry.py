"""Run the frozen OR30 static base-XY/aperture geometry diagnostic."""

from sim2claw.observable_registration_sample232_base_xy_aperture_geometry import (
    evaluate_sample232_base_xy_aperture_geometry,
)


if __name__ == "__main__":
    print(evaluate_sample232_base_xy_aperture_geometry()["status"])
