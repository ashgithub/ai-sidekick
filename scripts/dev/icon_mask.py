#!/usr/bin/env python3
"""Apply a macOS-style rounded transparent mask to a PNG icon."""

from __future__ import annotations

import binascii
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import sys
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass
class PngImage:
    width: int
    height: int
    chunks: list[tuple[bytes, bytes]]
    rows: list[bytearray]


def paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_delta = abs(estimate - left)
    up_delta = abs(estimate - up)
    up_left_delta = abs(estimate - up_left)
    if left_delta <= up_delta and left_delta <= up_left_delta:
        return left
    if up_delta <= up_left_delta:
        return up
    return up_left


def read_png(path: Path) -> PngImage:
    data = path.read_bytes()
    if data[:8] != PNG_SIGNATURE:
        raise SystemExit(f"{path} is not a PNG")

    chunks: list[tuple[bytes, bytes]] = []
    compressed = bytearray()
    width = height = 0
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        chunks.append((chunk_type, payload))
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or color_type != 6 or interlace != 0:
                raise SystemExit("Expected a non-interlaced 8-bit RGBA PNG")
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        offset += length + 12

    row_width = width * 4
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytearray] = []
    position = 0
    previous = bytearray(row_width)
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        row = bytearray(raw[position : position + row_width])
        position += row_width
        for index in range(row_width):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            up_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                row[index] = (row[index] + paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise SystemExit(f"Unsupported PNG filter: {filter_type}")
        rows.append(row)
        previous = row
    return PngImage(width=width, height=height, chunks=chunks, rows=rows)


def write_png(path: Path, image: PngImage) -> None:
    filtered = bytearray()
    for row in image.rows:
        filtered.append(0)
        filtered.extend(row)
    idat = zlib.compress(bytes(filtered), 9)

    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", checksum)

    output = bytearray(PNG_SIGNATURE)
    for chunk_type, payload in image.chunks:
        if chunk_type in {b"IDAT", b"IEND"}:
            continue
        output.extend(chunk(chunk_type, payload))
    output.extend(chunk(b"IDAT", idat))
    output.extend(chunk(b"IEND", b""))
    path.write_bytes(output)


def signed_rounded_rect_distance(x: float, y: float, width: int, height: int, radius: float) -> float:
    qx = abs(x - width / 2) - (width / 2 - radius)
    qy = abs(y - height / 2) - (height / 2 - radius)
    outside_x = max(qx, 0.0)
    outside_y = max(qy, 0.0)
    return math.hypot(outside_x, outside_y) + min(max(qx, qy), 0.0) - radius


def apply_mask(image: PngImage) -> None:
    inset = image.width * 0.045
    radius = image.width * 0.18
    edge = 4.0
    for y, row in enumerate(image.rows):
        for x in range(image.width):
            distance = signed_rounded_rect_distance(
                x + 0.5 - inset,
                y + 0.5 - inset,
                round(image.width - inset * 2),
                round(image.height - inset * 2),
                radius,
            )
            mask_alpha = max(0.0, min(1.0, 0.5 - distance / edge))
            offset = x * 4
            row[offset + 3] = round(row[offset + 3] * mask_alpha)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "src/ai_tools/web_panel/static/assets/codex-sidekick-icon.png"
    )
    image = read_png(path)
    if image.width != image.height:
        raise SystemExit("Expected a square icon PNG")
    apply_mask(image)
    write_png(path, image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
