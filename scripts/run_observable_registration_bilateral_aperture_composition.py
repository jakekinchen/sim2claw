"""Run the one-shot OR28 exact-action aperture/spatial composition."""

from sim2claw.observable_registration_belief_recalculation import REPO_ROOT
from sim2claw.observable_registration_unilateral_push_dynamic_replay import (
    run_unilateral_push_dynamic_replay_once,
)


if __name__ == "__main__":
    receipt = run_unilateral_push_dynamic_replay_once(
        contract_path=REPO_ROOT
        / "configs/evaluations/observable_registration_bilateral_aperture_composition_v1.json",
        output_directory=REPO_ROOT
        / "outputs/observable_registration_bilateral_aperture_composition_v1",
    )
    print(receipt["status"])
