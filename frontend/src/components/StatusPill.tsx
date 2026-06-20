import type { PaStatus } from "../lib/types";

const MAP: Record<PaStatus, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "text-faint border-line bg-surface-2" },
  pending: { label: "Pending review", cls: "text-amber border-amber/30 bg-amber/10" },
  needs_info: { label: "Needs info", cls: "text-amber border-amber/30 bg-amber/10" },
  approved: { label: "Approved", cls: "text-ok border-ok/30 bg-ok/10" },
  denied: { label: "Denied", cls: "text-danger border-danger/30 bg-danger/10" },
  completed: { label: "Completed", cls: "text-accent border-accent/30 bg-accent/10" },
  cancelled: { label: "Cancelled", cls: "text-faint border-line bg-surface-2" },
};

export function StatusPill({ status }: { status: PaStatus }) {
  const s = MAP[status] ?? MAP.draft;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${s.cls}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}

export function GroundedBadge({ grounded }: { grounded: boolean }) {
  return grounded ? (
    <span className="inline-flex items-center gap-1 rounded-md border border-ok/30 bg-ok/10 px-1.5 py-0.5 text-[11px] font-medium text-ok">
      grounded
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-md border border-danger/30 bg-danger/10 px-1.5 py-0.5 text-[11px] font-medium text-danger">
      ungrounded
    </span>
  );
}
