#!/usr/bin/env python3
"""Generate deterministic, synthetic Task Orchestrator frame fixtures.

These images are contract/test fixtures only. They are not camera evidence,
training data, metric calibration, or proof of a learned or physical skill.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FIXTURES = ROOT / "configs" / "orchestrator" / "fixtures"
TEST_FIXTURES = ROOT / "tests" / "fixtures" / "orchestrator"
SIZE = 512
SQUARE = SIZE // 8
BASE_OCCUPANCY = {"b1", "c2", "d1", "e2", "f1", "g2"}


def center(square: str) -> tuple[int, int]:
    file_index = ord(square[0]) - ord("a")
    rank = int(square[1])
    return (
        file_index * SQUARE + SQUARE // 2,
        (8 - rank) * SQUARE + SQUARE // 2,
    )


def render(
    path: Path,
    occupancy: set[str],
    *,
    exposure: float = 1.0,
    drift: tuple[int, int] = (0, 0),
    obstruction: str | None = None,
) -> None:
    board = Image.new("RGB", (SIZE, SIZE), (224, 226, 222))
    draw = ImageDraw.Draw(board)
    for file_index in range(8):
        for rank_index in range(8):
            value = 204 if (file_index + rank_index) % 2 else 238
            x0 = file_index * SQUARE
            y0 = rank_index * SQUARE
            draw.rectangle(
                (x0, y0, x0 + SQUARE, y0 + SQUARE),
                fill=(value, value, value),
            )

    for square in sorted(occupancy):
        x, y = center(square)
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(119, 70, 39))
        draw.ellipse((x - 7, y - 8, x + 7, y + 6), fill=(145, 91, 54))
        draw.ellipse((x - 4, y - 8, x + 1, y - 3), fill=(177, 122, 79))

    # Mirrored tan context is deliberately outside the managed classifier.
    for square in ("b8", "c7", "d8", "e7", "f8", "g7"):
        x, y = center(square)
        draw.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(196, 160, 103))

    if obstruction:
        x, y = center(obstruction)
        draw.rectangle((x - 21, y - 21, x + 21, y + 21), fill=(22, 82, 126))

    if exposure != 1.0:
        board = board.point(lambda value: max(0, min(255, round(value * exposure))))
    if drift != (0, 0):
        shifted = Image.new("RGB", board.size, (10, 10, 10))
        shifted.paste(board, drift)
        board = shifted
    path.parent.mkdir(parents=True, exist_ok=True)
    board.save(path, format="PNG", optimize=False)


def main() -> None:
    render(CONFIG_FIXTURES / "pawn_bg_base_case_v1.png", BASE_OCCUPANCY)
    render(TEST_FIXTURES / "base_case.png", BASE_OCCUPANCY)
    render(TEST_FIXTURES / "base_case_exposure.png", BASE_OCCUPANCY, exposure=0.93)
    render(TEST_FIXTURES / "b_mismatch.png", (BASE_OCCUPANCY - {"b1"}) | {"b2"})
    required_by_file = {"b": "b1", "c": "c2", "d": "d1", "e": "e2", "f": "f1", "g": "g2"}
    for file_name, required_square in required_by_file.items():
        other_square = f"{file_name}{2 if required_square.endswith('1') else 1}"
        render(
            TEST_FIXTURES / f"{file_name}_mismatch.png",
            (BASE_OCCUPANCY - {required_square}) | {other_square},
        )
    render(
        TEST_FIXTURES / "b_c_e_mismatch.png",
        (BASE_OCCUPANCY - {"b1", "c2", "e2"}) | {"b2", "c1", "e1"},
    )
    render(
        TEST_FIXTURES / "c_e_mismatch.png",
        (BASE_OCCUPANCY - {"c2", "e2"}) | {"c1", "e1"},
    )
    render(
        TEST_FIXTURES / "e_mismatch.png",
        (BASE_OCCUPANCY - {"e2"}) | {"e1"},
    )
    render(
        TEST_FIXTURES / "d_f_g_mismatch.png",
        (BASE_OCCUPANCY - {"d1", "f1", "g2"}) | {"d2", "f2", "g1"},
    )
    render(
        TEST_FIXTURES / "f_g_mismatch.png",
        (BASE_OCCUPANCY - {"f1", "g2"}) | {"f2", "g1"},
    )
    render(
        TEST_FIXTURES / "g_mismatch.png",
        (BASE_OCCUPANCY - {"g2"}) | {"g1"},
    )
    render(TEST_FIXTURES / "missing_d.png", BASE_OCCUPANCY - {"d1"})
    render(TEST_FIXTURES / "two_f.png", BASE_OCCUPANCY | {"f2"})
    render(TEST_FIXTURES / "obstruction_g.png", BASE_OCCUPANCY, obstruction="g2")
    render(TEST_FIXTURES / "camera_drift.png", BASE_OCCUPANCY, drift=(18, 0))


if __name__ == "__main__":
    main()
