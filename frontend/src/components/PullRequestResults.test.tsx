import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PullRequestReviewResponse } from "../api/types";
import { PullRequestResults } from "./PullRequestResults";

const FIXTURE: PullRequestReviewResponse = {
  pull_request: "https://github.com/owner/repo/pull/1",
  files: [
    {
      path: "src/ok.py",
      language: "python",
      lines_reviewed: 2,
      error: null,
      excerpt: [{ line_number: 10, text: "x = 1", is_context: false }],
      review: {
        issues: [
          {
            severity: "high",
            category: "bug",
            line_number: 10,
            description: "Something is wrong.",
            suggested_fix: "Fix it.",
          },
        ],
        summary: "One issue.",
      },
    },
    {
      path: "src/broken.py",
      language: "python",
      lines_reviewed: 3,
      error: "The model returned a review in an unexpected format.",
      excerpt: [],
      review: null,
    },
  ],
  skipped_files: [{ path: "CHANGES.rst", reason: "not a recognized source-code file type" }],
};

describe("PullRequestResults", () => {
  it("shows a failed file's error message rather than silently dropping it", () => {
    render(<PullRequestResults result={FIXTURE} />);

    expect(screen.getByText("src/broken.py")).toBeInTheDocument();
    expect(
      screen.getByText("The model returned a review in an unexpected format.")
    ).toBeInTheDocument();
  });

  it("still renders the successful file's issue alongside the failed one", () => {
    render(<PullRequestResults result={FIXTURE} />);

    expect(screen.getByText("Something is wrong.")).toBeInTheDocument();
  });

  it("lists skipped files with their reason", () => {
    render(<PullRequestResults result={FIXTURE} />);

    expect(screen.getByText("CHANGES.rst", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/not a recognized source-code file type/)).toBeInTheDocument();
  });
});
