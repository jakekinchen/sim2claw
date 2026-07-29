"""Explicit historical scene facade.

The wrapped implementation retains the prior frame-selection surface solely
for read-only reproduction. It grants no current-task or physical authority.
"""

from __future__ import annotations

from typing import Any

from ..scene import build_scene_spec, build_scene_xml


def build_historical_scene_xml(**kwargs: Any) -> str:
    return build_scene_xml(**kwargs)


def build_historical_scene_spec(**kwargs: Any):
    return build_scene_spec(**kwargs)
