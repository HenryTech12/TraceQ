"""Hashing: SHA-256 (exact identity) + perceptual hashes (near-duplicate
matching across resize/crop/re-encode) + ORB descriptor count (diagnostic
signal for how much matchable local structure survives)."""
from __future__ import annotations

import hashlib

import imagehash
import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_perceptual_hashes(image: Image.Image) -> dict[str, str]:
    return {
        "phash": str(imagehash.phash(image)),
        "dhash": str(imagehash.dhash(image)),
        "ahash": str(imagehash.average_hash(image)),
        "whash": str(imagehash.whash(image)),
    }


def hash_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two hex perceptual hashes of equal length."""
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def compute_orb_descriptors(image: Image.Image) -> np.ndarray | None:
    """Local binary feature descriptors (32 bytes each). Unlike a global
    perceptual hash, these describe small patches around distinctive
    keypoints — genuine correspondence between two images requires many
    of them to independently match, which is far harder to satisfy by
    coincidence than a global hash landing within a distance threshold.
    This is what makes crop detection reliable (a crop keeps the kept
    region's local structure byte-for-bit-identical; a global hash's
    frequency layout shifts with the composition change)."""
    if cv2 is None:
        return None
    gray = np.array(image.convert("L"))
    orb = cv2.ORB_create(nfeatures=500)
    _, descriptors = orb.detectAndCompute(gray, None)
    return descriptors


def orb_good_match_count(descriptors_a: np.ndarray | None, descriptors_b: np.ndarray | None) -> int:
    """Count of mutually distinctive ORB matches via Lowe's ratio test.
    Returns 0 if either image has too few keypoints to compare."""
    if cv2 is None or descriptors_a is None or descriptors_b is None:
        return 0
    if len(descriptors_a) < 2 or len(descriptors_b) < 2:
        return 0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    knn = matcher.knnMatch(descriptors_a, descriptors_b, k=2)
    good = 0
    for pair in knn:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good += 1
    return good
