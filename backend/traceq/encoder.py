"""Encoder fingerprint extraction: quantization tables, subsampling, progressive flag.

These are the bytes that survive a WhatsApp re-encode (fixed quant tables,
fixed progressive-JPEG shape) and distinguish a near-lossless export
(quality ~100, all-1 tables) from a normal camera JPEG.
"""
from __future__ import annotations

from .container import JpegContainer
from .models import EncoderFingerprint

DQT_MARKER = 0xFFDB


def _parse_dqt_tables(segments) -> dict[int, list[int]]:
    tables: dict[int, list[int]] = {}
    for seg in segments:
        if seg.marker != DQT_MARKER:
            continue
        data = seg.data
        i = 0
        while i < len(data):
            pq_tq = data[i]
            precision = pq_tq >> 4
            table_id = pq_tq & 0x0F
            i += 1
            n = 64 * (2 if precision else 1)
            if i + n > len(data):
                break
            if precision:
                values = [int.from_bytes(data[i + 2 * k : i + 2 * k + 2], "big") for k in range(64)]
            else:
                values = list(data[i : i + n])
            tables[table_id] = values
            i += n
    return tables


def _chroma_subsampling(component_sampling: dict[int, tuple[int, int]]) -> str | None:
    if len(component_sampling) < 2:
        return "4:4:4" if component_sampling else None
    ids = sorted(component_sampling.keys())
    luma = component_sampling[ids[0]]
    chroma = component_sampling[ids[1]] if len(ids) > 1 else luma
    if luma == (2, 2) and chroma == (1, 1):
        return "4:2:0"
    if luma == (2, 1) and chroma == (1, 1):
        return "4:2:2"
    if luma == (1, 2) and chroma == (1, 1):
        return "4:4:0"
    if luma == chroma:
        return "4:4:4"
    return f"custom({luma}/{chroma})"


def extract_encoder_fingerprint(container: JpegContainer) -> EncoderFingerprint:
    tables = _parse_dqt_tables(container.segments)
    luma = tables.get(0)
    chroma = tables.get(1)
    identical = luma is not None and chroma is not None and luma == chroma
    return EncoderFingerprint(
        quant_table_luma=luma,
        quant_table_chroma=chroma,
        quant_tables_identical=identical,
        is_progressive=container.is_progressive,
        chroma_subsampling=_chroma_subsampling(container.component_sampling),
    )


def is_near_lossless(fingerprint: EncoderFingerprint) -> bool:
    """All-1 quantization tables ~= quality 100, a signature of export
    tools and 'save for web at max quality', not camera capture."""
    tables = [t for t in (fingerprint.quant_table_luma, fingerprint.quant_table_chroma) if t]
    if not tables:
        return False
    return all(v <= 1 for t in tables for v in t)
