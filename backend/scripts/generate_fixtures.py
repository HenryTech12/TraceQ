"""Generate synthetic test fixtures exercising every pipeline signature in
Section 3 of the build spec.

TraceQ's engine is meant to be verified against real captures (a real
phone photo, a real WhatsApp round-trip, a real OpenAI generation with its
real C2PA manifest). This sandboxed dev environment has none of those, so
this script hand-crafts byte-accurate synthetic stand-ins: real TIFF/IFD
structures, a real (self-consistent) JUMBF/CBOR box tree, a real ICC
profile tag table, real xref-valid PDFs — everything the parser modules
actually walk, just with fabricated content instead of a real capture
device behind it. Treat these as unit-test fixtures, not demo evidence.
"""
from __future__ import annotations

import io
import struct
import sys
import zlib
from pathlib import Path

import cbor2
import numpy as np
import piexif
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent.parent / "seed_files"


def noisy_image(width: int, height: int, base_color: tuple[int, int, int], noise_std: float = 5.0) -> Image.Image:
    """A gradient background plus a few contrasting blobs, with per-pixel
    gaussian noise on top.

    Pure flat color + noise is adversarial for perceptual hashing (no
    macro-structure survives a crop/resize) and also under-tests the
    screen-capture detector's real job (distinguishing genuine sensor
    noise from an exactly-flat framebuffer block). Real photos have
    edges and shapes that phash/dhash are built to track, so fixtures
    need some too.
    """
    rng = np.random.default_rng(seed=sum(base_color))
    yy, xx = np.mgrid[0:height, 0:width]
    grad = (xx / max(width - 1, 1) + yy / max(height - 1, 1)) / 2.0

    base = np.array(base_color, dtype=np.float64)
    contrast = np.array([255.0, 255.0, 255.0]) - base
    arr = base[None, None, :] + grad[..., None] * contrast[None, None, :] * 0.35

    for _ in range(3):
        cx = rng.integers(int(width * 0.2), int(width * 0.8))
        cy = rng.integers(int(height * 0.2), int(height * 0.8))
        r = rng.integers(max(1, min(width, height) // 8), max(2, min(width, height) // 4))
        color = rng.integers(0, 255, 3).astype(np.float64)
        mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
        arr[mask] = 0.6 * arr[mask] + 0.4 * color

    # Sharp-edged rectangles ("bricks") — a smooth gradient plus soft
    # blobs gives ORB almost no real corners to key off (unlike an actual
    # photo's texture), which makes crop-matching untestable. Hard edges
    # fix that without changing what the fixture is standing in for.
    n_bricks = max(8, (width * height) // 6000)
    for _ in range(n_bricks):
        bw = rng.integers(max(4, width // 40), max(6, width // 15))
        bh = rng.integers(max(4, height // 40), max(6, height // 15))
        bx = rng.integers(0, max(1, width - bw))
        by = rng.integers(0, max(1, height - bh))
        color = rng.integers(0, 255, 3).astype(np.float64)
        arr[by : by + bh, bx : bx + bw] = 0.5 * arr[by : by + bh, bx : bx + bw] + 0.5 * color

    arr += rng.normal(0, noise_std, size=arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


# ---------------------------------------------------------------------------
# Generic byte-level helpers
# ---------------------------------------------------------------------------

def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def insert_png_chunk_before_iend(png_bytes: bytes, ctype: bytes, data: bytes) -> bytes:
    iend_marker = struct.pack(">I", 0) + b"IEND"
    idx = png_bytes.rfind(iend_marker)
    if idx == -1:
        raise ValueError("no IEND chunk found")
    return png_bytes[:idx] + _png_chunk(ctype, data) + png_bytes[idx:]


def build_jumbf_box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + box_type + payload


def build_jumd(uuid16: bytes, label: str) -> bytes:
    label_bytes = label.encode("utf-8") + b"\x00"
    toggles = 0x01  # has label
    return uuid16 + bytes([toggles]) + label_bytes


def build_jumb_superbox(label: str, uuid16: bytes, children: bytes) -> bytes:
    jumd_box = build_jumbf_box(b"jumd", build_jumd(uuid16, label))
    return build_jumbf_box(b"jumb", jumd_box + children)


def build_c2pa_jumbf_stream(claim: dict) -> bytes:
    cbor_box = build_jumbf_box(b"cbor", cbor2.dumps(claim))
    claim_jumb = build_jumb_superbox("c2pa.claim", b"\x11" * 16, cbor_box)
    return build_jumb_superbox("c2pa", b"\x22" * 16, claim_jumb)


def insert_c2pa_into_jpeg(jpeg_bytes: bytes, jumbf_stream: bytes) -> bytes:
    header = b"JP" + struct.pack(">H", 1) + struct.pack(">I", 1) + jumbf_stream
    segment = b"\xff\xeb" + struct.pack(">H", len(header) + 2) + header
    assert jpeg_bytes[:2] == b"\xff\xd8"
    return jpeg_bytes[:2] + segment + jpeg_bytes[2:]


def build_minimal_icc_profile(copyright_text: str, description_text: str = "TraceQ synthetic profile") -> bytes:
    def text_tag(s: str) -> bytes:
        body = s.encode("ascii") + b"\x00"
        if len(body) % 4:
            body += b"\x00" * (4 - len(body) % 4)
        return b"text\x00\x00\x00\x00" + body

    cprt_data = text_tag(copyright_text)
    desc_data = text_tag(description_text)

    tag_count = 2
    header = bytearray(128)
    header[36:40] = b"acsp"
    tag_table_size = 4 + tag_count * 12
    data_offset = 128 + tag_table_size
    tags = []
    payloads = b""
    for sig, payload in ((b"desc", desc_data), (b"cprt", cprt_data)):
        offset = 128 + tag_table_size + len(payloads)
        tags.append(struct.pack(">4sII", sig, offset, len(payload)))
        payloads += payload
    tag_table = struct.pack(">I", tag_count) + b"".join(tags)
    profile = bytes(header) + tag_table + payloads
    profile = struct.pack(">I", len(profile))[0:4] + profile[4:]  # write total size into header[0:4]
    return profile


def assemble_pdf(object_bodies: list[bytes], root_obj: int, info_obj: int | None) -> bytes:
    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(object_bodies, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode()
        buf += body
        buf += b"\nendobj\n"
    xref_offset = len(buf)
    n = len(object_bodies) + 1
    buf += f"xref\n0 {n}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {n} /Root {root_obj} 0 R"
    if info_obj:
        trailer += f" /Info {info_obj} 0 R"
    trailer += " >>\nstartxref\n" + str(xref_offset) + "\n%%EOF"
    buf += trailer.encode()
    return bytes(buf)


def build_simple_pdf(producer: str, creator: str, base_font: str = "Helvetica") -> bytes:
    content = b"BT /F1 12 Tf 10 100 Td (Hello) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
        b"/MediaBox [0 0 200 200] /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        f"<< /Type /Font /Subtype /Type1 /BaseFont /{base_font} >>".encode(),
        f"<< /Producer ({producer}) /Creator ({creator}) >>".encode(),
    ]
    return assemble_pdf(objects, root_obj=1, info_obj=6)


def build_pdf_with_embedded_font(producer: str, creator: str, base_font: str = "ArialMT") -> bytes:
    content = b"BT /F1 12 Tf 10 100 Td (Hello) Tj ET"
    fontfile_data = b"\x00\x01\x00\x00" + b"synthetic-embedded-font-data" * 4
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
        b"/MediaBox [0 0 200 200] /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        f"<< /Type /Font /Subtype /TrueType /BaseFont /ABCDEF+{base_font} /FontDescriptor 6 0 R >>".encode(),
        b"<< /Type /FontDescriptor /FontName /ABCDEF+" + base_font.encode() + b" /FontFile2 7 0 R >>",
        b"<< /Length " + str(len(fontfile_data)).encode() + b" >>\nstream\n" + fontfile_data + b"\nendstream",
        f"<< /Producer ({producer}) /Creator ({creator}) >>".encode(),
    ]
    return assemble_pdf(objects, root_obj=1, info_obj=8)


def build_tiff_bytes(exif_dict: dict) -> bytes:
    return piexif.dump(exif_dict)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def make_direct_phone_camera_jpeg(path: Path) -> None:
    img = noisy_image(640, 480, (90, 110, 140))
    thumb = noisy_image(160, 120, (90, 110, 140))

    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG")

    zeroth = {
        piexif.ImageIFD.Make: "TECNO",
        piexif.ImageIFD.Model: "KL4",
        piexif.ImageIFD.Software: "Camera",
    }
    exif_ifd = {
        piexif.ExifIFD.ExposureTime: (1, 25),
        piexif.ExifIFD.FNumber: (185, 100),
        piexif.ExifIFD.ISOSpeedRatings: 2042,
        piexif.ExifIFD.DateTimeOriginal: "2026:08:12 09:41:03",
        piexif.ExifIFD.SubSecTimeOriginal: "123",
    }
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N",
        piexif.GPSIFD.GPSLatitude: ((6, 1), (30, 1), (0, 1)),
        piexif.GPSIFD.GPSLongitudeRef: "E",
        piexif.GPSIFD.GPSLongitude: ((3, 1), (23, 1), (0, 1)),
    }
    first_ifd = {piexif.ImageIFD.Compression: 6}
    exif_dict = {
        "0th": zeroth,
        "Exif": exif_ifd,
        "GPS": gps_ifd,
        "1st": first_ifd,
        "thumbnail": thumb_buf.getvalue(),
    }
    exif_bytes = piexif.dump(exif_dict)
    img.save(path, "jpeg", exif=exif_bytes, quality=90)


def make_whatsapp_transmission_jpeg(path: Path) -> None:
    img = noisy_image(512, 512, (200, 50, 50))
    qtable = [
        16, 11, 10, 16, 24, 40, 51, 61,
        12, 12, 14, 19, 26, 58, 60, 55,
        14, 13, 16, 24, 40, 57, 69, 56,
        14, 17, 22, 29, 51, 87, 80, 62,
        18, 22, 37, 56, 68, 109, 103, 77,
        24, 35, 55, 64, 81, 104, 113, 92,
        49, 64, 78, 87, 103, 121, 120, 101,
        72, 92, 95, 98, 112, 100, 103, 99,
    ]
    img.save(path, "jpeg", progressive=True, qtables=[qtable, qtable])


def make_android_screenshot_png(path: Path) -> None:
    # Real screenshots legitimately contain large flat UI regions, so this
    # one is deliberately NOT noised — it's meant to also validate that a
    # screen_capture match and an android_screenshot match can co-occur.
    img = Image.new("RGB", (360, 640), color=(245, 245, 245))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    exif_dict = {
        "0th": {piexif.ImageIFD.Software: "Android 13"},
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: "2026:08:20 14:02:11",
            piexif.ExifIFD.ImageUniqueID: "a1b2c3d4e5f60718293a4b5c6d7e8f90",
        },
        "GPS": {},
        "1st": {},
        "thumbnail": None,
    }
    tiff_bytes = piexif.dump(exif_dict)
    if tiff_bytes[:6] == b"Exif\x00\x00":
        tiff_bytes = tiff_bytes[6:]
    out = insert_png_chunk_before_iend(png_bytes, b"eXIf", tiff_bytes)
    path.write_bytes(out)


def make_android_camera_reshared_jpeg(path: Path) -> None:
    img = noisy_image(600, 400, (80, 160, 90))
    icc = build_minimal_icc_profile(copyright_text="Google Inc. 2016")
    img.save(path, "jpeg", quality=88, icc_profile=icc)


def make_near_lossless_export(path: Path) -> None:
    img = noisy_image(300, 300, (30, 30, 30))
    qtable = [1] * 64
    img.save(path, "jpeg", qtables=[qtable, qtable])


def make_openai_generation_png(path: Path) -> None:
    img = noisy_image(512, 512, (120, 140, 200))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    claim = {
        "claim_generator": "OpenAI gpt-image/1.0",
        "claim_generator_info": [{"name": "gpt-image", "version": "1.0"}],
        "softwareAgent": "gpt-image",
        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
        "when": "2026-08-12T10:00:00+00:00",
        "instanceId": "xmp:iid:11111111-2222-3333-4444-555555555555",
    }
    stream = build_c2pa_jumbf_stream(claim)
    out = insert_png_chunk_before_iend(png_bytes, b"caBX", stream)
    path.write_bytes(out)


def make_openai_generation_jpeg(path: Path) -> None:
    img = noisy_image(512, 512, (140, 120, 200))
    img.save(path, "jpeg", quality=95)
    claim = {
        "claim_generator": "OpenAI gpt-image/1.0",
        "claim_generator_info": [{"name": "gpt-image", "version": "1.0"}],
        "softwareAgent": "gpt-image",
        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
        "when": "2026-08-12T10:00:00+00:00",
    }
    stream = build_c2pa_jumbf_stream(claim)
    out = insert_c2pa_into_jpeg(path.read_bytes(), stream)
    path.write_bytes(out)


def make_screen_capture_png(path: Path) -> None:
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    for x in range(40, 200):
        for y in range(40, 60):
            img.putpixel((x, y), (10, 10, 10))
    img.save(path, "png")


def make_reportlab_pdf(path: Path) -> None:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=(300, 300))
    c.drawString(20, 150, "TraceQ ReportLab fixture")
    c.save()


def make_browser_print_pdf(path: Path) -> None:
    data = build_pdf_with_embedded_font(producer="Skia/PDF m130", creator="Chromium", base_font="ArialMT")
    path.write_bytes(data)


def make_ilovepdf_pdf(path: Path) -> None:
    data = build_simple_pdf(producer="iLovePDF", creator="TraceQ fixture", base_font="Helvetica")
    path.write_bytes(data)


def make_no_record_jpeg(path: Path) -> None:
    img = noisy_image(320, 240, (60, 90, 200))
    img.save(path, "jpeg", quality=80)


def make_derived_crop(parent_path: Path, path: Path) -> None:
    # An aspect-ratio-changing crop (most real-world crops aren't
    # symmetric) so the DERIVED transformation heuristic — which tells
    # "cropped" from "resized" by whether the aspect ratio moved — reports
    # correctly instead of reading as a same-ratio resize.
    img = Image.open(parent_path)
    w, h = img.size
    cropped = img.crop((int(w * 0.15), int(h * 0.05), int(w * 0.70), h - int(h * 0.15)))
    cropped.save(path, "jpeg", quality=90)


def make_derived_resize(parent_path: Path, path: Path) -> None:
    img = Image.open(parent_path)
    w, h = img.size
    resized = img.resize((w // 2, h // 2))
    resized.save(path, "jpeg", quality=85)


FIXTURES = {
    "direct_phone_camera.jpg": make_direct_phone_camera_jpeg,
    "whatsapp_transmission.jpg": make_whatsapp_transmission_jpeg,
    "android_screenshot.png": make_android_screenshot_png,
    "android_camera_reshared.jpg": make_android_camera_reshared_jpeg,
    "near_lossless_export.jpg": make_near_lossless_export,
    "openai_generation.png": make_openai_generation_png,
    "openai_generation.jpg": make_openai_generation_jpeg,
    "screen_capture.png": make_screen_capture_png,
    "reportlab_programmatic.pdf": make_reportlab_pdf,
    "browser_print_to_pdf.pdf": make_browser_print_pdf,
    "ilovepdf_compressed.pdf": make_ilovepdf_pdf,
    "no_record.jpg": make_no_record_jpeg,
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in FIXTURES.items():
        builder(OUT_DIR / name)
        print(f"wrote {OUT_DIR / name}")

    make_derived_crop(OUT_DIR / "direct_phone_camera.jpg", OUT_DIR / "direct_phone_camera_cropped.jpg")
    make_derived_resize(OUT_DIR / "direct_phone_camera.jpg", OUT_DIR / "direct_phone_camera_resized.jpg")
    print(f"wrote {OUT_DIR / 'direct_phone_camera_cropped.jpg'}")
    print(f"wrote {OUT_DIR / 'direct_phone_camera_resized.jpg'}")


if __name__ == "__main__":
    sys.exit(main())
