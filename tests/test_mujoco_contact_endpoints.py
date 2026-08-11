from types import SimpleNamespace

import mujoco
import pytest

from sim2claw.mujoco_contact_endpoints import (
    ContactEndpointError,
    flex_semantics_from_names,
    resolve_contact_pair,
)


def _model() -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_string(
        """
        <mujoco>
          <worldbody>
            <body name="jaw">
              <geom name="jaw_geom" type="box" size=".01 .01 .01"/>
              <flexcomp name="cap" type="grid" dim="3" count="3 3 3"
                        spacing=".01 .01 .01" radius="0" mass=".001"
                        dof="trilinear">
                <contact selfcollide="none" internal="false"/>
                <edge equality="false"/>
                <elasticity young="10000"/>
                <pin id="0 1 2 3"/>
              </flexcomp>
            </body>
            <body name="pawn">
              <geom name="pawn_geom" type="sphere" size=".01"/>
            </body>
            <body name="decoy">
              <geom name="last_geom_decoy" type="sphere" size=".01"/>
            </body>
          </worldbody>
        </mujoco>
        """
    )


def _flex_geom_contact(model: mujoco.MjModel) -> SimpleNamespace:
    flex_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, "cap")
    pawn_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "pawn_geom")
    return SimpleNamespace(
        geom=[-1, pawn_geom],
        flex=[flex_id, -1],
        elem=[0, -1],
        vert=[-1, -1],
    )


def test_flex_endpoint_uses_explicit_alias_not_negative_geom_index() -> None:
    model = _model()
    semantics = flex_semantics_from_names(
        model, {"cap": ("jaw", "fixed_jaw")}
    )
    flex, pawn = resolve_contact_pair(
        model, _flex_geom_contact(model), flex_semantics=semantics
    )
    decoy_geom = model.ngeom - 1
    assert flex.kind == "flex"
    assert flex.geom_id == -1
    assert flex.body_name == "jaw"
    assert flex.role == "fixed_jaw"
    assert flex.body_id != int(model.geom_bodyid[decoy_geom])
    assert pawn.kind == "geom"
    assert pawn.body_name == "pawn"
    assert pawn.object_name == "pawn_geom"


def test_unknown_flex_identity_fails_closed() -> None:
    model = _model()
    with pytest.raises(ContactEndpointError, match="no explicit semantic alias"):
        resolve_contact_pair(model, _flex_geom_contact(model))


def test_rigid_contact_pair_remains_supported() -> None:
    model = _model()
    jaw_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "jaw_geom")
    pawn_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "pawn_geom")
    contact = SimpleNamespace(
        geom=[jaw_geom, pawn_geom],
        flex=[-1, -1],
        elem=[-1, -1],
        vert=[-1, -1],
    )
    jaw, pawn = resolve_contact_pair(model, contact)
    assert (jaw.kind, jaw.body_name) == ("geom", "jaw")
    assert (pawn.kind, pawn.body_name) == ("geom", "pawn")
