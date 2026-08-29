"""Phase 4 demo hardening: populate a session's Content DNA Graph from the
bundled synthetic fixtures in seed_files/, in an order that walks a judge
through all three verdict states and the crop-derivation "wow moment"
without requiring their own test photo.
"""
from __future__ import annotations

from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_files"

# Order matters: the crop must follow its parent so the DNA Graph draws
# the derivation edge live, the way it would for a judge's own upload.
SEED_SEQUENCE = [
    "direct_phone_camera.jpg",
    "direct_phone_camera_cropped.jpg",
    "openai_generation.png",
    "android_screenshot.png",
    "whatsapp_transmission.jpg",
    "no_record.jpg",
]


def load_seed_files() -> list[tuple[str, bytes]]:
    """Returns (filename, bytes) pairs for the curated demo sequence,
    skipping any fixture that hasn't been generated yet."""
    loaded = []
    for name in SEED_SEQUENCE:
        path = SEED_DIR / name
        if path.exists():
            loaded.append((name, path.read_bytes()))
    return loaded
