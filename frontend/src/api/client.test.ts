import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiError } from "./types";

// client.ts reads VITE_API_BASE_URL at MODULE LOAD time (see its own
// comment: failing fast at import, like backend/app/config.py does for
// missing env vars, rather than failing confusingly on the first request).
// That means it has to be stubbed BEFORE the module is imported, which is
// why this uses a dynamic import inside beforeAll instead of a static one
// (static imports are hoisted above any setup code in the file).
let client: typeof import("./client");

beforeAll(async () => {
  vi.stubEnv("VITE_API_BASE_URL", "http://localhost:8000");
  client = await import("./client");
});

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("reviewPullRequest error handling", () => {
  it("turns a string-detail HTTP error into a typed http ApiError", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(404, { detail: "Pull request not found. Check the URL; if the repository is private…" })
    );

    const error = (await client.reviewPullRequest({ pr_url: "x" }).catch((e) => e)) as ApiError;

    expect(error.kind).toBe("http");
    expect(error).toMatchObject({ status: 404, message: expect.stringContaining("Pull request not found") });
  });

  it("turns an array-detail (FastAPI validation) error into a typed validation ApiError, not a flattened string", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(422, {
        detail: [{ type: "string_too_short", loc: ["body", "pr_url"], msg: "String should have at least 1 character" }],
      })
    );

    const error = (await client.reviewPullRequest({ pr_url: "" }).catch((e) => e)) as ApiError;

    expect(error.kind).toBe("validation");
    if (error.kind === "validation") {
      expect(error.validationErrors).toHaveLength(1);
      expect(error.validationErrors[0].msg).toBe("String should have at least 1 character");
    }
  });

  it("turns a fetch rejection (backend unreachable or CORS-blocked) into a network ApiError, distinct from an http one", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));

    const error = (await client.reviewPullRequest({ pr_url: "x" }).catch((e) => e)) as ApiError;

    expect(error.kind).toBe("network");
    expect(error).not.toHaveProperty("status");
  });

  it("reads Retry-After and X-RateLimit-Remaining off a 429 into ApiError.rateLimit", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        429,
        { detail: "Rate limit exceeded: 5 per 1 minute. Try again later." },
        { "retry-after": "30", "x-ratelimit-remaining": "0" }
      )
    );

    const error = (await client.reviewPullRequest({ pr_url: "x" }).catch((e) => e)) as ApiError;

    expect(error.kind).toBe("http");
    if (error.kind === "http") {
      expect(error.status).toBe(429);
      expect(error.rateLimit?.retryAfterSeconds).toBe(30);
      expect(error.rateLimit?.remaining).toBe("0");
    }
  });
});

describe("reviewCode success path", () => {
  it("resolves with the parsed body on 200, and sends the request as JSON", async () => {
    const body = { issues: [], summary: "Clean." };
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, body));

    const result = await client.reviewCode({ code: "x = 1", language: "python" });

    expect(result).toEqual(body);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/review");
    expect(JSON.parse(init?.body as string)).toEqual({ code: "x = 1", language: "python" });
  });
});
