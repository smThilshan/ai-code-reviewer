import { useState } from "react";
import type { ReviewRequest } from "../api/types";
import { LANGUAGE_OPTIONS } from "../lib/constants";

// Mirrors backend/app/schemas/review.py's ReviewRequest.code max_length, so
// the length limit shows up as an inline hint instead of a round trip to
// the API just to learn the same thing as a 422.
const MAX_CODE_CHARS = 20_000;

// HTML <select> values are always strings; LANGUAGE_OPTIONS' "Other" entry
// is `value: null` (meaning: send no language field at all). This sentinel
// exists only in the DOM and is translated back to `null` on submit.
const OTHER_SENTINEL = "__other__";

interface CodeReviewFormProps {
  onSubmit: (payload: ReviewRequest) => void;
  submitting: boolean;
}

export function CodeReviewForm({ onSubmit, submitting }: CodeReviewFormProps) {
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState<string>(LANGUAGE_OPTIONS[0].value ?? OTHER_SENTINEL);
  const [filename, setFilename] = useState("");

  const trimmed = code.trim();
  const disabled = submitting || trimmed.length === 0 || code.length > MAX_CODE_CHARS;

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (disabled) return;
    onSubmit({
      code,
      language: language === OTHER_SENTINEL ? null : language,
      filename: filename.trim() || null,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label htmlFor="code" className="text-sm font-medium text-slate-700">
            Code
          </label>
          <span className={`text-xs ${code.length > MAX_CODE_CHARS ? "text-red-600" : "text-slate-400"}`}>
            {code.length.toLocaleString()} / {MAX_CODE_CHARS.toLocaleString()}
          </span>
        </div>
        <textarea
          id="code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="Paste code to review…"
          rows={16}
          spellCheck={false}
          className="w-full resize-y rounded-lg border border-slate-300 bg-white p-3 font-mono text-sm text-slate-800 focus:border-accent-600 focus:outline-none focus:ring-1 focus:ring-accent-600"
        />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="language" className="mb-1.5 block text-sm font-medium text-slate-700">
            Language
          </label>
          <select
            id="language"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-accent-600 focus:outline-none focus:ring-1 focus:ring-accent-600"
          >
            {LANGUAGE_OPTIONS.map((option) => (
              <option key={option.label} value={option.value ?? OTHER_SENTINEL}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1">
          <label htmlFor="filename" className="mb-1.5 block text-sm font-medium text-slate-700">
            Filename <span className="font-normal text-slate-400">(optional)</span>
          </label>
          <input
            id="filename"
            value={filename}
            onChange={(event) => setFilename(event.target.value)}
            placeholder="app/main.py"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 focus:border-accent-600 focus:outline-none focus:ring-1 focus:ring-accent-600"
          />
        </div>

        <button
          type="submit"
          disabled={disabled}
          className="rounded-lg bg-accent-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {submitting ? "Reviewing…" : "Review code"}
        </button>
      </div>
    </form>
  );
}
