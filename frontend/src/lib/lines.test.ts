import { describe, expect, it } from "vitest";
import type { ReviewIssue } from "../api/types";
import { highlightMapFromIssues, splitIntoRuns, toPrismLanguage } from "./lines";

describe("splitIntoRuns", () => {
  it("keeps a single contiguous file as one run", () => {
    const lines = [1, 2, 3].map((number) => ({ number, text: `line ${number}` }));

    expect(splitIntoRuns(lines)).toEqual([lines]);
  });

  it("splits on a gap in line numbers, as a PR excerpt with skipped context produces", () => {
    const lines = [
      { number: 10, text: "a" },
      { number: 11, text: "b" },
      { number: 40, text: "c" }, // gap: 12..39 not shown, matches backend's "..." marker
      { number: 41, text: "d" },
    ];

    const runs = splitIntoRuns(lines);

    expect(runs).toEqual([
      [
        { number: 10, text: "a" },
        { number: 11, text: "b" },
      ],
      [
        { number: 40, text: "c" },
        { number: 41, text: "d" },
      ],
    ]);
  });

  it("returns an empty array for no lines", () => {
    expect(splitIntoRuns([])).toEqual([]);
  });
});

describe("toPrismLanguage", () => {
  it("maps the languages Prism spells differently than the backend does", () => {
    expect(toPrismLanguage("c++")).toBe("cpp");
    expect(toPrismLanguage("c#")).toBe("csharp");
    expect(toPrismLanguage("shell")).toBe("bash");
  });

  it("passes an already-matching or unknown language through unchanged", () => {
    expect(toPrismLanguage("python")).toBe("python");
    expect(toPrismLanguage("c/c++")).toBe("c/c++"); // the ambiguous .h label — Prism just won't highlight it
  });

  it("falls back to plain text for a missing language", () => {
    expect(toPrismLanguage(null)).toBe("text");
    expect(toPrismLanguage(undefined)).toBe("text");
  });
});

describe("highlightMapFromIssues", () => {
  function issue(overrides: Partial<ReviewIssue>): ReviewIssue {
    return { severity: "low", category: "style", line_number: 1, description: "d", suggested_fix: "f", ...overrides };
  }

  it("maps each issue's line to its severity", () => {
    const map = highlightMapFromIssues([issue({ line_number: 4, severity: "high" })]);

    expect(map.get(4)).toBe("high");
  });

  it("keeps the most severe issue when two land on the same line", () => {
    const map = highlightMapFromIssues([
      issue({ line_number: 4, severity: "low" }),
      issue({ line_number: 4, severity: "high" }),
    ]);

    expect(map.get(4)).toBe("high");
  });

  it("skips issues with no line_number — they aren't placeable in the preview", () => {
    const map = highlightMapFromIssues([issue({ line_number: null, severity: "high" })]);

    expect(map.size).toBe(0);
  });
});
