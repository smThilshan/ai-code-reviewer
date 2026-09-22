import { describe, expect, it } from "vitest";
import type { ReviewIssue } from "../api/types";
import { groupIssuesBySeverity, severityGroupsInOrder } from "./groupBy";

function issue(overrides: Partial<ReviewIssue>): ReviewIssue {
  return {
    severity: "low",
    category: "style",
    line_number: 1,
    description: "d",
    suggested_fix: "f",
    ...overrides,
  };
}

describe("groupIssuesBySeverity", () => {
  it("buckets mixed-severity issues correctly, including one with a null line_number", () => {
    const issues = [
      issue({ severity: "high", line_number: 4 }),
      issue({ severity: "low", line_number: null }),
      issue({ severity: "medium", line_number: 10 }),
      issue({ severity: "high", line_number: 12 }),
    ];

    const groups = groupIssuesBySeverity(issues);

    expect(groups.high).toHaveLength(2);
    expect(groups.medium).toHaveLength(1);
    expect(groups.low).toHaveLength(1);
    expect(groups.low[0].line_number).toBeNull();
  });

  it("returns every severity key, even with zero issues in it (not omitted)", () => {
    const groups = groupIssuesBySeverity([]);

    expect(Object.keys(groups).sort()).toEqual(["high", "low", "medium"]);
    expect(groups.high).toEqual([]);
  });
});

describe("severityGroupsInOrder", () => {
  it("orders high, then medium, then low, and drops empty groups", () => {
    const groups = groupIssuesBySeverity([issue({ severity: "low" }), issue({ severity: "high" })]);

    const ordered = severityGroupsInOrder(groups);

    expect(ordered.map(([severity]) => severity)).toEqual(["high", "low"]); // medium dropped: empty
  });
});
