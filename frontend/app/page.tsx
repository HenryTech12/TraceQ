import Link from "next/link";

const VERDICTS = [
  {
    tag: "VERIFIED_ORIGIN",
    color: "text-verified",
    ring: "ring-verified/30",
    desc: "A C2PA manifest, camera EXIF, or other cryptographic/metadata evidence was found and checks out.",
  },
  {
    tag: "DERIVED",
    color: "text-derived",
    ring: "ring-derived/30",
    desc: "This file matches an earlier upload in the session — a crop, resize, or re-encode of a known parent.",
  },
  {
    tag: "NO_RECORD",
    color: "text-norecord",
    ring: "ring-norecord/30",
    desc: "No verifiable chain of custody exists. TraceQ says so plainly instead of guessing.",
  },
];

const FEATURES = [
  {
    title: "Content DNA Graph",
    desc: "Every upload becomes a node. Crops, resizes, and re-encodes draw live derivation edges back to their parent — a visual chain of custody for a session.",
  },
  {
    title: "Trace Score",
    desc: "A transparent, breakdown-visible score built only from deterministic evidence — never from pixel statistics or a black-box classifier.",
  },
  {
    title: "Full Evidence Panel",
    desc: "C2PA claims, EXIF/TIFF IFDs, ICC profiles, JPEG quantization tables, and perceptual hashes — the raw forensic record behind every verdict.",
  },
];

const PIPELINE = [
  "Container walk (raw JPEG markers / PNG chunks — never trusts a library that silently drops evidence)",
  "Provenance extraction (C2PA JUMBF/CBOR, EXIF, ICC)",
  "Encoder fingerprinting (quant tables, progressive flag, chroma subsampling)",
  "Perceptual + cryptographic hashing (SHA-256, pHash/dHash/aHash/wHash, ORB features)",
  "Session-scoped derivation matching",
  "Rule-based pipeline inference — diagnostics only, never the verdict",
];

export default function Landing() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <nav className="mb-16 flex items-center justify-between">
        <span className="text-lg font-bold tracking-tight">
          Trace<span className="text-accent">Q</span>
        </span>
        <Link
          href="/app"
          className="rounded-lg border border-accent/40 px-4 py-2 text-sm font-medium text-accent hover:border-accent hover:bg-accent/5"
        >
          Launch app →
        </Link>
      </nav>

      <section className="max-w-3xl">
        <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-accent">
          The forensic layer for the internet
        </p>
        <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
          Don&apos;t guess whether it&apos;s real.
          <br />
          <span className="text-muted">Verify what you can prove.</span>
        </h1>
        <p className="mt-6 text-lg leading-relaxed text-muted">
          Upload any image or PDF. TraceQ reconstructs where it&apos;s been — what created it, what
          pipelines it passed through, what was done to it — using only deterministic evidence:
          C2PA manifests, camera EXIF, encoder fingerprints, transmission signatures.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <Link
            href="/app"
            className="rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-[#0b0e14] hover:opacity-90"
          >
            Try it now — load demo files
          </Link>
          <a
            href="https://github.com/HenryTech12/TraceQ"
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-border px-5 py-3 text-sm text-muted hover:border-[#3a4256] hover:text-[#c7cddb]"
          >
            View source
          </a>
        </div>
      </section>

      <section className="mt-20 rounded-xl border border-border bg-panel p-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-muted">The one rule</p>
        <p className="mt-2 text-xl leading-relaxed">
          Every other tool in this category will show you a confidence percentage for
          &quot;is this AI-generated?&quot;. <span className="text-accent">TraceQ refuses to</span> — and
          that refusal is the feature. It reports a three-state verdict, backed only by evidence it can
          verify.
        </p>
      </section>

      <section className="mt-16">
        <h2 className="mb-6 text-sm font-semibold uppercase tracking-wide text-muted">
          Three verdicts. No guessing in between.
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {VERDICTS.map((v) => (
            <div key={v.tag} className={`rounded-xl border border-border bg-panel p-5 ring-1 ${v.ring}`}>
              <span className={`font-mono text-sm font-semibold ${v.color}`}>{v.tag}</span>
              <p className="mt-2 text-sm leading-relaxed text-muted">{v.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="mb-6 text-sm font-semibold uppercase tracking-wide text-muted">What you get</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-border bg-panel p-5">
              <h3 className="font-semibold text-[#e6e9f0]">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="mb-6 text-sm font-semibold uppercase tracking-wide text-muted">
          How a file is analyzed
        </h2>
        <ol className="space-y-3">
          {PIPELINE.map((step, i) => (
            <li key={step} className="flex gap-4 rounded-lg border border-border bg-panel px-4 py-3">
              <span className="shrink-0 font-mono text-sm text-accent">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-sm leading-relaxed text-muted">{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16 rounded-xl border border-border bg-panel p-8 text-center">
        <h2 className="text-2xl font-bold tracking-tight">Ready to see a file&apos;s real history?</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-muted">
          No account, no upload history kept beyond your session. Click load demo files for an instant
          populated Content DNA Graph, or drag in your own image.
        </p>
        <Link
          href="/app"
          className="mt-6 inline-block rounded-lg bg-accent px-6 py-3 text-sm font-semibold text-[#0b0e14] hover:opacity-90"
        >
          Launch TraceQ →
        </Link>
      </section>

      <footer className="mt-16 border-t border-border pt-6 text-xs text-muted">
        TraceQ does not answer &quot;is this AI-generated?&quot; as a guess. It reports only what it can
        verify — and stops there.
      </footer>
    </main>
  );
}
