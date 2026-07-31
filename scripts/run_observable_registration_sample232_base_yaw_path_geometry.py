"""Run OR32 static base-yaw path geometry refinement."""

from sim2claw.observable_registration_sample232_base_yaw_path_geometry import evaluate_base_yaw_path_geometry


if __name__ == "__main__":
    print(evaluate_base_yaw_path_geometry()["status"])
