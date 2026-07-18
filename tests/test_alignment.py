from __future__ import annotations

import unittest

import numpy as np

from sim2claw.alignment import project_planar, solve_planar_homography, unproject_planar
from sim2claw.capture import load_capture_config


class AlignmentContractTest(unittest.TestCase):
    def test_homography_round_trip(self) -> None:
        world = np.asarray(
            [[-0.7, -0.4], [0.7, -0.4], [-0.7, 0.4], [0.7, 0.4]],
            dtype=float,
        )
        pixels = np.asarray(
            [[100, 120], [900, 100], [20, 700], [980, 650]],
            dtype=float,
        )
        homography = solve_planar_homography(world, pixels)
        np.testing.assert_allclose(project_planar(homography, world), pixels)
        np.testing.assert_allclose(unproject_planar(homography, pixels), world)

    def test_registered_mounts_match_overhead_photo_layout(self) -> None:
        config = load_capture_config()
        robots = config["simulation_estimates"]["robots"]
        self.assertAlmostEqual(robots[0]["mount_in_table_frame_xyz_m"][0], -0.04)
        self.assertAlmostEqual(robots[1]["mount_in_table_frame_xyz_m"][0], -0.526)
        self.assertAlmostEqual(
            config["simulation_estimates"]["board"]["center_in_table_frame_xy_m"][1],
            -0.165,
        )


if __name__ == "__main__":
    unittest.main()
