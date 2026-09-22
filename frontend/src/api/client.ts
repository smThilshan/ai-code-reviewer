/**
 * The only module in this app that calls `fetch`.
 *
 * Mirrors the backend's own discipline: `ReviewService` is the only thing
 * that talks to OpenAI, `GitHubClient` the only thing that talks to GitHub —
 * everything else gets typed results or a typed error, never a raw
 * response or exception. Here, every component gets a typed result or a
 * typed `ApiError`; nothing else in the app imports `fetch`.
 */
import type {
  ApiError,
  HealthDetail,
  PullRequestReviewRequest,
  PullRequestReviewResponse,
  RateLimitInfo,
  ReviewRequest,
  ReviewResponse,
  ValidationErrorItem,
} from "./types";

// Read once at module load, not per-call: if this is missing, every request
// would fail the same way, so failing here — loudly, at startup — matches
// backend/app/config.py's own "fail fast on missing required config" rule,
// rather than letting a misconfigured deploy silently 404/CORS-fail on the
// first click and leave someone guessing why.
const BASE_URL = import.meta.env.VITE_API_BASE_URL;
if (!BASE_URL) {
  throw new Error(
    "VITE_API_BASE_URL is not set. Copy .env.example to .env and point it at the backend."
  );
}

function rateLimitFromHeaders(headers: Headers): RateLimitInfo | undefined {
  const limit = headers.get("x-ratelimit-limit") ?? undefined;
  const remaining = headers.get("x-ratelimit-remaining") ?? undefined;
  const reset = headers.get("x-ratelimit-reset");
  const retryAfter = headers.get("retry-after");
  if (!limit && !remaining && !reset && !retryAfter) return undefined;
  return {
    limit,
    remaining,
    resetAt: reset ? Number(reset) : undefined,
    retryAfterSeconds: retryAfter ? Number(retryAfter) : undefined,
  };
}

/** Type guard for FastAPI's own validation-error body: `detail` is an array. */
function isValidationErrors(detail: unknown): detail is ValidationErrorItem[] {
  return (
    Array.isArray(detail) &&
    detail.every((item) => typeof item === "object" && item !== null && "msg" in item)
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (cause) {
    // fetch() rejects for a connection failure — AND, indistinguishably at
    // this layer, for a CORS-blocked request: the browser reports a blocked
    // response to JS as the same opaque TypeError as "server unreachable"
    // (the real reason is visible only in the browser console, never to
    // code). ErrorDisplay's "API unreachable" message has to cover both.
    const detail = cause instanceof Error ? cause.message : String(cause);
    const error: ApiError = {
      kind: "network",
      message: `Could not reach the API at ${BASE_URL}. Is the backend running? (${detail})`,
    };
    throw error;
  }

  // Every endpoint returns JSON on both success and failure (see
  // backend/app/routers/*.py — every raised HTTPException carries a JSON
  // body), so this parse is safe even on non-2xx.
  const body: unknown = await response.json().catch(() => null);

  if (response.ok) return body as T;

  const detail = (body as { detail?: unknown } | null)?.detail;

  if (isValidationErrors(detail)) {
    const error: ApiError = { kind: "validation", status: response.status, validationErrors: detail };
    throw error;
  }

  const error: ApiError = {
    kind: "http",
    status: response.status,
    message: typeof detail === "string" ? detail : response.statusText,
    rateLimit: response.status === 429 ? rateLimitFromHeaders(response.headers) : undefined,
  };
  throw error;
}

export function reviewCode(payload: ReviewRequest): Promise<ReviewResponse> {
  return request<ReviewResponse>("/review", { method: "POST", body: JSON.stringify(payload) });
}

export function reviewPullRequest(
  payload: PullRequestReviewRequest
): Promise<PullRequestReviewResponse> {
  return request<PullRequestReviewResponse>("/review-pr", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getHealthDetailed(): Promise<HealthDetail> {
  return request<HealthDetail>("/health/detailed", { method: "GET" });
}
