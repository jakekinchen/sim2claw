"""Run OR33 static wrist path geometry diagnostic."""

from sim2claw.observable_registration_sample232_wrist_path_geometry import evaluate_wrist_path_geometry


if __name__ == "__main__":
    print(evaluate_wrist_path_geometry()["status"])
