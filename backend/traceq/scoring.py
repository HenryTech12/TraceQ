"""Trace Score — Section 5 of the build spec.

The Trace Score measures how much verifiable history survives, NOT how
likely the content is to be AI-generated. It is a plain sum of
deterministic, independently-checkable facts. Nothing here reads
ForensicStats — pixel statistics never contribute to the score.
"""
from __future__ import annotations

from .models import FileRecord, TraceScore

_MAX = 100


def compute_trace_score(record: FileRecord) -> TraceScore:
    breakdown: dict[str, int] = {}

    if record.c2pa.present:
        breakdown["valid_c2pa_manifest_present"] = 40

    has_coherent_exposure_triangle = (
        record.exif.present
        and bool(record.exif.make)
        and bool(record.exif.model)
        and record.exif.exposure_time is not None
        and record.exif.fnumber is not None
        and record.exif.iso is not None
    )
    if has_coherent_exposure_triangle:
        breakdown["full_camera_exif_coherent_exposure_triangle"] = 25

    if record.exif.has_thumbnail_ifd:
        breakdown["thumbnail_ifd_present"] = 10

    if record.icc.present and record.icc.copyright:
        breakdown["icc_profile_known_vendor_pipeline"] = 10

    if not record.format_mismatch:
        breakdown["no_format_extension_mismatch"] = 10

    if record.trailing_byte_count == 0:
        breakdown["no_trailing_bytes_after_eoi"] = 5

    value = min(sum(breakdown.values()), _MAX)
    return TraceScore(value=value, max_value=_MAX, breakdown=breakdown, label=_label_for(value))


def _label_for(value: int) -> str:
    if value == 0:
        return f"Trace Score: {value}/100 — no verifiable provenance data survives in this file."
    if value < 30:
        return f"Trace Score: {value}/100 — most provenance data has been stripped from this file."
    if value < 70:
        return f"Trace Score: {value}/100 — partial provenance history survives."
    return f"Trace Score: {value}/100 — strong verifiable history survives."
