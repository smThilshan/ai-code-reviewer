export type Mode = "code" | "pr";

const OPTIONS: { mode: Mode; label: string }[] = [
  { mode: "code", label: "Paste Code" },
  { mode: "pr", label: "Review a PR" },
];

export function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
      {OPTIONS.map((option) => (
        <button
          key={option.mode}
          type="button"
          onClick={() => onChange(option.mode)}
          aria-pressed={mode === option.mode}
          className={`rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors ${
            mode === option.mode ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
