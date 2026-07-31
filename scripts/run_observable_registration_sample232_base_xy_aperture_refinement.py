"""Run OR31 static enclosure refinement."""

from sim2claw.observable_registration_sample232_base_xy_aperture_refinement import evaluate_refinement


if __name__ == "__main__":
    print(evaluate_refinement()["status"])
