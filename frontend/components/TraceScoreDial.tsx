import { TraceScore } from "@/lib/types";

// The Trace Score measures how much verifiable history survives — NOT how
// likely the content is to be AI-generated. Never render this as a
// confidence/risk percentage; the label text carries that distinction.
export default function TraceScoreDial({ score }: { score: TraceScore }) {
  const pct = Math.max(0, Math.min(1, score.value / score.max_value));
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * pct;
  const color = pct >= 0.7 ? "#34d399" : pct >= 0.3 ? "#fbbf24" : "#8a93a6";

  return (
    <div className="flex items-center gap-4">
      <svg width={112} height={112} viewBox="0 0 112 112" className="shrink-0">
        <circle cx="56" cy="56" r={radius} fill="none" stroke="#232936" strokeWidth={10} />
        <circle
          cx="56"
          cy="56"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          transform="rotate(-90 56 56)"
        />
        <text x="56" y="52" textAnchor="middle" className="fill-[#e6e9f0]" fontSize="22" fontWeight={700}>
          {score.value}
        </text>
        <text x="56" y="70" textAnchor="middle" className="fill-[#8a93a6]" fontSize="11">
          / {score.max_value}
        </text>
      </svg>
      <div className="max-w-[220px]">
        <div className="text-[11px] uppercase tracking-wide text-muted mb-1">Trace Score</div>
        <p className="text-sm text-[#c7cddb] leading-snug">{score.label.replace(/^Trace Score: \d+\/\d+ — /, "")}</p>
      </div>
    </div>
  );
}
