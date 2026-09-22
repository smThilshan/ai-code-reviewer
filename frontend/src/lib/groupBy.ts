import type { ReviewIssue, Severity } from "../api/types";
import { SEVERITY_ORDER } from "./constants";

/**
 * Bucket issues by severity, in high→medium→low order.
 *
 * Every severity key is always present (possibly with an empty array) —
 * callers filter empty groups themselves rather than this function silently
 * omitting a key, which would make "high has 0 issues" indistinguishable
 * from "high wasn't checked."
 */
export function groupIssuesBySeverity(issues: ReviewIssue[]): Record<Severity, ReviewIssue[]> {
  const groups: Record<Severity, ReviewIssue[]> = { high: [], medium: [], low: [] };
  for (const issue of issues) {
    groups[issue.severity].push(issue);
  }
  return groups;
}

/** `groupIssuesBySeverity`'s buckets, in display order, with empties dropped. */
export function severityGroupsInOrder(
  groups: Record<Severity, ReviewIssue[]>
): [Severity, ReviewIssue[]][] {
  return SEVERITY_ORDER.map((severity): [Severity, ReviewIssue[]] => [severity, groups[severity]]).filter(
    ([, issues]) => issues.length > 0
  );
}
