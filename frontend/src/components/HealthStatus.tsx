import { useEffect, useState } from "react";
import { getHealthDetailed } from "../api/client";
import type { HealthDetail } from "../api/types";

type State = { kind: "checking" } | { kind: "connected"; detail: HealthDetail } | { kind: "unreachable" };

const DOT_STYLES: Record<"checking" | "connected" | "degraded" | "unreachable", string> = {
  checking: "bg-slate-300",
  connected: "bg-emerald-500",
  degraded: "bg-amber-500",
  unreachable: "bg-red-500",
};

/**
 * Polls GET /health/detailed once on mount and shows a small status pill.
 * /health/detailed never calls OpenAI/GitHub (see backend/app/schemas/
 * health.py), so this is free and instant — a fetch failure here genuinely
 * means "the backend can't be reached," not "the backend is busy."
 */
export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: "checking" });

  useEffect(() => {
    let cancelled = false;
    getHealthDetailed()
      .then((detail) => {
        if (!cancelled) setState({ kind: "connected", detail });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "unreachable" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const degraded = state.kind === "connected" && !state.detail.openai_configured;
  const dotKind = state.kind === "connected" ? (degraded ? "degraded" : "connected") : state.kind;
  const label =
    state.kind === "checking"
      ? "Checking API…"
      : state.kind === "unreachable"
        ? "API unreachable"
        : degraded
          ? "API connected — OpenAI not configured"
          : `API connected (${state.detail.openai_model})`;

  return (
    <div className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600">
      <span className={`h-2 w-2 rounded-full ${DOT_STYLES[dotKind]}`} aria-hidden="true" />
      {label}
    </div>
  );
}
