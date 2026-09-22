import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Severity } from "../api/types";
import type { DisplayLine } from "../lib/lines";
import { splitIntoRuns, toPrismLanguage } from "../lib/lines";

// Full-row tint per severity, applied to a flagged line's background —
// intentionally the same hues as SeverityBadge, so a card's badge and its
// highlighted line in the code below it read as the same finding.
const HIGHLIGHT_BACKGROUND: Record<Severity, string> = {
  high: "rgba(220, 38, 38, 0.08)",
  medium: "rgba(217, 119, 6, 0.10)",
  low: "rgba(100, 116, 139, 0.10)",
};

interface CodePreviewProps {
  lines: DisplayLine[];
  language: string | null | undefined;
  /** line number -> the most severe issue on it, for the row's background tint. */
  highlights?: Map<number, Severity>;
}

/**
 * Read-only, line-numbered, syntax-highlighted source display.
 *
 * Used by both modes: Code mode passes the whole pasted file (always one
 * contiguous run); PR mode passes a file's excerpt (added lines, plus
 * read-only context around them — dimmed here the same way the backend's
 * own prompt marks them "[context]" for the model). Renders as one block
 * per contiguous run of line numbers, since a PR excerpt can have gaps.
 */
export function CodePreview({ lines, language, highlights }: CodePreviewProps) {
  if (lines.length === 0) return null;
  const runs = splitIntoRuns(lines);
  const prismLanguage = toPrismLanguage(language);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      {runs.map((run, index) => {
        const contextLines = new Set(run.filter((l) => l.isContext).map((l) => l.number));
        return (
          <div key={run[0].number}>
            {index > 0 && (
              <div className="border-y border-slate-200 bg-slate-50 px-4 py-1 text-xs text-slate-400">
                ⋯
              </div>
            )}
            <SyntaxHighlighter
              language={prismLanguage}
              style={oneLight}
              showLineNumbers
              startingLineNumber={run[0].number}
              wrapLongLines
              customStyle={{ margin: 0, background: "white", fontSize: "0.8125rem" }}
              lineNumberStyle={{ color: "#94a3b8", minWidth: "3em" }}
              lineProps={(lineNumber: number) => {
                const severity = highlights?.get(lineNumber);
                if (severity) {
                  return { style: { display: "block", background: HIGHLIGHT_BACKGROUND[severity] } };
                }
                if (contextLines.has(lineNumber)) {
                  return { style: { display: "block", opacity: 0.55 } };
                }
                return { style: { display: "block" } };
              }}
            >
              {run.map((l) => l.text).join("\n")}
            </SyntaxHighlighter>
          </div>
        );
      })}
    </div>
  );
}
