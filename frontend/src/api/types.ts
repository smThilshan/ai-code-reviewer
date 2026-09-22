/**
 * TypeScript mirror of the backend's Pydantic schemas.
 *
 * Kept as one file, hand-written to match `app/schemas/*.py` field-for-field
 * (verified against the live `model_json_schema()` output, not guessed). No
 * codegen: the backend is small and stable enough that a generator would be
 * more ceremony than the four schemas it's replacing. If the backend's
 * schemas grow much further, generating this from `/openapi.json` becomes
 * worth it — until then, this file is the single place a mismatch would
 * surface (a field the backend renames breaks the frontend at compile time,
 * not at demo time).
 */

// --- app/schemas/review.py ---------------------------------------------------

export type Severity = "low" | "medium" | "high";
export type Category = "bug" | "security" | "performance" | "style";

export interface ReviewIssue {
  severity: Severity;
  category: Category;
  /** 1-based line number, or null when the issue isn't tied to one line. */
  line_number: number | null;
  description: string;
  suggested_fix: string;
}

export interface ReviewResponse {
  issues: ReviewIssue[];
  summary: string;
}

export interface ReviewRequest {
  code: string;
  /** Omit or null to let the backend infer it from `filename`, or the model identify it. */
  language?: string | null;
  filename?: string | null;
}

// --- app/schemas/pull_request.py ---------------------------------------------

export interface PullRequestReviewRequest {
  pr_url: string;
}

/**
 * One line the backend sent to the model for this file: either an added
 * line (reviewable) or read-only context around it (shown for understanding
 * only — see app/services/prompts.py's EXCERPT_NOTE). Added by Phase 8 to
 * power the code-preview panel; reuses data the backend already computed
 * for the review itself, nothing new is fetched.
 */
export interface ExcerptLine {
  line_number: number;
  text: string;
  is_context: boolean;
}

export interface FileReview {
  path: string;
  language: string;
  lines_reviewed: number;
  /** Null exactly when `error` is set — this file's review failed. */
  review: ReviewResponse | null;
  error: string | null;
  excerpt: ExcerptLine[];
}

export interface SkippedFile {
  path: string;
  reason: string;
}

export interface PullRequestReviewResponse {
  pull_request: string;
  files: FileReview[];
  skipped_files: SkippedFile[];
}

// --- app/schemas/health.py ----------------------------------------------------

export interface RateLimits {
  review: string;
  review_pr: string;
}

export interface HealthDetail {
  status: string;
  version: string;
  openai_model: string;
  openai_configured: boolean;
  github_token_configured: boolean;
  rate_limits: RateLimits;
}

// --- Error shapes (not backend schemas — this is what FastAPI/our routers
// actually put in an error response body; see api/client.ts for how each is
// produced) -------------------------------------------------------------------

/** One item of FastAPI's own validation-error body (a 422 for a malformed request). */
export interface ValidationErrorItem {
  type: string;
  loc: (string | number)[];
  msg: string;
}

export interface RateLimitInfo {
  limit?: string;
  remaining?: string;
  /** Unix epoch seconds (X-RateLimit-Reset), when the window resets. */
  resetAt?: number;
  /** Seconds to wait before retrying (Retry-After), present on a 429. */
  retryAfterSeconds?: number;
}

/**
 * Every failure api/client.ts can produce, normalized to one shape so
 * ErrorDisplay never has to guess what it was handed.
 *
 * - "network": fetch() itself failed — backend unreachable, DNS failure, or
 *   (indistinguishably, at this layer) a CORS-blocked request. The browser
 *   reports all three as the same opaque failure; see client.ts for why.
 * - "http": the backend answered with a non-2xx and a string `detail` — one
 *   of our own domain errors (see backend/app/services/exceptions.py).
 * - "validation": the backend answered 422 with an array `detail` — FastAPI's
 *   own request-validation error, before our code ever ran.
 */
export type ApiError =
  | { kind: "network"; message: string }
  | { kind: "http"; status: number; message: string; rateLimit?: RateLimitInfo }
  | { kind: "validation"; status: number; validationErrors: ValidationErrorItem[] };
