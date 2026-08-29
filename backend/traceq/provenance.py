"""Provenance extraction: C2PA manifests, EXIF (all IFDs), ICC profiles.

All of this is done by walking raw bytes — TIFF/IFD structure for EXIF,
JUMBF box structure (+ CBOR/JSON payload decode) for C2PA, and the ICC
profile tag table for ICC. No metadata library wrapper is used, because
Pillow drops exactly the segments this module needs (PNG eXIf, JPEG
APP11/JUMBF).
"""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .container import JpegSegment, PngChunk
from .models import C2PAData, ExifData, GPSInfo, ICCData

try:
    import cbor2
except ImportError:  # pragma: no cover
    cbor2 = None


# ---------------------------------------------------------------------------
# EXIF / TIFF
# ---------------------------------------------------------------------------

_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

_IFD0_TAGS = {
    0x010F: "Make",
    0x0110: "Model",
    0x0131: "Software",
    0x0132: "DateTime",
    0x8769: "ExifIFDPointer",
    0x8825: "GPSInfoIFDPointer",
}
_EXIF_SUBIFD_TAGS = {
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x8827: "ISOSpeedRatings",
    0x8833: "ISOSpeedRatings",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0x9290: "SubSecTime",
    0x9291: "SubSecTimeOriginal",
    0x9292: "SubSecTimeDigitized",
    0xA420: "ImageUniqueID",
}
_GPS_TAGS = {1: "GPSLatitudeRef", 2: "GPSLatitude", 3: "GPSLongitudeRef", 4: "GPSLongitude"}
_THUMBNAIL_TAGS = {0x0201: "JPEGInterchangeFormat", 0x0202: "JPEGInterchangeFormatLength"}


def _read_ifd(tiff: bytes, offset: int, order: str) -> tuple[dict[int, object], int]:
    entries: dict[int, object] = {}
    if offset + 2 > len(tiff):
        return entries, 0
    count = struct.unpack_from(order + "H", tiff, offset)[0]
    pos = offset + 2
    for _ in range(count):
        if pos + 12 > len(tiff):
            break
        tag, type_, cnt = struct.unpack_from(order + "HHI", tiff, pos)
        raw4 = tiff[pos + 8 : pos + 12]
        size_each = _TYPE_SIZES.get(type_, 1)
        total = size_each * cnt
        value_bytes = raw4 if total <= 4 else tiff[
            struct.unpack_from(order + "I", raw4)[0] : struct.unpack_from(order + "I", raw4)[0] + total
        ]
        entries[tag] = _decode_value(value_bytes, type_, cnt, order)
        pos += 12
    next_offset = 0
    if pos + 4 <= len(tiff):
        next_offset = struct.unpack_from(order + "I", tiff, pos)[0]
    return entries, next_offset


def _decode_value(value_bytes: bytes, type_: int, count: int, order: str):
    try:
        if type_ == 2:  # ASCII
            return value_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")
        if type_ == 3:  # SHORT
            vals = struct.unpack_from(order + "H" * count, value_bytes)
        elif type_ == 4:  # LONG
            vals = struct.unpack_from(order + "I" * count, value_bytes)
        elif type_ == 5:  # RATIONAL
            vals = []
            for i in range(count):
                num, den = struct.unpack_from(order + "II", value_bytes, i * 8)
                vals.append(num / den if den else 0.0)
            vals = tuple(vals)
        elif type_ == 9:  # SLONG
            vals = struct.unpack_from(order + "i" * count, value_bytes)
        elif type_ == 10:  # SRATIONAL
            vals = []
            for i in range(count):
                num, den = struct.unpack_from(order + "ii", value_bytes, i * 8)
                vals.append(num / den if den else 0.0)
            vals = tuple(vals)
        elif type_ == 1:  # BYTE
            vals = tuple(value_bytes[:count])
        else:
            return value_bytes.hex()
        return vals[0] if len(vals) == 1 else list(vals)
    except (struct.error, ZeroDivisionError):
        return None


def _gps_to_decimal(dms, ref) -> float | None:
    try:
        deg, minute, sec = dms
        val = deg + minute / 60 + sec / 3600
        if ref in ("S", "W"):
            val = -val
        return val
    except (TypeError, ValueError):
        return None


def parse_exif(tiff_bytes: bytes) -> ExifData:
    """Parse raw TIFF/EXIF bytes (the payload after the 'Exif\\0\\0' marker
    in a JPEG APP1 segment, or the full content of a PNG eXIf chunk)."""
    if len(tiff_bytes) < 8 or tiff_bytes[0:2] not in (b"II", b"MM"):
        return ExifData(present=False)

    order = "<" if tiff_bytes[0:2] == b"II" else ">"
    ifd0_offset = struct.unpack_from(order + "I", tiff_bytes, 4)[0]
    ifd0, ifd1_offset = _read_ifd(tiff_bytes, ifd0_offset, order)

    exif_sub: dict[int, object] = {}
    if 0x8769 in ifd0:
        exif_sub, _ = _read_ifd(tiff_bytes, ifd0[0x8769], order)

    has_gps = 0x8825 in ifd0
    gps_info = None
    if has_gps:
        gps_ifd, _ = _read_ifd(tiff_bytes, ifd0[0x8825], order)
        lat = _gps_to_decimal(gps_ifd.get(2), gps_ifd.get(1)) if 2 in gps_ifd else None
        lon = _gps_to_decimal(gps_ifd.get(4), gps_ifd.get(3)) if 4 in gps_ifd else None
        if lat is not None or lon is not None:
            gps_info = GPSInfo(latitude=lat, longitude=lon)

    has_thumbnail = ifd1_offset != 0
    if has_thumbnail:
        ifd1, _ = _read_ifd(tiff_bytes, ifd1_offset, order)
        has_thumbnail = has_thumbnail and (0x0201 in ifd1 or len(ifd1) > 0)

    def fmt_rat(v):
        return f"1/{round(1/v)}" if isinstance(v, (int, float)) and v else None

    raw: dict = {}
    for tag, name in {**_IFD0_TAGS, **_EXIF_SUBIFD_TAGS}.items():
        src = ifd0 if tag in _IFD0_TAGS else exif_sub
        if tag in src:
            raw[name] = src[tag]

    return ExifData(
        present=True,
        make=ifd0.get(0x010F),
        model=ifd0.get(0x0110),
        software=ifd0.get(0x0131),
        datetime_original=exif_sub.get(0x9003) or ifd0.get(0x0132),
        exposure_time=fmt_rat(exif_sub.get(0x829A)) if isinstance(exif_sub.get(0x829A), float) else exif_sub.get(0x829A),
        fnumber=exif_sub.get(0x829D) if isinstance(exif_sub.get(0x829D), (int, float)) else None,
        iso=exif_sub.get(0x8827) if isinstance(exif_sub.get(0x8827), int) else None,
        has_gps_ifd=has_gps,
        has_thumbnail_ifd=has_thumbnail,
        subsec_time=exif_sub.get(0x9291) or exif_sub.get(0x9290),
        gps=gps_info,
        raw=raw,
    )


def extract_exif_from_jpeg(segments: list[JpegSegment]) -> ExifData:
    for seg in segments:
        if seg.marker == 0xFFE1 and seg.data[:6] == b"Exif\x00\x00":
            return parse_exif(seg.data[6:])
    return ExifData(present=False)


def extract_exif_from_png(chunks: list[PngChunk]) -> ExifData:
    for chunk in chunks:
        if chunk.type == "eXIf":
            data = chunk.data
            # Per the PNG eXIf spec this is raw TIFF data (no "Exif\0\0"
            # prefix), but some encoders carry it over from the JPEG
            # convention anyway — strip it defensively if present.
            if data[:6] == b"Exif\x00\x00":
                data = data[6:]
            return parse_exif(data)
    return ExifData(present=False)


# ---------------------------------------------------------------------------
# ICC profiles
# ---------------------------------------------------------------------------

def _read_icc_text_tag(block: bytes) -> str | None:
    if len(block) < 8:
        return None
    type_sig = block[0:4].decode("ascii", errors="replace")
    try:
        if type_sig == "text":
            return block[8:].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        if type_sig == "desc" and len(block) >= 12:
            count = struct.unpack_from(">I", block, 8)[0]
            return block[12 : 12 + count].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        if type_sig == "mluc" and len(block) >= 16:
            rec_base = 16
            length = struct.unpack_from(">I", block, rec_base + 4)[0]
            rec_offset = struct.unpack_from(">I", block, rec_base + 8)[0]
            s = block[rec_offset : rec_offset + length]
            return s.decode("utf-16-be", errors="replace").strip("\x00").strip()
    except (struct.error, UnicodeDecodeError):
        return None
    return None


def parse_icc_profile(data: bytes) -> ICCData:
    if len(data) < 132:
        return ICCData(present=len(data) > 0)
    tag_count = struct.unpack_from(">I", data, 128)[0]
    tags: dict[str, tuple[int, int]] = {}
    for i in range(tag_count):
        base = 132 + i * 12
        if base + 12 > len(data):
            break
        sig = data[base : base + 4].decode("ascii", errors="replace")
        offset, size = struct.unpack_from(">II", data, base + 4)
        tags[sig] = (offset, size)

    def read(sig: str) -> str | None:
        if sig not in tags:
            return None
        offset, size = tags[sig]
        if offset + size > len(data):
            return None
        return _read_icc_text_tag(data[offset : offset + size])

    return ICCData(present=True, description=read("desc"), copyright=read("cprt"))


def extract_icc_from_jpeg(segments: list[JpegSegment]) -> ICCData:
    app2 = [s for s in segments if s.marker == 0xFFE2 and s.data[:12] == b"ICC_PROFILE\x00"]
    if not app2:
        return ICCData(present=False)
    chunks = []
    for seg in app2:
        # ICC_PROFILE\0 + seq(1) + count(1) + profile chunk
        if len(seg.data) > 14:
            seq = seg.data[12]
            chunks.append((seq, seg.data[14:]))
    chunks.sort(key=lambda c: c[0])
    profile = b"".join(c[1] for c in chunks)
    return parse_icc_profile(profile)


def extract_icc_from_png(chunks: list[PngChunk]) -> ICCData:
    for chunk in chunks:
        if chunk.type == "iCCP":
            try:
                name_end = chunk.data.index(b"\x00")
                compressed = chunk.data[name_end + 2 :]
                profile = zlib.decompress(compressed)
                return parse_icc_profile(profile)
            except (ValueError, zlib.error):
                return ICCData(present=True)
        if chunk.type == "sRGB":
            return ICCData(present=True, description="sRGB (embedded sRGB chunk)")
    return ICCData(present=False)


# ---------------------------------------------------------------------------
# C2PA / JUMBF
# ---------------------------------------------------------------------------

@dataclass
class JumbfBox:
    type: str
    payload: bytes
    label: str | None = None
    children: list["JumbfBox"] = field(default_factory=list)


def _parse_jumd_label(payload: bytes) -> str | None:
    if len(payload) < 17:
        return None
    toggles = payload[16]
    if not (toggles & 0x01):
        return None
    idx = 17
    end = payload.find(b"\x00", idx)
    if end == -1:
        return None
    return payload[idx:end].decode("utf-8", errors="replace")


def parse_jumbf_boxes(data: bytes, _depth: int = 0) -> list[JumbfBox]:
    if _depth > 12:
        return []
    boxes: list[JumbfBox] = []
    i, n = 0, len(data)
    while i + 8 <= n:
        length = int.from_bytes(data[i : i + 4], "big")
        btype = data[i + 4 : i + 8].decode("ascii", errors="replace")
        if length == 1:
            if i + 16 > n:
                break
            ext_len = int.from_bytes(data[i + 8 : i + 16], "big")
            payload = data[i + 16 : min(i + ext_len, n)]
            i += ext_len
        elif length == 0:
            payload = data[i + 8 : n]
            i = n
        else:
            end = min(i + length, n)
            payload = data[i + 8 : end]
            i = end
        box = JumbfBox(type=btype, payload=payload)
        if btype == "jumb":
            box.children = parse_jumbf_boxes(payload, _depth + 1)
            for child in box.children:
                if child.type == "jumd":
                    box.label = _parse_jumd_label(child.payload)
                    break
        boxes.append(box)
        if length <= 0:
            break
    return boxes


def _collect_leaf_payloads(boxes: list[JumbfBox], parent_label: str | None = None) -> list[tuple[str, str | None, bytes]]:
    out: list[tuple[str, str | None, bytes]] = []
    for box in boxes:
        if box.type == "jumb":
            out.extend(_collect_leaf_payloads(box.children, box.label))
        elif box.type in ("cbor", "json", "bfdb"):
            out.append((box.type, parent_label, box.payload))
    return out


_INTERESTING_KEYS = {
    "claim_generator",
    "claim_generator_info",
    "softwareAgent",
    "digitalSourceType",
    "generator",
    "when",
    "instanceId",
}


def _search_keys(obj, found: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _INTERESTING_KEYS and k not in found:
                found[k] = v
            _search_keys(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _search_keys(item, found)


def reassemble_c2pa_jumbf_from_jpeg(segments: list[JpegSegment]) -> bytes | None:
    app11 = [s for s in segments if s.marker == 0xFFEB]
    if not app11:
        return None
    groups: dict[int, list[tuple[int, bytes]]] = {}
    for seg in app11:
        d = seg.data
        if len(d) < 8 or d[0:2] != b"JP":
            continue
        en = int.from_bytes(d[2:4], "big")
        z = int.from_bytes(d[4:8], "big")
        groups.setdefault(en, []).append((z, d[8:]))
    if not groups:
        return None
    for en, parts in groups.items():
        parts.sort(key=lambda t: t[0])
        stream = b"".join(p[1] for p in parts)
        if len(stream) >= 8 and stream[4:8] == b"jumb":
            return stream
    en0 = next(iter(groups))
    parts = sorted(groups[en0], key=lambda t: t[0])
    return b"".join(p[1] for p in parts)


def _parse_manifest_stream(stream: bytes) -> C2PAData:
    boxes = parse_jumbf_boxes(stream)
    if not boxes:
        return C2PAData(present=False)

    leaves = _collect_leaf_payloads(boxes)
    found: dict = {}
    labels: set[str] = set()

    def collect_labels(bs: list[JumbfBox]):
        for b in bs:
            if b.label:
                labels.add(b.label)
            collect_labels(b.children)

    collect_labels(boxes)

    for box_type, parent_label, payload in leaves:
        decoded = None
        try:
            if box_type == "cbor" and cbor2 is not None:
                decoded = cbor2.loads(payload)
            elif box_type == "json":
                decoded = json.loads(payload.decode("utf-8", errors="replace"))
        except Exception:
            decoded = None
        if decoded is not None:
            _search_keys(decoded, found)

    generator_info = found.get("claim_generator_info")
    generator_name = None
    if isinstance(generator_info, list) and generator_info:
        first = generator_info[0]
        if isinstance(first, dict):
            generator_name = first.get("name")
    software_agent = found.get("softwareAgent")
    if isinstance(software_agent, dict):
        software_agent = software_agent.get("name")

    timestamp = None
    when = found.get("when")
    if isinstance(when, str):
        try:
            timestamp = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            timestamp = None

    return C2PAData(
        present=True,
        valid=None,  # cryptographic signature verification is out of scope; see README
        software_agent=software_agent if isinstance(software_agent, str) else generator_name,
        digital_source_type=found.get("digitalSourceType") if isinstance(found.get("digitalSourceType"), str) else None,
        generator=generator_name or (software_agent if isinstance(software_agent, str) else None),
        timestamp=timestamp,
        claim_generator=found.get("claim_generator") if isinstance(found.get("claim_generator"), str) else None,
        assertions=sorted(labels),
    )


def extract_c2pa_from_jpeg(segments: list[JpegSegment]) -> C2PAData:
    stream = reassemble_c2pa_jumbf_from_jpeg(segments)
    if stream is None:
        return C2PAData(present=False)
    try:
        return _parse_manifest_stream(stream)
    except Exception:
        return C2PAData(present=True, valid=None)


def extract_c2pa_from_png(chunks: list[PngChunk]) -> C2PAData:
    for chunk in chunks:
        if chunk.type == "caBX":
            try:
                return _parse_manifest_stream(chunk.data)
            except Exception:
                return C2PAData(present=True, valid=None)
    return C2PAData(present=False)
