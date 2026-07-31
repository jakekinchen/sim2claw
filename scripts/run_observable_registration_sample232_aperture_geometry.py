"""Run the frozen OR29 static sample-232 aperture geometry selection."""

from sim2claw.observable_registration_sample232_aperture_geometry import (
    evaluate_sample232_aperture_geometry,
)


if __name__ == "__main__":
    print(evaluate_sample232_aperture_geometry()["status"])
