"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { analyzeFile, ApiError, createSession, getFile, getGraph, seedSession } from "@/lib/api";
import { clearStoredSessionId, loadStoredSessionId, storeSessionId } from "@/lib/session";
import { AnalysisResult, SessionGraph } from "@/lib/types";
import UploadZone from "@/components/UploadZone";
import DnaGraph from "@/components/DnaGraph";
import EvidencePanel from "@/components/EvidencePanel";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [graph, setGraph] = useState<SessionGraph>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<AnalysisResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initRef = useRef(false);

  const refreshGraph = useCallback(async (sid: string) => {
    try {
      const g = await getGraph(sid);
      setGraph(g);
    } catch {
      // demo backend may not be running yet — surfaced by upload errors instead
    }
  }, []);

  useEffect(() => {
    if (initRef.current) return; // React 18 dev StrictMode double-invokes effects
    initRef.current = true;
    (async () => {
      const existing = loadStoredSessionId();
      if (existing) {
        setSessionId(existing);
        refreshGraph(existing);
        return;
      }
      try {
        const sid = await createSession();
        storeSessionId(sid);
        setSessionId(sid);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not reach the TraceQ API — is the backend running?");
      }
    })();
  }, [refreshGraph]);

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (!sessionId) return;
      setBusy(true);
      setError(null);
      try {
        for (const file of files) {
          const result = await analyzeFile(sessionId, file);
          setSelected(result);
        }
        await refreshGraph(sessionId);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Analysis failed unexpectedly.");
      } finally {
        setBusy(false);
      }
    },
    [sessionId, refreshGraph],
  );

  const handleSelectNode = useCallback(
    async (fileId: string) => {
      if (!sessionId) return;
      try {
        const result = await getFile(sessionId, fileId);
        setSelected(result);
      } catch {
        // ignore
      }
    },
    [sessionId],
  );

  const handleNewSession = useCallback(async () => {
    clearStoredSessionId();
    setSelected(null);
    setGraph({ nodes: [], edges: [] });
    try {
      const sid = await createSession();
      storeSessionId(sid);
      setSessionId(sid);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not reach the TraceQ API.");
    }
  }, []);

  const handleLoadDemo = useCallback(async () => {
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const g = await seedSession(sessionId);
      setGraph(g);
      if (g.nodes.length > 0) {
        const result = await getFile(sessionId, g.nodes[0].id);
        setSelected(result);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the demo fixtures.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Trace<span className="text-accent">Q</span>
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            The forensic layer for the internet. Upload a file — TraceQ reports only what it can verify
            deterministically, and says so plainly when it can&apos;t.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            onClick={handleLoadDemo}
            disabled={busy || !sessionId}
            className="rounded-lg border border-accent/40 px-3 py-1.5 text-xs text-accent hover:border-accent disabled:opacity-40"
          >
            Load demo files
          </button>
          <button
            onClick={handleNewSession}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:border-[#3a4256] hover:text-[#c7cddb]"
          >
            New session
          </button>
        </div>
      </header>

      <UploadZone onFiles={handleFiles} busy={busy} />

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Content DNA Graph</h2>
        <DnaGraph graph={graph} selectedId={selected?.file_id ?? null} onSelect={handleSelectNode} />
      </section>

      {selected && (
        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Evidence</h2>
          <EvidencePanel result={selected} />
        </section>
      )}

      <footer className="mt-16 border-t border-border pt-6 text-xs text-muted">
        Every other tool in this category will show you a confidence percentage. Ours refuses to — and that refusal
        is the feature.
      </footer>
    </main>
  );
}
