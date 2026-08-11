"""Fail-closed MuJoCo contact endpoint identity resolution.

MuJoCo stores geom-to-flex contacts with ``geom == -1`` on the flex side.
Indexing ``model.geom_bodyid[-1]`` therefore silently assigns the last geom's
body to that endpoint.  This module centralizes endpoint resolution so rigid
and deformable contacts use explicit, auditable identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import mujoco


class ContactEndpointError(RuntimeError):
    """A contact endpoint cannot be assigned a safe semantic identity."""


@dataclass(frozen=True)
class FlexContactSemantic:
    """Explicit body/role alias for a compiled flex identity."""

    flex_id: int
    flex_name: str
    body_id: int
    body_name: str
    role: str


@dataclass(frozen=True)
class ContactEndpoint:
    """Resolved identity for one side of ``mjContact``."""

    side: int
    kind: str
    geom_id: int
    flex_id: int
    elem_id: int
    vert_id: int
    body_id: int
    body_name: str
    object_name: str
    role: str | None


def _name(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    object_id: int,
    fallback: str,
) -> str:
    value = mujoco.mj_id2name(model, object_type, object_id)
    return str(value) if value else fallback


def flex_semantics_from_names(
    model: mujoco.MjModel,
    declarations: Mapping[str, tuple[str, str]],
) -> dict[int, FlexContactSemantic]:
    """Compile flex-name declarations into ID-bound body aliases.

    ``declarations`` maps flex name to ``(body_name, role)``.  Trilinear flex
    vertices do not own a reliable body identity, so the alias is mandatory.
    """

    semantics: dict[int, FlexContactSemantic] = {}
    for flex_name, (body_name, role) in declarations.items():
        flex_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_FLEX, flex_name)
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if flex_id < 0:
            raise ContactEndpointError(f"declared flex is missing: {flex_name}")
        if body_id < 0:
            raise ContactEndpointError(
                f"declared flex body alias is missing: {body_name}"
            )
        semantics[flex_id] = FlexContactSemantic(
            flex_id=flex_id,
            flex_name=flex_name,
            body_id=body_id,
            body_name=body_name,
            role=role,
        )
    return semantics


def resolve_contact_endpoint(
    model: mujoco.MjModel,
    contact: mujoco.MjContact,
    side: int,
    *,
    flex_semantics: Mapping[int, FlexContactSemantic] | None = None,
) -> ContactEndpoint:
    """Resolve a rigid geom or flex endpoint without negative indexing."""

    if side not in (0, 1):
        raise ContactEndpointError(f"contact side must be 0 or 1, got {side}")
    geom_id = int(contact.geom[side])
    flex_id = int(contact.flex[side])
    elem_id = int(contact.elem[side])
    vert_id = int(contact.vert[side])
    if geom_id >= 0 and flex_id >= 0:
        raise ContactEndpointError("contact endpoint has both geom and flex identity")
    if geom_id >= 0:
        if geom_id >= model.ngeom:
            raise ContactEndpointError(f"contact geom id is out of range: {geom_id}")
        body_id = int(model.geom_bodyid[geom_id])
        return ContactEndpoint(
            side=side,
            kind="geom",
            geom_id=geom_id,
            flex_id=-1,
            elem_id=elem_id,
            vert_id=vert_id,
            body_id=body_id,
            body_name=_name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id, f"body_{body_id}"
            ),
            object_name=_name(
                model, mujoco.mjtObj.mjOBJ_GEOM, geom_id, f"geom_{geom_id}"
            ),
            role=None,
        )
    if flex_id >= 0:
        semantic = (flex_semantics or {}).get(flex_id)
        if semantic is None:
            flex_name = _name(
                model, mujoco.mjtObj.mjOBJ_FLEX, flex_id, f"flex_{flex_id}"
            )
            raise ContactEndpointError(
                f"flex contact has no explicit semantic alias: {flex_name}"
            )
        return ContactEndpoint(
            side=side,
            kind="flex",
            geom_id=-1,
            flex_id=flex_id,
            elem_id=elem_id,
            vert_id=vert_id,
            body_id=semantic.body_id,
            body_name=semantic.body_name,
            object_name=semantic.flex_name,
            role=semantic.role,
        )
    raise ContactEndpointError("contact endpoint has neither geom nor flex identity")


def resolve_contact_pair(
    model: mujoco.MjModel,
    contact: mujoco.MjContact,
    *,
    flex_semantics: Mapping[int, FlexContactSemantic] | None = None,
) -> tuple[ContactEndpoint, ContactEndpoint]:
    """Resolve both endpoints of one contact."""

    return (
        resolve_contact_endpoint(
            model, contact, 0, flex_semantics=flex_semantics
        ),
        resolve_contact_endpoint(
            model, contact, 1, flex_semantics=flex_semantics
        ),
    )


__all__ = [
    "ContactEndpoint",
    "ContactEndpointError",
    "FlexContactSemantic",
    "flex_semantics_from_names",
    "resolve_contact_endpoint",
    "resolve_contact_pair",
]
