from __future__ import annotations

import mujoco
import pytest

from sim2claw.named_jaw_contact import (
    NamedJawContactError,
    measure_named_jaw_contact,
    resolve_named_contact_geometry,
)


XML = """
<mujoco>
  <worldbody>
    <body name="fixed" pos="-0.02 0 0">
      <geom name="left_fixed_jaw_pad" type="sphere" size="0.01"/>
      <geom name="left_fixed_jaw_sph_tip1" type="sphere" size="0.001"/>
    </body>
    <body name="moving" pos="0.02 0 0">
      <geom name="left_moving_jaw_pad" type="sphere" size="0.01"/>
      <geom name="left_moving_jaw_sph_tip1" type="sphere" size="0.001"/>
    </body>
    <body name="pawn" pos="-0.005 0 0">
      <freejoint name="pawn_free"/>
      <geom name="pawn_collision" type="sphere" size="0.005"/>
    </body>
  </worldbody>
</mujoco>
"""


def test_named_contact_reports_pad_identity_and_bracketing() -> None:
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    geometry = resolve_named_contact_geometry(
        model,
        selected_body_name="pawn",
        fixed_jaw_prefix="left_fixed_jaw_",
        moving_jaw_prefix="left_moving_jaw_",
        fixed_tip_names=["left_fixed_jaw_sph_tip1"],
        moving_tip_names=["left_moving_jaw_sph_tip1"],
    )

    measured = measure_named_jaw_contact(
        model,
        data,
        geometry,
        distance_maximum_m=1.0,
        other_pad_tolerance_m=0.04,
    )

    assert measured["fixed"]["signed_distance_m"] <= 0.0
    assert measured["fixed"]["jaw_geom"] == "left_fixed_jaw_pad"
    assert measured["pawn_center_bracketed"] is True
    assert measured["phase_contact_geometry_pass"] is True


def test_named_contact_fails_closed_when_prefix_is_missing() -> None:
    model = mujoco.MjModel.from_xml_string(XML)
    with pytest.raises(NamedJawContactError, match="fixed jaw"):
        resolve_named_contact_geometry(
            model,
            selected_body_name="pawn",
            fixed_jaw_prefix="missing_",
            moving_jaw_prefix="left_moving_jaw_",
            fixed_tip_names=["left_fixed_jaw_sph_tip1"],
            moving_tip_names=["left_moving_jaw_sph_tip1"],
        )
