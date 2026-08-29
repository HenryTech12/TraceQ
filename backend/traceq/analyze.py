"""Orchestrator: raw file bytes in, AnalysisResult out.

Wires container -> provenance -> encoder -> pipeline -> hashes -> stats ->
matching -> scoring into a single FileRecord, then applies the exact
three-state verdict contract from Section 5 of the build spec.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from . import container, encoder as encoder_mod, hashes as hashes_mod
from . import matching, pipeline as pipeline_mod, provenance, scoring, stats as stats_mod
from .models import (
    AnalysisResult,
    C2PAData,
    DerivationInfo,
    EncoderFingerprint,
    ExifData,
    FileRecord,
    ForensicStats,
    ICCData,
    Observations,
    Verdict,
)

_RASTER_FORMATS = {"jpeg", "png", "webp", "bmp", "gif"}


def _extract_pdf_info(data: bytes) -> pipeline_mod.PdfInfo | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return None

    meta = reader.metadata
    producer = getattr(meta, "producer", None) if meta else None
    creator = getattr(meta, "creator", None) if meta else None

    fonts: list[tuple[str, bool]] = []
    try:
        for page in reader.pages:
            resources = page.get("/Resources")
            if not resources:
                continue
            font_dict = resources.get("/Font")
            if not font_dict:
                continue
            for font_ref in font_dict.values():
                font_obj = font_ref.get_object()
                base_font = str(font_obj.get("/BaseFont", "")).lstrip("/")
                if "+" in base_font:
                    base_font = base_font.split("+", 1)[1]
                descriptor = font_obj.get("/FontDescriptor")
                embedded = False
                if descriptor is not None:
                    d = descriptor.get_object()
                    embedded = any(k in d for k in ("/FontFile", "/FontFile2", "/FontFile3"))
                fonts.append((base_font, embedded))
    except Exception:
        pass

    return pipeline_mod.PdfInfo(producer=producer, creator=creator, fonts=fonts)


def _extract_container_evidence(data: bytes, actual_format: str):
    """Returns (exif, icc, c2pa, encoder_fp, trailing_byte_count, width, height, pdf_info)."""
    if actual_format == "jpeg":
        jc = container.walk_jpeg(data)
        exif = provenance.extract_exif_from_jpeg(jc.segments)
        icc = provenance.extract_icc_from_jpeg(jc.segments)
        c2pa = provenance.extract_c2pa_from_jpeg(jc.segments)
        enc_fp = encoder_mod.extract_encoder_fingerprint(jc)
        return exif, icc, c2pa, enc_fp, jc.trailing_byte_count, jc.width, jc.height, None
    if actual_format == "png":
        pc = container.walk_png(data)
        exif = provenance.extract_exif_from_png(pc.chunks)
        icc = provenance.extract_icc_from_png(pc.chunks)
        c2pa = provenance.extract_c2pa_from_png(pc.chunks)
        return exif, icc, c2pa, EncoderFingerprint(), pc.trailing_byte_count, pc.width, pc.height, None
    if actual_format == "pdf":
        pdf_info = _extract_pdf_info(data)
        return ExifData(), ICCData(), C2PAData(), EncoderFingerprint(), 0, None, None, pdf_info
    return ExifData(), ICCData(), C2PAData(), EncoderFingerprint(), 0, None, None, None


def analyze_file(
    data: bytes,
    filename: str,
    prior_files: list[matching.StoredFile] | None = None,
) -> AnalysisResult:
    """Convenience entry point (CLI, tests) that discards the ORB
    descriptor matrix computed along the way. Session-aware callers that
    need to persist it for future crop-matching should use
    analyze_file_with_descriptors instead."""
    result, _descriptors = analyze_file_with_descriptors(data, filename, prior_files)
    return result


def analyze_file_with_descriptors(
    data: bytes,
    filename: str,
    prior_files: list[matching.StoredFile] | None = None,
) -> tuple[AnalysisResult, np.ndarray | None]:
    prior_files = prior_files or []

    sha = hashes_mod.compute_sha256(data)
    actual_format = container.detect_actual_format(data)
    declared_format = container.declared_format_from_filename(filename)
    format_mismatch = (
        actual_format != "unknown" and declared_format != "unknown" and actual_format != declared_format
    )

    exif, icc, c2pa, enc_fp, trailing, width, height, pdf_info = _extract_container_evidence(data, actual_format)

    min_flat_std = None
    forensic_stats = ForensicStats()
    phashes: dict[str, str] = {}
    orb_descriptors: np.ndarray | None = None

    if actual_format in _RASTER_FORMATS:
        pil_image = None
        try:
            pil_image = Image.open(io.BytesIO(data))
            pil_image.load()
        except Exception:
            pil_image = None
        if pil_image is not None:
            if width is None:
                width, height = pil_image.size
            try:
                min_flat_std = stats_mod.compute_min_flat_region_std(pil_image)
            except Exception:
                min_flat_std = None
            try:
                forensic_stats = stats_mod.compute_forensic_stats(pil_image)
            except Exception:
                pass
            try:
                phashes = hashes_mod.compute_perceptual_hashes(pil_image)
            except Exception:
                phashes = {}
            try:
                orb_descriptors = hashes_mod.compute_orb_descriptors(pil_image)
            except Exception:
                orb_descriptors = None

    evidence = pipeline_mod.Evidence(
        actual_format=actual_format,
        declared_format=declared_format,
        format_mismatch=format_mismatch,
        exif=exif,
        icc=icc,
        c2pa=c2pa,
        encoder=enc_fp,
        trailing_byte_count=trailing,
        min_flat_region_std=min_flat_std,
        pdf=pdf_info,
    )
    pipeline_matches = pipeline_mod.classify_pipelines(evidence)

    record = FileRecord(
        sha256=sha,
        declared_format=declared_format,
        actual_format=actual_format,
        format_mismatch=format_mismatch,
        file_size=len(data),
        width=width,
        height=height,
        c2pa=c2pa,
        exif=exif,
        icc=icc,
        encoder=enc_fp,
        trailing_byte_count=trailing,
        min_flat_region_std=min_flat_std,
        pipeline_matches=pipeline_matches,
        phash=phashes.get("phash"),
        dhash=phashes.get("dhash"),
        ahash=phashes.get("ahash"),
        whash=phashes.get("whash"),
        orb_descriptor_count=None if orb_descriptors is None else len(orb_descriptors),
        stats=forensic_stats,
    )

    verdict, verdict_statement, derivation = _determine_verdict(record, orb_descriptors, prior_files)
    trace_score = scoring.compute_trace_score(record)

    observations = Observations(
        pipeline_inference=pipeline_matches,
        transformations_detected=derivation.transformations_detected if derivation else [],
        format_mismatch=format_mismatch,
        embedded_credentials={
            "c2pa_present": c2pa.present,
            "exif_present": exif.present,
            "icc_present": icc.present,
        },
    )

    result = AnalysisResult(
        file_id=sha[:16],
        filename=filename,
        verdict=verdict,
        verdict_statement=verdict_statement,
        trace_score=trace_score,
        record=record,
        derivation=derivation,
        observations=observations,
    )
    return result, orb_descriptors


def _determine_verdict(
    record: FileRecord, orb_descriptors: np.ndarray | None, prior_files: list[matching.StoredFile]
) -> tuple[Verdict, str, DerivationInfo | None]:
    exif, c2pa = record.exif, record.c2pa

    has_coherent_camera_exif = (
        exif.present
        and bool(exif.make)
        and bool(exif.model)
        and exif.exposure_time is not None
        and exif.fnumber is not None
        and exif.iso is not None
    )

    if c2pa.present:
        parts = ["Cryptographically signed"]
        agent = c2pa.generator or c2pa.software_agent
        if agent:
            parts.append(f"by {agent}")
        statement = " ".join(parts) + "."
        if c2pa.digital_source_type:
            statement += f" Declared as AI-generated ({c2pa.digital_source_type})."
        if c2pa.timestamp:
            statement += f" Signed {c2pa.timestamp.date().isoformat()}."
        return Verdict.VERIFIED_ORIGIN, statement, None

    if has_coherent_camera_exif:
        bits = [f"Captured on {exif.make} {exif.model}."]
        triangle = []
        if exif.iso:
            triangle.append(f"ISO {exif.iso}")
        if exif.exposure_time:
            triangle.append(str(exif.exposure_time))
        if exif.fnumber:
            triangle.append(f"f/{exif.fnumber}")
        if triangle:
            bits.append(", ".join(triangle) + " — consistent with a coherent exposure triangle.")
        if exif.has_thumbnail_ifd:
            bits.append("Thumbnail IFD present.")
        return Verdict.VERIFIED_ORIGIN, " ".join(bits), None

    match = matching.find_best_match(record, orb_descriptors, prior_files)
    if match is not None:
        parent, metric, hash_type = match
        transforms = matching.detect_transformations(record, parent)
        derivation = DerivationInfo(
            parent_sha256=parent.sha256,
            parent_filename=parent.filename,
            transformations_detected=transforms,
            hash_distance=metric,
            hash_type=hash_type,
        )
        evidence_note = (
            f"{metric} matching local features (ORB)" if hash_type == "orb_features" else f"{hash_type} distance {metric}"
        )
        statement = (
            f"Matches '{parent.filename}' uploaded earlier this session ({', '.join(transforms)}; {evidence_note})."
        )
        return Verdict.DERIVED, statement, derivation

    statement = (
        "No chain of custody found for this file. Content credentials are "
        "commonly removed by screenshots, messaging apps, and re-encoding."
    )
    return Verdict.NO_RECORD, statement, None
