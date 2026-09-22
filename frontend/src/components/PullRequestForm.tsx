import { useState } from "react";
import type { PullRequestReviewRequest } from "../api/types";

interface PullRequestFormProps {
  onSubmit: (payload: PullRequestReviewRequest) => void;
  submitting: boolean;
}

export function PullRequestForm({ onSubmit, submitting }: PullRequestFormProps) {
  const [prUrl, setPrUrl] = useState("");
  const trimmed = prUrl.trim();
  const disabled = submitting || trimmed.length === 0;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (disabled) return;
    onSubmit({ pr_url: trimmed });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="pr_url" className="mb-1.5 block text-sm font-medium text-slate-700">
          GitHub pull request URL
        </label>
        <input
          id="pr_url"
          value={prUrl}
          onChange={(event) => setPrUrl(event.target.value)}
          placeholder="https://github.com/owner/repo/pull/123"
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 focus:border-accent-600 focus:outline-none focus:ring-1 focus:ring-accent-600"
        />
        <p className="mt-1.5 text-xs text-slate-400">
          Only the lines the PR adds or changes are reviewed, with a little surrounding context.
        </p>
      </div>

      <button
        type="submit"
        disabled={disabled}
        className="rounded-lg bg-accent-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {submitting ? "Reviewing…" : "Review pull request"}
      </button>
    </form>
  );
}
