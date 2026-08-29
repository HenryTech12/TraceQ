"use client";

import { useState } from "react";
import { AnalysisResult } from "@/lib/types";
import VerdictBadge from "./VerdictBadge";
import TraceScoreDial from "./TraceScoreDial";
import PipelineBadges from "./PipelineBadges";

function Section({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between py-3 text-left text-sm font-semibold text-[#dfe3ec]"
      >
        {title}
        <span className="text-muted">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="pb-4 text-sm text-[#c7cddb]">{children}</div>}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex justify-between gap-4 py-1 text-xs">
      <span className="text-muted">{label}</span>
      <span className="text-right font-mono text-[#dfe3ec]">{String(value)}</span>
    </div>
  );
}

function QuantTable({ table }: { table: number[] | null }) {
  if (!table) return <p className="text-xs text-muted">not present</p>;
  return (
    <div className="grid grid-cols-8 gap-px overflow-hidden rounded border border-border bg-border font-mono text-[10px]">
      {table.map((v, i) => (
        <div key={i} className="bg-panel px-1 py-0.5 text-center text-[#9fb0d0]">
          {v}
        </div>
      ))}
    </div>
  );
}

export default function EvidencePanel({ result }: { result: AnalysisResult }) {
  const { record } = result;

  return (
    <div className="rounded-xl border border-border bg-panel">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <VerdictBadge verdict={result.verdict} size="lg" />
          </div>
          <p className="max-w-xl text-sm leading-relaxed text-[#dfe3ec]">{result.verdict_statement}</p>
          <p className="mt-1 truncate text-xs text-muted" title={result.filename}>
            {result.filename} · {(record.file_size / 1024).toFixed(1)} KB
            {record.width && record.height ? ` · ${record.width}×${record.height}` : ""}
          </p>
        </div>
        <TraceScoreDial score={result.trace_score} />
      </div>

      <div className="p-4 pb-0">
        <div className="mb-3 text-[11px] uppercase tracking-wide text-muted">Pipeline inference</div>
        <PipelineBadges matches={record.pipeline_matches} />
      </div>

      {result.derivation && (
        <div className="mx-4 mt-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
          <div className="mb-1 font-semibold text-amber-300">Derivation</div>
          <p className="text-[#dfe3ec]">
            Matches <span className="font-mono">{result.derivation.parent_filename ?? result.derivation.parent_sha256.slice(0, 16)}</span>{" "}
            uploaded earlier this session — {result.derivation.transformations_detected.join(", ")} (
            {result.derivation.hash_type === "orb_features"
              ? `${result.derivation.hash_distance} matching local features`
              : `${result.derivation.hash_type} distance ${result.derivation.hash_distance}`}
            ).
          </p>
        </div>
      )}

      <div className="px-4">
        <Section title="C2PA / Content Credentials" defaultOpen={record.c2pa.present}>
          {!record.c2pa.present ? (
            <p className="text-xs text-muted">No C2PA manifest present.</p>
          ) : (
            <>
              <Fact label="present" value="true" />
              <Fact label="software_agent" value={record.c2pa.software_agent} />
              <Fact label="generator" value={record.c2pa.generator} />
              <Fact label="digital_source_type" value={record.c2pa.digital_source_type} />
              <Fact label="claim_generator" value={record.c2pa.claim_generator} />
              <Fact label="timestamp" value={record.c2pa.timestamp} />
              <Fact label="assertions" value={record.c2pa.assertions.join(", ")} />
              <p className="mt-2 text-[11px] text-muted">
                Signature cryptographic validation against a trust list is out of scope for this build — manifest
                presence and claimed fields are reported as-is.
              </p>
            </>
          )}
        </Section>

        <Section title="Camera EXIF" defaultOpen={record.exif.present}>
          {!record.exif.present ? (
            <p className="text-xs text-muted">No EXIF data present.</p>
          ) : (
            <>
              <Fact label="make / model" value={[record.exif.make, record.exif.model].filter(Boolean).join(" / ")} />
              <Fact label="software" value={record.exif.software} />
              <Fact label="datetime_original" value={record.exif.datetime_original} />
              <Fact label="exposure_time" value={record.exif.exposure_time} />
              <Fact label="f-number" value={record.exif.fnumber ? `f/${record.exif.fnumber}` : null} />
              <Fact label="iso" value={record.exif.iso} />
              <Fact label="subsec_time" value={record.exif.subsec_time} />
              <Fact label="has_gps_ifd" value={String(record.exif.has_gps_ifd)} />
              <Fact label="has_thumbnail_ifd" value={String(record.exif.has_thumbnail_ifd)} />
              {record.exif.has_thumbnail_ifd && (
                <p className="mt-1 text-[11px] text-emerald-300">
                  Thumbnail IFD present — near-certain real camera capture (generation pipelines essentially never emit one).
                </p>
              )}
            </>
          )}
        </Section>

        <Section title="ICC profile">
          {!record.icc.present ? (
            <p className="text-xs text-muted">No ICC profile present.</p>
          ) : (
            <>
              <Fact label="description" value={record.icc.description} />
              <Fact label="copyright" value={record.icc.copyright} />
            </>
          )}
        </Section>

        <Section title="Encoder fingerprint">
          <Fact label="progressive (SOF2)" value={String(record.encoder.is_progressive)} />
          <Fact label="chroma subsampling" value={record.encoder.chroma_subsampling} />
          <Fact label="quant tables identical" value={String(record.encoder.quant_tables_identical)} />
          <Fact label="trailing bytes after EOI" value={record.trailing_byte_count} />
          <Fact label="format mismatch" value={String(record.format_mismatch)} />
          {(record.encoder.quant_table_luma || record.encoder.quant_table_chroma) && (
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1 text-[10px] uppercase text-muted">luma quant table</div>
                <QuantTable table={record.encoder.quant_table_luma} />
              </div>
              <div>
                <div className="mb-1 text-[10px] uppercase text-muted">chroma quant table</div>
                <QuantTable table={record.encoder.quant_table_chroma} />
              </div>
            </div>
          )}
        </Section>

        <Section title="Hashes">
          <Fact label="sha256" value={record.sha256} />
          <Fact label="phash" value={record.phash} />
          <Fact label="dhash" value={record.dhash} />
          <Fact label="ahash" value={record.ahash} />
          <Fact label="whash" value={record.whash} />
          <Fact label="ORB descriptors" value={record.orb_descriptor_count} />
        </Section>

        <Section title="Diagnostics (non-authoritative)">
          <p className="mb-2 text-[11px] text-muted">{record.stats.note}</p>
          <Fact label="mean residual noise" value={record.stats.mean_residual_noise} />
          <Fact label="chromatic aberration (px, est.)" value={record.stats.chromatic_aberration_px} />
          <Fact label="min flat-region std" value={record.min_flat_region_std} />
        </Section>
      </div>
    </div>
  );
}
