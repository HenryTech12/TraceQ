"""Raw-byte container walkers.

Pillow silently drops PNG `eXIf` chunks and JPEG APP11/JUMBF segments —
exactly where the highest-value provenance evidence lives (C2PA manifests,
Android screenshot EXIF). This module never uses a library wrapper for
metadata; it walks the raw bytes of the container format itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
MAGIC_PDF = b"%PDF-"

# JPEG markers that carry a 2-byte big-endian length field after the marker.
_LENGTH_BEARING = True  # all markers except SOI/EOI/RSTn/TEM carry a length


@dataclass
class JpegSegment:
    marker: int  # e.g. 0xFFE1
    offset: int  # byte offset of the marker in the file
    length: int  # segment length as declared (includes the 2 length bytes)
    data: bytes  # payload, excluding the 2 length bytes


@dataclass
class JpegContainer:
    segments: list[JpegSegment] = field(default_factory=list)
    sof_marker: int | None = None
    width: int | None = None
    height: int | None = None
    num_components: int | None = None
    component_sampling: dict[int, tuple[int, int]] = field(default_factory=dict)
    is_progressive: bool = False
    trailing_byte_count: int = 0
    truncated: bool = False

    def segments_of(self, marker: int) -> list[JpegSegment]:
        return [s for s in self.segments if s.marker == marker]


@dataclass
class PngChunk:
    type: str
    offset: int
    data: bytes


@dataclass
class PngContainer:
    chunks: list[PngChunk] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    trailing_byte_count: int = 0
    truncated: bool = False

    def chunks_of(self, type_: str) -> list[PngChunk]:
        return [c for c in self.chunks if c.type == type_]


def detect_actual_format(data: bytes) -> str:
    """Detect format from magic bytes, never from the file extension."""
    if data.startswith(MAGIC_JPEG):
        return "jpeg"
    if data.startswith(MAGIC_PNG):
        return "png"
    if data.startswith(MAGIC_PDF):
        return "pdf"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] in (b"BM",):
        return "bmp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "unknown"


def declared_format_from_filename(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "pdf": "pdf",
        "webp": "webp",
        "bmp": "bmp",
        "gif": "gif",
    }.get(ext, ext or "unknown")


# Markers with no payload / length field.
_NO_LENGTH_MARKERS = {0xD8, 0xD9, 0x01} | set(range(0xD0, 0xD8))  # SOI, EOI, TEM, RSTn
_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def walk_jpeg(data: bytes) -> JpegContainer:
    """Walk a JPEG from SOI to EOI, recording every marker segment.

    After EOI, any remaining bytes are recorded as trailing_byte_count —
    a common hidden-payload vector.
    """
    container = JpegContainer()
    n = len(data)
    if n < 4 or data[0:2] != b"\xff\xd8":
        container.truncated = True
        return container

    i = 2
    in_scan = False
    eoi_offset = None

    while i < n - 1:
        if data[i] != 0xFF:
            # Not aligned on a marker — bail defensively rather than loop forever.
            break

        # Skip fill bytes (multiple 0xFF before the real marker byte).
        j = i + 1
        while j < n and data[j] == 0xFF:
            j += 1
        if j >= n:
            container.truncated = True
            break
        marker_byte = data[j]
        marker = 0xFF00 | marker_byte
        offset = i

        if marker_byte == 0xD9:  # EOI
            eoi_offset = j + 1
            break

        if marker_byte in _NO_LENGTH_MARKERS:
            i = j + 1
            continue

        if j + 3 > n:
            container.truncated = True
            break
        length = (data[j + 1] << 8) | data[j + 2]
        payload_start = j + 3
        payload_end = j + 1 + length
        if payload_end > n:
            container.truncated = True
            break
        payload = data[payload_start:payload_end]
        container.segments.append(JpegSegment(marker=marker, offset=offset, length=length, data=payload))

        if marker_byte in _SOF_MARKERS:
            container.sof_marker = marker
            container.is_progressive = marker_byte == 0xC2
            if len(payload) >= 6:
                container.height = (payload[1] << 8) | payload[2]
                container.width = (payload[3] << 8) | payload[4]
                num_components = payload[5]
                container.num_components = num_components
                comp_offset = 6
                for c in range(num_components):
                    base = comp_offset + c * 3
                    if base + 1 < len(payload):
                        comp_id = payload[base]
                        sampling = payload[base + 1]
                        h_samp = (sampling >> 4) & 0x0F
                        v_samp = sampling & 0x0F
                        container.component_sampling[comp_id] = (h_samp, v_samp)

        if marker_byte == 0xDA:  # SOS — entropy-coded data follows
            i = payload_end
            in_scan = True
            # Scan forward for the next real marker, honouring byte-stuffing
            # (FF 00) and restart markers (FFD0-D7), which appear inside
            # compressed scan data and are not segment boundaries.
            k = i
            while k < n - 1:
                if data[k] == 0xFF:
                    nxt = data[k + 1]
                    if nxt == 0x00:
                        k += 2
                        continue
                    if 0xD0 <= nxt <= 0xD7:
                        k += 2
                        continue
                    if nxt == 0xFF:
                        k += 1
                        continue
                    # Real marker found — resume the outer walk here.
                    break
                k += 1
            i = k
            in_scan = False
            continue

        i = payload_end

    if eoi_offset is not None:
        container.trailing_byte_count = max(0, n - eoi_offset)
    elif not container.truncated:
        # Ran off the end without an explicit EOI.
        container.truncated = True

    return container


def walk_png(data: bytes) -> PngContainer:
    """Walk PNG chunks: length(4) | type(4) | data | crc(4)."""
    container = PngContainer()
    n = len(data)
    if n < 8 or data[:8] != MAGIC_PNG:
        container.truncated = True
        return container

    i = 8
    seen_iend = False
    while i + 8 <= n:
        length = int.from_bytes(data[i : i + 4], "big")
        ctype = data[i + 4 : i + 8].decode("ascii", errors="replace")
        data_start = i + 8
        data_end = data_start + length
        if data_end + 4 > n:
            container.truncated = True
            break
        chunk_data = data[data_start:data_end]
        container.chunks.append(PngChunk(type=ctype, offset=i, data=chunk_data))

        if ctype == "IHDR" and len(chunk_data) >= 8:
            container.width = int.from_bytes(chunk_data[0:4], "big")
            container.height = int.from_bytes(chunk_data[4:8], "big")

        i = data_end + 4  # skip CRC
        if ctype == "IEND":
            seen_iend = True
            break

    if seen_iend:
        container.trailing_byte_count = max(0, n - i)
    elif not container.truncated:
        container.truncated = True

    return container
