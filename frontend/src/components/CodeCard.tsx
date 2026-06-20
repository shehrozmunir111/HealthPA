import type { ProposedCode } from "../lib/types";
import { GroundedBadge } from "./StatusPill";
import { Check, Quote, X } from "./icons";

function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[11px] text-muted">{pct}%</span>
    </div>
  );
}

interface Props {
  code: ProposedCode;
  kept?: boolean;
  onToggle?: () => void;
}

export function CodeCard({ code, kept, onToggle }: Props) {
  const interactive = typeof onToggle === "function";
  const dropped = interactive && !kept;

  return (
    <div
      className={`card animate-rise p-4 transition ${
        dropped ? "opacity-45" : ""
      } ${kept ? "shadow-glow" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
              {code.code_system}
            </span>
            <GroundedBadge grounded={code.grounded} />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold leading-none text-text">
            {code.code}
          </div>
          <p className="mt-1.5 text-sm text-muted">{code.description}</p>
        </div>

        {interactive && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={kept}
            title={kept ? "Remove from approval" : "Keep in approval"}
            className={`btn h-9 w-9 shrink-0 rounded-lg p-0 ${
              kept
                ? "bg-ok/15 text-ok hover:bg-ok/25"
                : "border border-line bg-surface-2 text-faint hover:text-text"
            }`}
          >
            {kept ? <Check /> : <X />}
          </button>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <Confidence value={code.confidence} />
      </div>

      {code.citations.length > 0 && (
        <div className="mt-3 space-y-2 border-t border-line pt-3">
          {code.citations.map((cite, i) => (
            <div key={i} className="text-xs">
              <div className="flex items-center gap-1.5 font-mono text-[11px] text-accent">
                <Quote width={13} height={13} />
                {cite.source_doc}
                {cite.chunk != null ? `#${cite.chunk}` : ""}
              </div>
              {cite.quote && (
                <p className="mt-1 border-l-2 border-line pl-2.5 italic text-muted">
                  "{cite.quote}"
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
