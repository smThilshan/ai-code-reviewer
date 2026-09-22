import type { Category, Severity } from "../api/types";

/**
 * Dropdown options for Code mode's language select.
 *
 * Deliberately NOT the full list backend/app/services/prompts.py has notes
 * for. That list also contains "c/c++" — an internal label the backend's PR
 * review generates for ambiguous .h files (see backend/app/services/
 * languages.py's AMBIGUOUS_C_HEADER), never something a person pasting code
 * would pick: if you're pasting it, you already know whether it's C or C++.
 * `value: null` on the last option sends no `language` field at all, which
 * is exactly what the backend's own "unknown language" path expects (see
 * ReviewRequest.language and resolve_language in the backend).
 */
export const LANGUAGE_OPTIONS: { label: string; value: string | null }[] = [
  { label: "Python", value: "python" },
  { label: "JavaScript", value: "javascript" },
  { label: "TypeScript", value: "typescript" },
  { label: "Java", value: "java" },
  { label: "Go", value: "go" },
  { label: "C", value: "c" },
  { label: "C++", value: "c++" },
  { label: "Other (let AI detect)", value: null },
];

/** Display order for severity groups — most urgent first, matching the backend's own ordering rule. */
export const SEVERITY_ORDER: Severity[] = ["high", "medium", "low"];

export const SEVERITY_LABELS: Record<Severity, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const CATEGORY_LABELS: Record<Category, string> = {
  bug: "Bug",
  security: "Security",
  performance: "Performance",
  style: "Style",
};
