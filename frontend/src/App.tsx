import { useReducer, useState } from "react";
import { reviewCode, reviewPullRequest } from "./api/client";
import type { ApiError, PullRequestReviewRequest, ReviewRequest } from "./api/types";
import { CodeReviewForm } from "./components/CodeReviewForm";
import { ErrorDisplay } from "./components/ErrorDisplay";
import { HealthStatus } from "./components/HealthStatus";
import { LoadingSpinner } from "./components/LoadingSpinner";
import type { Mode } from "./components/ModeToggle";
import { ModeToggle } from "./components/ModeToggle";
import { PullRequestForm } from "./components/PullRequestForm";
import { ResultsPanel } from "./components/ResultsPanel";

type Success =
  | { mode: "code"; request: ReviewRequest; result: Awaited<ReturnType<typeof reviewCode>> }
  | { mode: "pr"; result: Awaited<ReturnType<typeof reviewPullRequest>> };

// A tagged union, not three separate useState calls, so "loading" and a
// stale "result" from the previous submission can never be true at once —
// the type system rules that state out, rather than a render-time `if`
// having to remember to check for it.
type RequestState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; success: Success }
  | { status: "error"; error: ApiError };

type Action =
  | { type: "start" }
  | { type: "success"; success: Success }
  | { type: "error"; error: ApiError }
  | { type: "reset" };

function reducer(_state: RequestState, action: Action): RequestState {
  switch (action.type) {
    case "start":
      return { status: "loading" };
    case "success":
      return { status: "success", success: action.success };
    case "error":
      return { status: "error", error: action.error };
    case "reset":
      return { status: "idle" };
  }
}

export default function App() {
  const [mode, setMode] = useState<Mode>("code");
  const [state, dispatch] = useReducer(reducer, { status: "idle" });

  function handleModeChange(next: Mode) {
    setMode(next);
    dispatch({ type: "reset" }); // a PR result under the Code form (or vice versa) would be confusing
  }

  async function handleReviewCode(request: ReviewRequest) {
    dispatch({ type: "start" });
    try {
      const result = await reviewCode(request);
      dispatch({ type: "success", success: { mode: "code", request, result } });
    } catch (error) {
      dispatch({ type: "error", error: error as ApiError });
    }
  }

  async function handleReviewPullRequest(request: PullRequestReviewRequest) {
    dispatch({ type: "start" });
    try {
      const result = await reviewPullRequest(request);
      dispatch({ type: "success", success: { mode: "pr", result } });
    } catch (error) {
      dispatch({ type: "error", error: error as ApiError });
    }
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">AI Code Reviewer</h1>
          <HealthStatus />
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <ModeToggle mode={mode} onChange={handleModeChange} />

        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-6">
          {mode === "code" ? (
            <CodeReviewForm onSubmit={handleReviewCode} submitting={state.status === "loading"} />
          ) : (
            <PullRequestForm onSubmit={handleReviewPullRequest} submitting={state.status === "loading"} />
          )}
        </div>

        <div className="mt-6">
          {state.status === "loading" && (
            <LoadingSpinner
              label={mode === "code" ? "Reviewing your code…" : "Fetching the diff and reviewing changed files…"}
            />
          )}
          {state.status === "error" && <ErrorDisplay error={state.error} />}
          {state.status === "success" && <ResultsPanel success={state.success} />}
        </div>
      </main>
    </div>
  );
}
