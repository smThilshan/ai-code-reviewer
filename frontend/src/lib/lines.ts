import type { ReviewIssue, Severity } from "../api/types";

/** One displayable source line: what CodePreview renders, regardless of mode. */
export interface DisplayLine {
  number: number;
  text: string;
  isContext?: boolean;
}

const SEVERITY_RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2 };

/**
 * One line -> the most severe issue reported on it, for CodePreview's
 * per-line background tint. Issues with no line_number ("general") aren't
 * placeable and are left out; they still show in the issue list itself.
 */
export function highlightMapFromIssues(issues: ReviewIssue[]): Map<number, Severity> {
  const map = new Map<number, Severity>();
  for (const issue of issues) {
    if (issue.line_number === null) continue;
    const existing = map.get(issue.line_number);
    if (!existing || SEVERITY_RANK[issue.severity] > SEVERITY_RANK[existing]) {
      map.set(issue.line_number, issue.severity);
    }
  }
  return map;
}

/**
 * Split lines into runs of consecutive line numbers.
 *
 * Code mode always produces one run (1..N, nothing skipped). A PR excerpt
 * can have gaps — only the lines the backend sent the model are present,
 * matching the "..." gap marker in backend/app/services/line_numbering.py's
 * own rendering — so CodePreview renders each run as its own block with a
 * visible divider between them, rather than implying adjacency that isn't
 * real.
 */
export function splitIntoRuns(lines: DisplayLine[]): DisplayLine[][] {
  const runs: DisplayLine[][] = [];
  for (const line of lines) {
    const previous = runs.at(-1)?.at(-1);
    if (previous && previous.number === line.number - 1) {
      runs.at(-1)!.push(line);
    } else {
      runs.push([line]);
    }
  }
  return runs;
}

// Backend language labels that don't match Prism's own language identifiers.
// Unlisted languages (including the "c/c++" ambiguous-header label — see
// backend/app/services/languages.py) pass through as-is; Prism silently
// renders unhighlighted plain text for anything it doesn't recognize rather
// than erroring, which is an acceptable, graceful fallback here.
const PRISM_LANGUAGE_ALIASES: Record<string, string> = {
  "c++": "cpp",
  "c#": "csharp",
  shell: "bash",
};

/** Map a backend language label to the identifier Prism expects. */
export function toPrismLanguage(language: string | null | undefined): string {
  if (!language) return "text";
  return PRISM_LANGUAGE_ALIASES[language] ?? language;
}
