import { AnalysisResult, SessionGraph } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore — non-JSON error body
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export async function createSession(): Promise<string> {
  const res = await fetch(`${API_BASE}/api/session`, { method: "POST" });
  const data = await handle<{ session_id: string }>(res);
  return data.session_id;
}

export async function analyzeFile(sessionId: string, file: File): Promise<AnalysisResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/analyze?session_id=${encodeURIComponent(sessionId)}`, {
    method: "POST",
    body: form,
  });
  return handle<AnalysisResult>(res);
}

export async function seedSession(sessionId: string): Promise<SessionGraph> {
  const res = await fetch(`${API_BASE}/api/session/${encodeURIComponent(sessionId)}/seed`, { method: "POST" });
  return handle<SessionGraph>(res);
}

export async function getGraph(sessionId: string): Promise<SessionGraph> {
  const res = await fetch(`${API_BASE}/api/session/${encodeURIComponent(sessionId)}/graph`, {
    cache: "no-store",
  });
  return handle<SessionGraph>(res);
}

export async function getFile(sessionId: string, fileId: string): Promise<AnalysisResult> {
  const res = await fetch(
    `${API_BASE}/api/session/${encodeURIComponent(sessionId)}/files/${encodeURIComponent(fileId)}`,
    { cache: "no-store" },
  );
  return handle<AnalysisResult>(res);
}
