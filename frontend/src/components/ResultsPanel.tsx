import type { PullRequestReviewResponse, ReviewRequest, ReviewResponse } from "../api/types";
import { CodeReviewResults } from "./CodeReviewResults";
import { PullRequestResults } from "./PullRequestResults";

type Success =
  | { mode: "code"; request: ReviewRequest; result: ReviewResponse }
  | { mode: "pr"; result: PullRequestReviewResponse };

/** Picks the right results view for whichever mode actually produced this response. */
export function ResultsPanel({ success }: { success: Success }) {
  if (success.mode === "pr") return <PullRequestResults result={success.result} />;

  return (
    <CodeReviewResults
      review={success.result}
      language={success.request.language}
      lines={success.request.code.split("\n").map((text, index) => ({ number: index + 1, text }))}
    />
  );
}
