import type { Category, Severity } from "../api/types";
import { CATEGORY_LABELS, SEVERITY_LABELS } from "../lib/constants";

// Severity carries the color in this UI; category is deliberately neutral.
// Coloring both would make every card fight for attention — see the
// project's "not over-designed" brief.
const SEVERITY_STYLES: Record<Severity, string> = {
  high: "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20",
  medium: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/20",
  low: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-500/20",
};

const BADGE_BASE = "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium";

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`${BADGE_BASE} ${SEVERITY_STYLES[severity]}`}>{SEVERITY_LABELS[severity]}</span>;
}

export function CategoryBadge({ category }: { category: Category }) {
  return (
    <span className={`${BADGE_BASE} bg-zinc-100 text-zinc-700 ring-1 ring-inset ring-zinc-300`}>
      {CATEGORY_LABELS[category]}
    </span>
  );
}
