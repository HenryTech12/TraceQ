# TraceQ — the forensic layer for the internet

Upload any image (or PDF) and TraceQ reconstructs where it's been —
what created it, what pipelines it passed through, what was done to it —
and renders that history as a **Content DNA Graph** plus a numeric
**Trace Score**.

**The one rule that defines this product:** TraceQ does not answer *"is
this AI-generated?"* as a guess. It reports only what it can verify
deterministically (a C2PA manifest, camera EXIF, an encoder fingerprint,
a transmission signature). When the evidence isn't there, it says so
plainly and stops — see `backend/traceq/models.py::Verdict` for the exact
three-state contract (`VERIFIED_ORIGIN` / `DERIVED` / `NO_RECORD`), and
`backend/traceq/pipeline.py` for the rule-based fingerprint library that
does the actual classification.

## Why this exists (the short version)

A labeled test series run on 13 real images found pixel-statistics-based
forensics (noise residuals, chromatic aberration) confidently wrong on 2
of 2 transmitted images, while cryptographic/metadata evidence
(C2PA, camera EXIF) was correct 3 of 3 times it was present. So this
build never lets pixel statistics drive a verdict or a score — they're
computed and shown in a "diagnostics (non-authoritative)" panel only.
Full rationale in `backend/traceq/stats.py`'s module docstring.

## Architecture

```
traceq/
  backend/    Python 3.11 + FastAPI. The forensic engine:
              container.py   — raw JPEG marker / PNG chunk walk (never trusts Pillow,
                                which silently drops the PNG eXIf chunk and JPEG
                                APP11/JUMBF segment — exactly where the highest-value
                                evidence lives)
              provenance.py  — C2PA (JUMBF/CBOR box walk), EXIF (all IFDs, raw TIFF
                                parse), ICC profile tag table
              encoder.py     — quantization tables, progressive flag, chroma subsampling
              pipeline.py    — the rule-based Pipeline Fingerprint Library (Section 3)
              hashes.py      — SHA-256, pHash/dHash/aHash/wHash, ORB local features
              matching.py    — session-scoped DERIVED-verdict matching (see below)
              stats.py       — diagnostics-only pixel statistics
              scoring.py     — the Trace Score formula
              analyze.py     — orchestrates all of the above into a FileRecord + verdict
              store.py       — session-scoped SQLite store
              api.py         — the FastAPI app
              cli.py         — `traceq analyze <file>` (Phase 1 CLI)
  frontend/   Next.js 14 + Tailwind + React Flow. Upload zone, Trace Score dial,
              Content DNA Graph, full evidence panel.
```

## Running it

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn traceq.api:app --port 8000 --reload
```

Generate the synthetic test fixtures (see below) and try the CLI first:

```bash
.venv/bin/python scripts/generate_fixtures.py
.venv/bin/python -m traceq.cli analyze seed_files/direct_phone_camera.jpg
```

Run the test suite:

```bash
.venv/bin/python -m pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm run dev
```

Open http://localhost:3000. Click **Load demo files** for an instant
populated graph (VERIFIED_ORIGIN via camera EXIF, a DERIVED crop, a
VERIFIED_ORIGIN via C2PA, two NO_RECORD files with pipeline inference,
one plain NO_RECORD) — or drag in the fixtures from `backend/seed_files/`
yourself, uploading `direct_phone_camera.jpg` and then
`direct_phone_camera_cropped.jpg` to see the DNA Graph draw the
derivation edge live. That's the ninety-second demo moment.

## Test fixtures are synthetic — read this before demoing

`backend/scripts/generate_fixtures.py` hand-crafts byte-accurate synthetic
stand-ins for real captures: real TIFF/IFD structures with a fabricated
camera make/model, a real (self-consistent) JUMBF/CBOR box tree with a
fabricated C2PA claim, a real ICC profile tag table with a fabricated
copyright string, xref-valid PDFs with fabricated producer strings. This
sandboxed dev environment has no real phone, no real WhatsApp round-trip,
no real OpenAI-generated file to test against — **verify the engine
against real captures** (an actual phone photo, an actual WhatsApp
send/receive, an actual browser print-to-PDF) before trusting this for a
live demo. `backend/tests/test_pipeline.py` runs against these fixtures
and documents which pipeline signature each one is meant to trigger.

## Matching design note (why DERIVED uses two different signals)

`matching.py` deliberately does **not** use a single perceptual hash
threshold across all four hash algorithms. Empirically (see the
docstring in `matching.py`), aHash/wHash false-positived a DERIVED match
between two genuinely unrelated synthetic images at a smaller distance
than a legitimate crop scored on the same algorithm — i.e. no threshold
safely separates true from false on that signal alone. So:

- **phash/dhash** (structure-aware) gate a match for resize/re-encode,
  where the composition is preserved.
- **ORB local-feature correspondence** (genuine keypoint matches via
  Lowe's ratio test) gates a match for crops, where the composition
  changes but the kept region's local structure doesn't.
- ahash/whash are still computed and shown in the evidence panel, but
  never trigger a DERIVED verdict.

`tests/test_pipeline.py::test_unrelated_files_are_never_falsely_derived`
is the regression test for this.

## Non-goals (see the build spec, Section 8)

No general AI-image detector, no confidence score for AI generation, no
classifier trained on user feedback, no "restoring" a screenshot to its
original, no user accounts/billing/cross-user registry.
