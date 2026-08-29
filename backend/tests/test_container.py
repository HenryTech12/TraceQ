"""Unit tests for the raw-byte container walkers and format detection —
independent of the fixture files, so these run even before
generate_fixtures.py has been run."""
from __future__ import annotations

import io
import struct
import zlib

from PIL import Image

from traceq.container import declared_format_from_filename, detect_actual_format, walk_jpeg, walk_png


def test_format_detection_ignores_extension_uses_magic_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "JPEG")
    data = buf.getvalue()
    assert detect_actual_format(data) == "jpeg"
    assert declared_format_from_filename("photo.png") == "png"
    assert declared_format_from_filename("photo.png") != detect_actual_format(data)


def test_walk_jpeg_finds_soi_eoi_and_no_trailing_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32)).save(buf, "JPEG")
    data = buf.getvalue()
    container = walk_jpeg(data)
    assert container.width == 32
    assert container.height == 32
    assert container.trailing_byte_count == 0
    assert not container.truncated


def test_walk_jpeg_detects_trailing_bytes_after_eoi():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32)).save(buf, "JPEG")
    data = buf.getvalue() + b"HIDDEN-PAYLOAD-AFTER-EOI"
    container = walk_jpeg(data)
    assert container.trailing_byte_count == len(b"HIDDEN-PAYLOAD-AFTER-EOI")


def test_walk_jpeg_detects_progressive_flag():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "JPEG", progressive=True)
    container = walk_jpeg(buf.getvalue())
    assert container.is_progressive is True

    buf2 = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf2, "JPEG", progressive=False)
    container2 = walk_jpeg(buf2.getvalue())
    assert container2.is_progressive is False


def test_walk_png_finds_ihdr_dimensions_and_no_trailing_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (48, 40)).save(buf, "PNG")
    data = buf.getvalue()
    container = walk_png(data)
    assert container.width == 48
    assert container.height == 40
    assert container.trailing_byte_count == 0


def test_walk_png_detects_trailing_bytes_after_iend():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    data = buf.getvalue() + b"TRAILING"
    container = walk_png(data)
    assert container.trailing_byte_count == len(b"TRAILING")


def test_walk_png_reads_custom_chunk():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    png_bytes = buf.getvalue()
    chunk_type, chunk_data = b"teSt", b"hello-world"
    crc = struct.pack(">I", zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF)
    chunk = struct.pack(">I", len(chunk_data)) + chunk_type + chunk_data + crc
    iend_marker = struct.pack(">I", 0) + b"IEND"
    idx = png_bytes.rfind(iend_marker)
    injected = png_bytes[:idx] + chunk + png_bytes[idx:]

    container = walk_png(injected)
    matches = [c for c in container.chunks if c.type == "teSt"]
    assert len(matches) == 1
    assert matches[0].data == chunk_data
