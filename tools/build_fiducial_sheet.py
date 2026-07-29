from __future__ import annotations

import ctypes
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "apriltag_tag36h11_20mm_ids_0-19_letter.pdf"


def mm(value: float) -> float:
    return value * 72.0 / 25.4


class AprilTagFamily(ctypes.Structure):
    _fields_ = [
        ("ncodes", ctypes.c_uint32),
        ("codes", ctypes.POINTER(ctypes.c_uint64)),
        ("width_at_border", ctypes.c_int),
        ("total_width", ctypes.c_int),
        ("reversed_border", ctypes.c_bool),
        ("nbits", ctypes.c_uint32),
        ("bit_x", ctypes.POINTER(ctypes.c_uint32)),
        ("bit_y", ctypes.POINTER(ctypes.c_uint32)),
        ("h", ctypes.c_uint32),
        ("name", ctypes.c_char_p),
        ("impl", ctypes.c_void_p),
    ]


def load_tag36h11_family() -> tuple[int, int, list[int], list[tuple[int, int]]]:
    native = Path("/tmp/sim2claw_fiducial_pkgs.d3wzrV/native")
    ctypes.CDLL(str(native / "wpiutil/lib/libwpiutil.dylib"), mode=ctypes.RTLD_GLOBAL)
    ctypes.CDLL(str(native / "wpimath/lib/libwpimath.dylib"), mode=ctypes.RTLD_GLOBAL)
    apriltag = ctypes.CDLL(
        str(native / "apriltag/lib/libapriltag.dylib"), mode=ctypes.RTLD_GLOBAL
    )
    apriltag.tag36h11_create.restype = ctypes.POINTER(AprilTagFamily)
    apriltag.tag36h11_destroy.argtypes = [ctypes.POINTER(AprilTagFamily)]

    family_ptr = apriltag.tag36h11_create()
    family = family_ptr.contents
    try:
        codes = [int(family.codes[i]) for i in range(family.ncodes)]
        bit_positions = [
            (int(family.bit_x[i]), int(family.bit_y[i]))
            for i in range(family.nbits)
        ]
        return int(family.total_width), int(family.width_at_border), codes, bit_positions
    finally:
        apriltag.tag36h11_destroy(family_ptr)


def tag_grid(tag_id: int, family: tuple[int, int, list[int], list[tuple[int, int]]]) -> list[list[int]]:
    total_width, width_at_border, codes, bit_positions = family
    nbits = len(bit_positions)
    code = codes[tag_id]
    offset = (total_width - width_at_border) // 2

    # 1 means white, 0 means black. The full tag is 10 x 10 modules:
    # one white quiet module, an 8 x 8 black/data region, and the data bits.
    grid = [[1 for _ in range(total_width)] for _ in range(total_width)]
    for row in range(offset, offset + width_at_border):
        for col in range(offset, offset + width_at_border):
            grid[row][col] = 0

    for bit_index, (col, row) in enumerate(bit_positions):
        bit = (code >> (nbits - 1 - bit_index)) & 1
        grid[offset + row][offset + col] = int(bit)
    return grid


def draw_tag(pdf: canvas.Canvas, tag_id: int, x: float, y: float, size: float, family) -> None:
    grid = tag_grid(tag_id, family)
    module = size / len(grid)
    for row, cells in enumerate(grid):
        for col, value in enumerate(cells):
            pdf.setFillColor(colors.white if value else colors.black)
            pdf.rect(
                x + col * module,
                y + (len(grid) - row - 1) * module,
                module,
                module,
                stroke=0,
                fill=1,
            )


def build_pdf() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = letter
    pdf = canvas.Canvas(str(OUTPUT), pagesize=letter, pageCompression=0)
    pdf.setTitle("AprilTag tag36h11 fiducial sheet - 20 mm IDs 0-19")
    pdf.setAuthor("Codex")
    pdf.setSubject("Twenty unique tag36h11 AprilTags, each exactly 20 mm x 20 mm")

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawCentredString(page_width / 2, page_height - mm(16), "AprilTag tag36h11 fiducials")
    pdf.setFont("Helvetica", 8.5)
    pdf.drawCentredString(
        page_width / 2,
        page_height - mm(22),
        "IDs 0-9 | black tag area: exactly 20 mm x 20 mm | print at 100% / Actual Size",
    )

    tag_size = mm(20)
    col_pitch = mm(35)
    row_pitch = mm(41)
    left = (page_width - 4 * col_pitch - tag_size) / 2
    top = page_height - mm(37)
    family = load_tag36h11_family()

    for tag_id in range(20):
        col = tag_id % 5
        row = tag_id // 5
        x = left + col * col_pitch
        y = top - row * row_pitch - tag_size
        draw_tag(pdf, tag_id, x, y, tag_size, family)
        pdf.setFillColor(colors.black)
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(x + tag_size / 2, y - mm(4.0), f"tag36h11 ID {tag_id}")

    pdf.setFillColor(colors.Color(0.35, 0.35, 0.35))
    pdf.setFont("Helvetica", 7.5)
    pdf.drawCentredString(
        page_width / 2,
        mm(12),
        "Cut on the tag edges if needed; preserve the white border around each tag.",
    )
    pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    build_pdf()
