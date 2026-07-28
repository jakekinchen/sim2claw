"""Canonical chessboard semantics over the rotated legacy scene grid.

Pawn body names such as ``brown_pawn_b1`` already express the physical,
operator-reviewed semantic label.  The raw MuJoCo board grid under those bodies
must be rotated 180 degrees: canonical ``b1`` occupies raw grid coordinate
``g8``.  This module is the only adapter for new square-dependent geometry.
Historical body IDs, action bytes, receipts, and hashes remain unchanged.
"""

from __future__ import annotations

from pathlib import Path


BOARD_FILES = "abcdefgh"
BOARD_RANKS = "12345678"
CANONICAL_FRAME_ID = "standard_robot_near_rank1_v1"
LEGACY_FRAME_ID = "frozen_scene_robot_near_rank8_v1"


def _validate_square(square: str) -> str:
    normalized = str(square).lower()
    if (
        len(normalized) != 2
        or normalized[0] not in BOARD_FILES
        or normalized[1] not in BOARD_RANKS
    ):
        raise ValueError(f"invalid chess square: {square}")
    return normalized


def rotate_180_square(square: str) -> str:
    """Return the opposite square under the legacy/canonical frame change."""

    normalized = _validate_square(square)
    file_index = BOARD_FILES.index(normalized[0])
    rank_index = BOARD_RANKS.index(normalized[1])
    return f"{BOARD_FILES[7 - file_index]}{BOARD_RANKS[7 - rank_index]}"


def legacy_to_canonical_square(square: str) -> str:
    """Map a frozen-scene square label into the canonical physical frame."""

    return rotate_180_square(square)


def canonical_to_legacy_square(square: str) -> str:
    """Map a canonical semantic label to the frozen scene's raw grid label."""

    return rotate_180_square(square)


def canonical_body_grid_square(square: str) -> str:
    """Return the raw grid coordinate for a canonical semantic body suffix."""

    return canonical_to_legacy_square(square)


def canonical_square_center(square: str, **kwargs: object) -> tuple[float, float, float]:
    """Resolve a canonical square through the immutable legacy scene geometry."""

    from .scene import board_square_center

    return board_square_center(canonical_to_legacy_square(square), **kwargs)


def all_square_mappings() -> dict[str, str]:
    """Return all 64 legacy-to-canonical labels in deterministic order."""

    return {
        f"{file_name}{rank}": legacy_to_canonical_square(f"{file_name}{rank}")
        for rank in BOARD_RANKS
        for file_name in BOARD_FILES
    }


def render_canonical_orientation_svg(output_path: Path) -> None:
    """Write a deterministic, responsive 64-label orientation review artifact."""

    cell = 80
    left = 108
    top = 86
    board = cell * 8
    width = 856
    height = 860
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="title description">',
        '<title id="title">Canonical chessboard orientation</title>',
        '<description id="description">All 64 standard square labels, with '
        'rank 1 nearest the operator and board-reaching left robot arm.</description>',
        "<style>",
        "text{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}",
        ".title{font-size:28px;font-weight:700;fill:#171a18}",
        ".cue{font-size:18px;font-weight:700;fill:#8a321e}",
        ".axis{font-size:15px;font-weight:700;fill:#353a36}",
        ".sq{font-size:14px;font-weight:800;paint-order:stroke;"
        "stroke:#fff;stroke-width:3px;stroke-linejoin:round;fill:#151713}",
        "</style>",
        '<rect width="100%" height="100%" fill="#f3f1e8"/>',
        '<text class="title" x="428" y="38" text-anchor="middle">'
        "STANDARD / CANONICAL BOARD FRAME</text>",
        '<text class="cue" x="428" y="66" text-anchor="middle">'
        "FAR SIDE · RANK 8</text>",
    ]
    for visual_row, rank in enumerate(reversed(BOARD_RANKS)):
        for file_index, file_name in enumerate(BOARD_FILES):
            x = left + file_index * cell
            y = top + visual_row * cell
            fill = "#e3c79d" if (file_index + int(rank)) % 2 else "#956747"
            square = f"{file_name}{rank}"
            lines.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                    f'fill="{fill}" data-square="{square}"/>',
                    f'<text class="sq" x="{x + 8}" y="{y + 20}" '
                    f'data-square-label="{square}">{square.upper()}</text>',
                ]
            )
    lines.extend(
        [
            f'<rect x="{left}" y="{top}" width="{board}" height="{board}" '
            'fill="none" stroke="#4b2c1d" stroke-width="10"/>',
            f'<text class="cue" x="428" y="{top + board + 38}" '
            'text-anchor="middle">NEAR SIDE · RANK 1 · OPERATOR + LEFT ARM</text>',
            f'<text class="axis" x="428" y="{top + board + 70}" '
            'text-anchor="middle">a → h runs left-to-right from the operator view</text>',
            f'<text class="axis" x="428" y="{top + board + 94}" '
            'text-anchor="middle">rank 1 → 8 runs away from the operator</text>',
            "</svg>",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
