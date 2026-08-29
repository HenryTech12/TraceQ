"""Session-scoped perceptual matching — the DERIVED verdict.

Compares a newly analyzed file's perceptual hash against every file
uploaded earlier in the same session. A close match is what makes the
Content DNA Graph light up: it is direct, deterministic evidence of a
parent/child relationship, not a probabilistic guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .hashes import hash_distance, orb_good_match_count
from .models import FileRecord, PipelineMatch

# Hamming distance threshold for a 64-bit perceptual hash. Below this,
# two images are considered the same underlying content; empirically,
# unrelated images differ by 20+ bits, same-content transformations
# (resize/re-encode, composition preserved) differ by single digits.
#
# Only phash and dhash gate a match — both are structure-aware (DCT
# frequency layout, local gradient direction). ahash/whash are coarse
# brightness-average hashes: measured against synthetic fixtures with
# similar gradients but unrelated content, they false-positived at a
# smaller distance (4) than a genuine crop match scored on the SAME
# algorithm (also ~4) — i.e. no threshold separates true from false
# there. They're still computed and shown in the evidence panel, just
# never used to trigger DERIVED.
MATCH_THRESHOLD = 10

# ORB good-match count (Lowe's-ratio-filtered) required to call two images
# related by local feature correspondence. This is what catches crops,
# where the composition change defeats phash/dhash entirely but the kept
# region's local structure is untouched. Empirically: genuine crop/resize
# pairs scored 66-226 good matches; unrelated pairs scored 0-12 — a wide,
# safe margin at 25.
ORB_MATCH_THRESHOLD = 25


@dataclass
class StoredFile:
    file_id: str
    filename: str
    sha256: str
    phash: str | None
    dhash: str | None = None
    ahash: str | None = None
    whash: str | None = None
    width: int | None = None
    height: int | None = None
    pipeline_matches: list[PipelineMatch] = field(default_factory=list)
    orb_descriptors: np.ndarray | None = None


def find_best_match(
    record: FileRecord,
    descriptors: np.ndarray | None,
    candidates: list[StoredFile],
) -> tuple[StoredFile, int, str] | None:
    """Two-pass match: global hash first (cheap, catches resize/re-encode
    reliably), then ORB local-feature correspondence (catches crops that
    defeat any global hash). Never falls back to ahash/whash — see the
    module docstring above for why that's unsafe on this decision."""
    best_hash: tuple[StoredFile, int, str] | None = None
    for candidate in candidates:
        for hash_type in ("phash", "dhash"):
            new_hash = getattr(record, hash_type)
            old_hash = getattr(candidate, hash_type)
            if not new_hash or not old_hash:
                continue
            distance = hash_distance(old_hash, new_hash)
            if distance <= MATCH_THRESHOLD and (best_hash is None or distance < best_hash[1]):
                best_hash = (candidate, distance, hash_type)
    if best_hash is not None:
        return best_hash

    if descriptors is None:
        return None
    best_orb: tuple[StoredFile, int, str] | None = None
    for candidate in candidates:
        if candidate.orb_descriptors is None:
            continue
        good = orb_good_match_count(descriptors, candidate.orb_descriptors)
        if good >= ORB_MATCH_THRESHOLD and (best_orb is None or good > best_orb[1]):
            best_orb = (candidate, good, "orb_features")
    return best_orb


def detect_transformations(record: FileRecord, parent: StoredFile) -> list[str]:
    """Report the transformation observed between a matched parent and
    this file. Keyed off deterministic signals only: exact hash equality,
    dimension change, and pipeline fingerprints already established for
    this file — never off the pixel statistics in ForensicStats."""
    if record.sha256 == parent.sha256:
        return ["identical (bit-for-bit)"]

    transforms: list[str] = []
    if record.width and record.height and parent.width and parent.height:
        area_ratio = (record.width * record.height) / (parent.width * parent.height)
        if area_ratio < 0.98:
            pct = round(area_ratio * 100)
            if (record.width, record.height) != (parent.width, parent.height) and abs(
                record.width / record.height - parent.width / parent.height
            ) > 0.03:
                transforms.append("cropped")
            else:
                transforms.append(f"resized {pct}%")
        elif area_ratio > 1.02:
            transforms.append(f"upscaled {round(area_ratio * 100)}%")

    pipeline_names = {m.name for m in record.pipeline_matches}
    if "whatsapp_transmission" in pipeline_names:
        transforms.append("WhatsApp (1 hop)")
    if "android_screenshot" in pipeline_names or "screen_capture" in pipeline_names:
        transforms.append("screenshot")

    if not transforms:
        transforms.append("re-encoded")

    return transforms
