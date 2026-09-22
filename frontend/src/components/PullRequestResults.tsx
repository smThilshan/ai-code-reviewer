import type { FileReview, PullRequestReviewResponse } from "../api/types";
import { CodeReviewResults } from "./CodeReviewResults";
import { SkippedFilesList } from "./SkippedFilesList";

function FileSection({ file }: { file: FileReview }) {
  const issueCount = file.review?.issues.length ?? 0;
  return (
    <details className="rounded-lg border border-slate-200 bg-white" open={issueCount > 0 || !!file.error}>
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 p-4">
        <span className="font-mono text-sm text-slate-800">{file.path}</span>
        <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">{file.language}</span>
        <span className="text-xs text-slate-400">{file.lines_reviewed} lines reviewed</span>
        {file.error ? (
          <span className="ml-auto text-xs font-medium text-red-600">review failed</span>
        ) : (
          <span className="ml-auto text-xs text-slate-400">
            {issueCount === 0 ? "no issues" : `${issueCount} issue${issueCount === 1 ? "" : "s"}`}
          </span>
        )}
      </summary>
      <div className="border-t border-slate-200 p-4">
        {/* file.review is null exactly when file.error is set (see ExcerptLine's
            comment in api/types.ts) — shown distinctly, never silently dropped. */}
        {file.error ? (
          <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {file.error}
          </p>
        ) : (
          <CodeReviewResults
            review={file.review!}
            language={file.language}
            lines={file.excerpt.map((l) => ({ number: l.line_number, text: l.text, isContext: l.is_context }))}
          />
        )}
      </div>
    </details>
  );
}

export function PullRequestResults({ result }: { result: PullRequestReviewResponse }) {
  return (
    <div className="space-y-4">
      <p className="break-all text-sm text-slate-500">{result.pull_request}</p>
      {result.files.map((file) => (
        <FileSection key={file.path} file={file} />
      ))}
      <SkippedFilesList files={result.skipped_files} />
    </div>
  );
}
