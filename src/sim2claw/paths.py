from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE_CONFIG = (
    REPO_ROOT
    / "configs"
    / "polycam"
    / "8873B66C-774C-48B1-B51D-338645867009.json"
)
DEFAULT_EXTERNAL_ROOT = REPO_ROOT / "external" / "polycam"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs" / "polycam_chess_table"
DEFAULT_CHESS_TASK_CONFIG = REPO_ROOT / "configs" / "tasks" / "chess_rook_lift_v1.json"
DEFAULT_GROOT_CHESS_TASK_CONFIG = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_groot_v1.json"
)
DEFAULT_SO101_MASS_PROFILE = (
    REPO_ROOT / "calibration" / "so101" / "follower_mass_profile_v1.json"
)
STUDIO_ASSET_ROOT = (
    REPO_ROOT / "src" / "sim2claw" / "studio_web" / "assets" / "workcell"
)
SO101_MODEL_PATH = (
    REPO_ROOT
    / "third_party"
    / "mujoco_menagerie"
    / "robotstudio_so101"
    / "so101.xml"
)
