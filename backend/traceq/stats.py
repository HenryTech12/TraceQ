"""Pixel-statistics diagnostics — computed, logged, shown in a diagnostics
panel, and NEVER used to drive a verdict or the Trace Score.

Two documented failure modes motivate this hard boundary (see the TraceQ
build spec, Section 1):

1. Texture confound: median-residual "noise" measures all high-frequency
   content, not sensor noise. A real photo of coarse concrete measured 77x
   higher residual than an AI image of a smooth desk — the difference was
   subject matter, not origin.
2. Chromatic aberration inversion: measured CA was higher on a confirmed
   AI image (0.019px) than a confirmed real photo (0.002px) — the opposite
   of what lens-optics theory predicts, because lossy transmission
   dominates the signal.

The one pixel-level measurement that IS deterministic enough to use in
pipeline matching is the flat-region standard deviation (screen-capture
detector, see pipeline.py) — an exact 0.000 there is a framebuffer
artifact no camera sensor or generator produces, unlike the two above,
which are magnitude comparisons with no reliable decision boundary.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .models import ForensicStats

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def compute_min_flat_region_std(image: Image.Image, block_size: int = 8) -> float:
    """Minimum standard deviation across non-overlapping blocks. A camera
    sensor essentially never produces an exactly flat block; a framebuffer
    screen capture routinely does (solid UI backgrounds)."""
    gray = np.asarray(image.convert("L"), dtype=np.float64)
    h, w = gray.shape
    if h < block_size or w < block_size:
        return float(gray.std())
    min_std = None
    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = gray[y : y + block_size, x : x + block_size]
            std = float(block.std())
            if min_std is None or std < min_std:
                min_std = std
            if min_std == 0.0:
                return 0.0
    return min_std if min_std is not None else float(gray.std())


def _median_residual_noise(gray: np.ndarray) -> float:
    if cv2 is not None:
        filtered = cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float64)
    else:
        # Cheap fallback median filter without OpenCV.
        padded = np.pad(gray, 1, mode="edge")
        stacked = np.stack(
            [padded[i : i + gray.shape[0], j : j + gray.shape[1]] for i in range(3) for j in range(3)]
        )
        filtered = np.median(stacked, axis=0)
    return float(np.mean(np.abs(gray - filtered)))


def _chromatic_aberration_px(rgb: np.ndarray, search: int = 3) -> float | None:
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return None
    r, g, b = rgb[:, :, 0].astype(np.float64), rgb[:, :, 1].astype(np.float64), rgb[:, :, 2].astype(np.float64)

    def edge_map(channel: np.ndarray) -> np.ndarray:
        gy, gx = np.gradient(channel)
        return np.hypot(gx, gy)

    eg = edge_map(g)

    def best_shift(channel: np.ndarray) -> float:
        e = edge_map(channel)
        best_score, best_dx, best_dy = None, 0, 0
        for dy in range(-search, search + 1):
            for dx in range(-search, search + 1):
                shifted = np.roll(np.roll(e, dy, axis=0), dx, axis=1)
                score = float(np.mean((shifted - eg) ** 2))
                if best_score is None or score < best_score:
                    best_score, best_dx, best_dy = score, dx, dy
        return float(np.hypot(best_dx, best_dy))

    # Downsample for speed — this is a diagnostic estimate, not a
    # forensic ground truth.
    step = max(1, min(r.shape) // 256)
    r_ds, g_ds, b_ds = r[::step, ::step], g[::step, ::step], b[::step, ::step]
    eg_full = eg
    eg = edge_map(g_ds)
    shift_r = best_shift(r_ds)
    shift_b = best_shift(b_ds)
    return round((shift_r + shift_b) / 2, 4)


def compute_forensic_stats(image: Image.Image) -> ForensicStats:
    arr = np.asarray(image.convert("RGB"))
    gray = np.asarray(image.convert("L"), dtype=np.float64)
    try:
        noise = round(_median_residual_noise(gray), 4)
    except Exception:
        noise = None
    try:
        ca = _chromatic_aberration_px(arr)
    except Exception:
        ca = None
    return ForensicStats(mean_residual_noise=noise, chromatic_aberration_px=ca)
