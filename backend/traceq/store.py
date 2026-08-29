"""Session-scoped SQLite store.

SQLite for the hackathon — zero setup, Postgres-shaped schema (one table,
one row per uploaded file, a nullable self-referential parent for the DNA
Graph edges). No user accounts, no cross-session registry — sessions are
just an opaque id a client keeps for the duration of a demo.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .matching import StoredFile
from .models import AnalysisResult, GraphEdge, GraphNode, PipelineMatch, SessionGraph, Verdict

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "traceq.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    phash TEXT,
    dhash TEXT,
    ahash TEXT,
    whash TEXT,
    width INTEGER,
    height INTEGER,
    verdict TEXT NOT NULL,
    trace_score INTEGER NOT NULL,
    pipeline_matches TEXT NOT NULL,
    parent_file_id TEXT,
    edge_label TEXT,
    orb_descriptors BLOB,
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, file_id)
);
"""

_ORB_DESCRIPTOR_WIDTH = 32  # ORB descriptors are fixed 32-byte binary vectors


def _descriptors_to_blob(descriptors: np.ndarray | None) -> bytes | None:
    if descriptors is None or len(descriptors) == 0:
        return None
    return descriptors.astype(np.uint8).tobytes()


def _blob_to_descriptors(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    arr = np.frombuffer(blob, dtype=np.uint8)
    return arr.reshape(-1, _ORB_DESCRIPTOR_WIDTH)


@contextmanager
def _connect(db_path: Path = DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with _connect(db_path):
        pass


def get_prior_files(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> list[StoredFile]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT file_id, filename, sha256, phash, dhash, ahash, whash, width, height, "
            "pipeline_matches, orb_descriptors FROM files WHERE session_id = ? ORDER BY rowid ASC",
            (session_id,),
        ).fetchall()
    result = []
    for row in rows:
        matches = [PipelineMatch(**m) for m in json.loads(row["pipeline_matches"])]
        result.append(
            StoredFile(
                file_id=row["file_id"],
                filename=row["filename"],
                sha256=row["sha256"],
                phash=row["phash"],
                dhash=row["dhash"],
                ahash=row["ahash"],
                whash=row["whash"],
                width=row["width"],
                height=row["height"],
                pipeline_matches=matches,
                orb_descriptors=_blob_to_descriptors(row["orb_descriptors"]),
            )
        )
    return result


def save_result(
    session_id: str,
    result: AnalysisResult,
    orb_descriptors: np.ndarray | None = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    parent_file_id = None
    edge_label = None
    if result.derivation is not None:
        # parent_file_id is stored as the sha256 prefix used elsewhere as file_id
        parent_file_id = result.derivation.parent_sha256[:16]
        edge_label = ", ".join(result.derivation.transformations_detected)

    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO files "
            "(session_id, file_id, filename, sha256, phash, dhash, ahash, whash, width, height, verdict, "
            " trace_score, pipeline_matches, parent_file_id, edge_label, orb_descriptors, analysis_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                result.file_id,
                result.filename,
                result.record.sha256,
                result.record.phash,
                result.record.dhash,
                result.record.ahash,
                result.record.whash,
                result.record.width,
                result.record.height,
                result.verdict.value,
                result.trace_score.value,
                json.dumps([m.model_dump() for m in result.record.pipeline_matches]),
                parent_file_id,
                edge_label,
                _descriptors_to_blob(orb_descriptors),
                result.model_dump_json(),
            ),
        )


_BADGE_BY_PIPELINE = {
    "whatsapp_transmission": "whatsapp",
    "android_screenshot": "android",
    "android_camera_reshared": "android",
    "direct_phone_camera": "camera",
    "openai_generation": "ai-generator",
    "screen_capture": "screen-capture",
    "near_lossless_export": "export-tool",
    "reportlab_programmatic_pdf": "pdf",
    "browser_print_to_pdf": "pdf",
    "ilovepdf_compression": "pdf",
}


def get_graph(session_id: str, db_path: Path = DEFAULT_DB_PATH) -> SessionGraph:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT file_id, filename, verdict, trace_score, pipeline_matches, "
            "parent_file_id, edge_label FROM files WHERE session_id = ? ORDER BY rowid ASC",
            (session_id,),
        ).fetchall()

    nodes = []
    edges = []
    known_ids = {row["file_id"] for row in rows}
    for row in rows:
        matches = json.loads(row["pipeline_matches"])
        badges = sorted({_BADGE_BY_PIPELINE.get(m["name"], m["name"]) for m in matches})
        nodes.append(
            GraphNode(
                id=row["file_id"],
                filename=row["filename"],
                verdict=Verdict(row["verdict"]),
                badges=badges,
                trace_score=row["trace_score"],
            )
        )
        if row["parent_file_id"] and row["parent_file_id"] in known_ids:
            edges.append(
                GraphEdge(
                    source=row["parent_file_id"],
                    target=row["file_id"],
                    label=row["edge_label"] or "derived",
                )
            )

    return SessionGraph(nodes=nodes, edges=edges)


def get_result(session_id: str, file_id: str, db_path: Path = DEFAULT_DB_PATH) -> AnalysisResult | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT analysis_json FROM files WHERE session_id = ? AND file_id = ?",
            (session_id, file_id),
        ).fetchone()
    if row is None:
        return None
    return AnalysisResult.model_validate_json(row["analysis_json"])
