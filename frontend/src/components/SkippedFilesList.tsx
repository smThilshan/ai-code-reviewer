import type { SkippedFile } from "../api/types";

export function SkippedFilesList({ files }: { files: SkippedFile[] }) {
  if (files.length === 0) return null;
  return (
    <details className="rounded-lg border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-medium text-slate-600">
        Skipped files ({files.length})
      </summary>
      <ul className="mt-3 space-y-1.5">
        {files.map((file) => (
          <li key={file.path} className="flex flex-wrap gap-2 text-sm">
            <span className="font-mono text-slate-700">{file.path}</span>
            <span className="text-slate-400">— {file.reason}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
