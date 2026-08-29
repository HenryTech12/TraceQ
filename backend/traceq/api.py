"""Phase 2 API.

POST /api/analyze (multipart)      -> AnalysisResult (record + verdict + observations)
GET  /api/session/{id}/graph       -> nodes and edges for the Content DNA Graph
GET  /api/session/{id}/files/{fid} -> a previously computed AnalysisResult (evidence panel)
POST /api/session                  -> allocate a new session id
POST /api/session/{id}/seed        -> Phase 4 demo hardening: populate the graph from bundled fixtures
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import seed, store
from .analyze import analyze_file_with_descriptors
from .models import AnalysisResult, SessionGraph

app = FastAPI(title="TraceQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon demo scope — no auth, no user accounts
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB — generous for a phone photo, bounded against abuse


@app.on_event("startup")
def _startup() -> None:
    store.init_db()


@app.post("/api/session")
def create_session() -> dict:
    return {"session_id": uuid.uuid4().hex}


def _analyze_and_store(session_id: str, data: bytes, filename: str) -> AnalysisResult:
    prior_files = store.get_prior_files(session_id)
    result, orb_descriptors = analyze_file_with_descriptors(data, filename, prior_files)
    store.save_result(session_id, result, orb_descriptors)
    return result


@app.post("/api/analyze", response_model=AnalysisResult)
async def analyze(session_id: str, file: UploadFile = File(...)) -> AnalysisResult:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (25MB limit for this demo).")

    try:
        return _analyze_and_store(session_id, data, file.filename or "upload")
    except Exception as exc:  # noqa: BLE001 — never crash the demo on a malformed upload
        raise HTTPException(status_code=422, detail=f"Could not parse this file: {exc}") from exc


@app.post("/api/session/{session_id}/seed", response_model=SessionGraph)
def seed_session(session_id: str) -> SessionGraph:
    """Demo hardening: load the bundled synthetic fixtures into this
    session so the Content DNA Graph is populated without a judge needing
    their own test photo. Never fails the whole request over one bad
    fixture — each is analyzed independently."""
    for filename, data in seed.load_seed_files():
        try:
            _analyze_and_store(session_id, data, filename)
        except Exception:  # noqa: BLE001 — one broken fixture shouldn't block the rest
            continue
    return store.get_graph(session_id)


@app.get("/api/session/{session_id}/graph", response_model=SessionGraph)
def get_graph(session_id: str) -> SessionGraph:
    return store.get_graph(session_id)


@app.get("/api/session/{session_id}/files/{file_id}", response_model=AnalysisResult)
def get_file(session_id: str, file_id: str) -> AnalysisResult:
    result = store.get_result(session_id, file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No such file in this session.")
    return result


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
