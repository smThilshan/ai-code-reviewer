import type { ApiError } from "../api/types";

/**
 * Renders whatever api/client.ts produced, distinctly per kind — this is
 * the component the project's "surface real backend error messages, not a
 * generic failure" requirement lives in.
 */
export function ErrorDisplay({ error }: { error: ApiError }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4">
      <p className="text-sm font-medium text-red-800">{titleFor(error)}</p>
      <div className="mt-1 text-sm text-red-700">{bodyFor(error)}</div>
    </div>
  );
}

function titleFor(error: ApiError): string {
  switch (error.kind) {
    case "network":
      return "API unreachable";
    case "validation":
      return `Request rejected (${error.status})`;
    case "http":
      return error.status === 429 ? "Rate limit exceeded" : `Request failed (${error.status})`;
  }
}

function bodyFor(error: ApiError) {
  switch (error.kind) {
    case "network":
      return error.message;

    case "validation":
      // FastAPI's own validation body: one entry per invalid field. `loc`
      // is e.g. ["body", "code"] — drop the leading "body" and join the
      // rest, so "code: String should have at least 1 character" reads
      // like a normal field-level message, not a JSON path.
      return (
        <ul className="list-disc space-y-0.5 pl-4">
          {error.validationErrors.map((item, index) => (
            <li key={index}>
              <span className="font-mono text-xs">{item.loc.filter((p) => p !== "body").join(".")}</span>
              : {item.msg}
            </li>
          ))}
        </ul>
      );

    case "http": {
      const retryAfter = error.rateLimit?.retryAfterSeconds;
      return (
        <>
          <p>{error.message}</p>
          {retryAfter !== undefined && (
            <p className="mt-1 font-medium">Try again in {retryAfter}s.</p>
          )}
        </>
      );
    }
  }
}
