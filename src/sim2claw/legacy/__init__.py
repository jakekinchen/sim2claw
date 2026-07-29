"""Read-only compatibility entrypoints for frozen sim2claw evidence.

New runtime code must not import this namespace. It exists only so historical
receipts and action hashes remain reproducible after the canonical cutover.
"""

from .scene import build_historical_scene_spec, build_historical_scene_xml

__all__ = ["build_historical_scene_spec", "build_historical_scene_xml"]
