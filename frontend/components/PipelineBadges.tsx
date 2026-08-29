import { PipelineMatch } from "@/lib/types";

const ICON: Record<string, string> = {
  whatsapp_transmission: "💬",
  android_screenshot: "📱",
  android_camera_reshared: "📷",
  direct_phone_camera: "📸",
  near_lossless_export: "🖼️",
  openai_generation: "✨",
  screen_capture: "🖥️",
  reportlab_programmatic_pdf: "📄",
  browser_print_to_pdf: "🌐",
  ilovepdf_compression: "📉",
};

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "border-emerald-500/40 text-emerald-300",
  medium: "border-amber-500/40 text-amber-300",
  low: "border-slate-500/40 text-slate-300",
};

export default function PipelineBadges({ matches }: { matches: PipelineMatch[] }) {
  if (matches.length === 0) {
    return <p className="text-xs text-muted">No pipeline signature matched.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {matches.map((m) => (
        <span
          key={m.name}
          title={m.basis.join(" · ")}
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-mono ${
            CONFIDENCE_COLOR[m.confidence] ?? "border-border text-muted"
          }`}
        >
          <span>{ICON[m.name] ?? "🔍"}</span>
          {m.name.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  );
}
