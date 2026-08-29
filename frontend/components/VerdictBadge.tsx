import { Verdict } from "@/lib/types";

const STYLES: Record<Verdict, { bg: string; fg: string; dot: string; label: string }> = {
  VERIFIED_ORIGIN: { bg: "bg-emerald-500/10", fg: "text-emerald-300", dot: "bg-emerald-400", label: "VERIFIED ORIGIN" },
  DERIVED: { bg: "bg-amber-500/10", fg: "text-amber-300", dot: "bg-amber-400", label: "DERIVED" },
  NO_RECORD: { bg: "bg-slate-500/10", fg: "text-slate-300", dot: "bg-slate-400", label: "NO RECORD" },
};

export default function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict; size?: "sm" | "md" | "lg" }) {
  const s = STYLES[verdict];
  const sizeCls = size === "lg" ? "text-sm px-3 py-1.5" : size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-1";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-mono font-semibold tracking-wide ${s.bg} ${s.fg} ${sizeCls}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
