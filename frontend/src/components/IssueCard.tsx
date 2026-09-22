import type { ReviewIssue } from "../api/types";
import { CategoryBadge, SeverityBadge } from "./Badge";

export function IssueCard({ issue }: { issue: ReviewIssue }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={issue.severity} />
        <CategoryBadge category={issue.category} />
        <span className="ml-auto font-mono text-xs text-slate-400">
          {issue.line_number !== null ? `line ${issue.line_number}` : "general"}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-800">{issue.description}</p>
      <div className="mt-2 rounded-md bg-slate-50 p-2.5 text-sm text-slate-600">
        <span className="font-medium text-slate-500">Suggested fix: </span>
        {issue.suggested_fix}
      </div>
    </li>
  );
}
