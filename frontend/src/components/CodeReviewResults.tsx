import type { ReviewResponse } from "../api/types";
import { severityGroupsInOrder, groupIssuesBySeverity } from "../lib/groupBy";
import type { DisplayLine } from "../lib/lines";
import { highlightMapFromIssues } from "../lib/lines";
import { SEVERITY_LABELS } from "../lib/constants";
import { CodePreview } from "./CodePreview";
import { IssueCard } from "./IssueCard";

interface CodeReviewResultsProps {
  review: ReviewResponse;
  /** Omitted when the caller has no code to preview (shouldn't happen in practice, but keeps this reusable). */
  lines?: DisplayLine[];
  language?: string | null;
}

/**
 * One review's results: an optional code preview with flagged lines
 * highlighted, then issues grouped by severity. Reused as-is for Code
 * mode's top-level result and for each file inside PullRequestResults.
 */
export function CodeReviewResults({ review, lines, language }: CodeReviewResultsProps) {
  const groups = severityGroupsInOrder(groupIssuesBySeverity(review.issues));

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{review.summary}</p>

      {lines && lines.length > 0 && (
        <CodePreview lines={lines} language={language} highlights={highlightMapFromIssues(review.issues)} />
      )}

      {review.issues.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
          No issues found.
        </p>
      ) : (
        groups.map(([severity, issues]) => (
          <div key={severity}>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {SEVERITY_LABELS[severity]} ({issues.length})
            </h3>
            <ul className="space-y-2">
              {issues.map((issue, index) => (
                <IssueCard key={index} issue={issue} />
              ))}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}
