"""Pipeline Fingerprint Library — Section 3 of the build spec.

This is the heart of the demo. Every rule here is an explicit, auditable
boolean check against verified bytes (EXIF fields, ICC copyright strings,
quantization tables, C2PA claims, PDF producer strings). No ML, no
statistics, no confidence guessing — a rule either matches its documented
signature or it doesn't. Rules degrade gracefully: a partial match is
simply not reported rather than reported with fabricated confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import C2PAData, EncoderFingerprint, ExifData, ICCData, PipelineMatch

_BASE14_FONTS = {
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}


@dataclass
class PdfInfo:
    producer: str | None = None
    creator: str | None = None
    fonts: list[tuple[str, bool]] = field(default_factory=list)  # (base_font_name, embedded)


@dataclass
class Evidence:
    actual_format: str
    declared_format: str
    format_mismatch: bool
    exif: ExifData
    icc: ICCData
    c2pa: C2PAData
    encoder: EncoderFingerprint
    trailing_byte_count: int
    min_flat_region_std: float | None
    pdf: PdfInfo | None = None


def _rule_whatsapp(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "jpeg":
        return None
    if not (e.encoder.is_progressive and e.encoder.quant_tables_identical and not e.exif.present and not e.icc.present):
        return None
    return PipelineMatch(
        name="whatsapp_transmission",
        confidence="high",
        basis=[
            "progressive JPEG (SOF2)",
            "luma and chroma quantization tables byte-identical",
            "no EXIF present",
            "no ICC profile present",
        ],
    )


def _rule_android_screenshot(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "png":
        return None
    software = e.exif.software or ""
    if not e.exif.present or "android" not in software.lower():
        return None
    basis = [f"PNG eXIf chunk with Software: {software}"]
    if e.exif.datetime_original:
        basis.append("DateTimeOriginal present")
    if e.exif.raw.get("ImageUniqueID"):
        basis.append("ImageUniqueID present")
    return PipelineMatch(name="android_screenshot", confidence="high", basis=basis)


def _rule_android_camera_reshared(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "jpeg":
        return None
    copyright_ = (e.icc.copyright or "")
    if "google inc" not in copyright_.lower():
        return None
    if e.exif.present or e.encoder.is_progressive:
        return None
    return PipelineMatch(
        name="android_camera_reshared",
        confidence="high",
        basis=[f"ICC profile copyright = '{e.icc.copyright}'", "EXIF stripped", "baseline JPEG"],
    )


def _rule_direct_phone_camera(e: Evidence) -> PipelineMatch | None:
    if not e.exif.present or not (e.exif.make and e.exif.model):
        return None
    triangle = [e.exif.exposure_time, e.exif.fnumber, e.exif.iso]
    if not all(v is not None for v in triangle):
        return None
    basis = [
        f"Make/Model: {e.exif.make} / {e.exif.model}",
        f"exposure triangle present: {e.exif.exposure_time}, f/{e.exif.fnumber}, ISO {e.exif.iso}",
    ]
    confidence = "medium"
    if e.exif.subsec_time:
        basis.append(f"SubSecTime: {e.exif.subsec_time}")
    if e.exif.has_gps_ifd:
        basis.append("GPS IFD present")
    if e.exif.has_thumbnail_ifd:
        basis.append("thumbnail IFD present")
        confidence = "high"
    return PipelineMatch(name="direct_phone_camera", confidence=confidence, basis=basis)


def _rule_near_lossless_export(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "jpeg":
        return None
    tables = [t for t in (e.encoder.quant_table_luma, e.encoder.quant_table_chroma) if t]
    if not tables or not all(v <= 1 for t in tables for v in t):
        return None
    if e.exif.present or e.icc.present:
        return None
    basis = ["all-1 quantization tables (quality ~100)", "no EXIF present", "no ICC profile present"]
    if e.format_mismatch:
        basis.append(f"format/extension mismatch (declared {e.declared_format}, actual {e.actual_format})")
    return PipelineMatch(name="near_lossless_export", confidence="medium", basis=basis)


def _rule_openai_generation(e: Evidence) -> PipelineMatch | None:
    if not e.c2pa.present:
        return None
    agent = (e.c2pa.software_agent or e.c2pa.generator or "").lower()
    source_type = (e.c2pa.digital_source_type or "")
    if "gpt" not in agent and "openai" not in agent and "trainedalgorithmicmedia" not in source_type.lower():
        return None
    basis = [f"C2PA manifest embedded ({'PNG caBX' if e.actual_format == 'png' else 'JPEG APP11 JUMBF'})"]
    if e.c2pa.software_agent:
        basis.append(f"softwareAgent: {e.c2pa.software_agent}")
    if e.c2pa.digital_source_type:
        basis.append(f"digitalSourceType: {e.c2pa.digital_source_type}")
    return PipelineMatch(name="openai_generation", confidence="high", basis=basis)


def _rule_screen_capture(e: Evidence) -> PipelineMatch | None:
    if e.min_flat_region_std is None or e.min_flat_region_std != 0.0:
        return None
    return PipelineMatch(
        name="screen_capture",
        confidence="high",
        basis=["flat region with standard deviation exactly 0.000 (min == max) — framebuffer capture"],
    )


def _rule_reportlab_pdf(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "pdf" or e.pdf is None:
        return None
    if not e.pdf.producer or "reportlab" not in e.pdf.producer.lower():
        return None
    non_embedded_base14 = [name for name, embedded in e.pdf.fonts if not embedded and name in _BASE14_FONTS]
    basis = [f"Producer: {e.pdf.producer}"]
    if non_embedded_base14:
        basis.append(f"non-embedded base-14 fonts: {', '.join(sorted(set(non_embedded_base14)))}")
    return PipelineMatch(name="reportlab_programmatic_pdf", confidence="high", basis=basis)


def _rule_browser_print_pdf(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "pdf" or e.pdf is None:
        return None
    producer = (e.pdf.producer or "").lower()
    creator = (e.pdf.creator or "").lower()
    if "skia/pdf" not in producer or "chromium" not in creator:
        return None
    basis = [f"Producer: {e.pdf.producer}", f"Creator: {e.pdf.creator}"]
    embedded = [name for name, emb in e.pdf.fonts if emb]
    if embedded:
        basis.append(f"embedded subsetted fonts: {', '.join(sorted(set(embedded)))}")
    return PipelineMatch(name="browser_print_to_pdf", confidence="high", basis=basis)


def _rule_ilovepdf(e: Evidence) -> PipelineMatch | None:
    if e.actual_format != "pdf" or e.pdf is None:
        return None
    if not e.pdf.producer or "ilovepdf" not in e.pdf.producer.lower():
        return None
    return PipelineMatch(
        name="ilovepdf_compression",
        confidence="high",
        basis=[f"Producer: {e.pdf.producer} (overwrites the original producer string)"],
    )


_RULES = [
    _rule_openai_generation,  # C2PA is the strongest evidence — check first
    _rule_whatsapp,
    _rule_android_screenshot,
    _rule_android_camera_reshared,
    _rule_direct_phone_camera,
    _rule_near_lossless_export,
    _rule_screen_capture,
    _rule_reportlab_pdf,
    _rule_browser_print_pdf,
    _rule_ilovepdf,
]


def classify_pipelines(evidence: Evidence) -> list[PipelineMatch]:
    matches = []
    for rule in _RULES:
        match = rule(evidence)
        if match is not None:
            matches.append(match)
    return matches
