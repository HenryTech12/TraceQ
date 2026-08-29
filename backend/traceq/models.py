"""Pydantic models for TraceQ's evidence records, verdicts, and API payloads.

These are data contracts, not opinions: everything under `stats` is
diagnostic-only and must never feed a verdict or the Trace Score
(see traceq/scoring.py and Section 5 of the build spec).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    VERIFIED_ORIGIN = "VERIFIED_ORIGIN"  # cryptographic or camera evidence found
    DERIVED = "DERIVED"                  # matches an earlier file this session
    NO_RECORD = "NO_RECORD"              # no chain of custody found


class PipelineMatch(BaseModel):
    name: str
    confidence: str  # "high" | "medium" | "low"
    basis: list[str]


class ForensicStats(BaseModel):
    """Diagnostics only. Never used in scoring or verdicts."""

    mean_residual_noise: float | None = None
    chromatic_aberration_px: float | None = None
    note: str = (
        "Pixel statistics are logged for transparency only. They do not "
        "drive any verdict or score — see empirical failure modes in the "
        "TraceQ build spec (texture confound, chromatic aberration inversion)."
    )


class GPSInfo(BaseModel):
    latitude: float | None = None
    longitude: float | None = None


class ExifData(BaseModel):
    present: bool = False
    make: str | None = None
    model: str | None = None
    software: str | None = None
    datetime_original: str | None = None
    exposure_time: str | None = None
    fnumber: float | None = None
    iso: int | None = None
    has_gps_ifd: bool = False
    has_thumbnail_ifd: bool = False
    subsec_time: str | None = None
    gps: GPSInfo | None = None
    raw: dict = Field(default_factory=dict)


class C2PAData(BaseModel):
    present: bool = False
    valid: bool | None = None
    software_agent: str | None = None
    digital_source_type: str | None = None
    generator: str | None = None
    timestamp: datetime | None = None
    claim_generator: str | None = None
    assertions: list[str] = Field(default_factory=list)


class ICCData(BaseModel):
    present: bool = False
    description: str | None = None
    copyright: str | None = None


class EncoderFingerprint(BaseModel):
    quant_table_luma: list[int] | None = None
    quant_table_chroma: list[int] | None = None
    quant_tables_identical: bool = False
    is_progressive: bool = False
    chroma_subsampling: str | None = None


class FileRecord(BaseModel):
    sha256: str
    declared_format: str
    actual_format: str
    format_mismatch: bool
    file_size: int
    width: int | None = None
    height: int | None = None

    # Provenance
    c2pa: C2PAData = Field(default_factory=C2PAData)
    exif: ExifData = Field(default_factory=ExifData)
    icc: ICCData = Field(default_factory=ICCData)

    # Encoder fingerprint
    encoder: EncoderFingerprint = Field(default_factory=EncoderFingerprint)
    trailing_byte_count: int = 0

    # Screen-capture detector
    min_flat_region_std: float | None = None

    # Pipeline inference
    pipeline_matches: list[PipelineMatch] = Field(default_factory=list)

    # Matching
    phash: str | None = None
    dhash: str | None = None
    ahash: str | None = None
    whash: str | None = None
    orb_descriptor_count: int | None = None

    # Diagnostics ONLY — never used in scoring
    stats: ForensicStats = Field(default_factory=ForensicStats)


class DerivationInfo(BaseModel):
    parent_sha256: str
    parent_filename: str | None = None
    transformations_detected: list[str] = Field(default_factory=list)
    hash_distance: int
    hash_type: str


class TraceScore(BaseModel):
    value: int
    max_value: int = 100
    label: str
    breakdown: dict[str, int] = Field(default_factory=dict)


class Observations(BaseModel):
    pipeline_inference: list[PipelineMatch] = Field(default_factory=list)
    transformations_detected: list[str] = Field(default_factory=list)
    format_mismatch: bool = False
    embedded_credentials: dict = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    file_id: str
    filename: str
    verdict: Verdict
    verdict_statement: str
    trace_score: TraceScore
    record: FileRecord
    derivation: DerivationInfo | None = None
    observations: Observations


class GraphNode(BaseModel):
    id: str
    filename: str
    verdict: Verdict
    badges: list[str] = Field(default_factory=list)
    trace_score: int


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str


class SessionGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
