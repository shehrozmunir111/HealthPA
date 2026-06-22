import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listCases } from "../lib/api";
import type { PaCase } from "../lib/types";
import { StatusPill } from "../components/StatusPill";
import { ChevronRight, Search } from "../components/icons";

export function Dashboard() {
  const [cases, setCases] = useState<PaCase[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listCases()
      .then(setCases)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load cases")
      );
  }, []);

  const filtered = useMemo(() => {
    if (!cases) return [];
    const term = q.trim().toLowerCase();
    if (!term) return cases;
    return cases.filter((c) =>
      [c.request_number, c.patient, c.payer, c.status]
        .join(" ")
        .toLowerCase()
        .includes(term)
    );
  }, [cases, q]);

  const pending = cases?.filter(
    (c) => c.status === "pending" || c.status === "needs_info"
  ).length;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Prior authorization</p>
          <h1 className="mt-1.5 font-display text-3xl font-bold tracking-tight">
            Cases
          </h1>
          <p className="mt-1 text-sm text-muted">
            {error ? (
              <span className="text-danger">{error}</span>
            ) : cases ? (
              `${cases.length} cases · ${pending} awaiting your review`
            ) : (
              "Loading…"
            )}
          </p>
        </div>
        <label className="relative">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint">
            <Search />
          </span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search cases…"
            className="field w-64 pl-9"
          />
        </label>
      </div>

      <div className="mt-6 overflow-hidden card">
        {/* horizontal scroll on small screens so the wide table is never cut off */}
        <div className="overflow-x-auto">
          <div className="min-w-[620px]">
            <div className="grid grid-cols-[110px_1fr_140px_150px_40px] gap-3 border-b border-line px-4 py-2.5 font-mono text-[11px] uppercase tracking-wider text-faint">
              <span>Case</span>
              <span>Patient / note</span>
              <span>Payer</span>
              <span>Status</span>
              <span />
            </div>

            {!cases &&
              !error &&
              [0, 1, 2].map((i) => (
                <div key={i} className="px-4 py-4">
                  <div className="h-4 w-1/3 animate-pulse rounded bg-surface-2" />
                </div>
              ))}

            {error && (
              <div className="px-4 py-10 text-center text-sm text-muted">
                Couldn't load cases. Make sure the API server is running, then refresh.
              </div>
            )}

            {filtered.map((c) => (
              <Link
                key={c.id}
                to={`/cases/${c.id}`}
                className="grid grid-cols-[110px_1fr_140px_150px_40px] items-center gap-3 border-b border-line/60 px-4 py-3.5 transition last:border-0 hover:bg-surface-2/50"
              >
                <span className="font-mono text-sm text-accent">
                  {c.request_number}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-text">
                    {c.patient}
                  </span>
                  <span className="block truncate text-xs text-faint">
                    {c.clinical_notes}
                  </span>
                </span>
                <span className="truncate text-sm text-muted">{c.payer}</span>
                <span>
                  <StatusPill status={c.status} />
                </span>
                <span className="text-faint">
                  <ChevronRight />
                </span>
              </Link>
            ))}

            {cases && filtered.length === 0 && (
              <div className="px-4 py-10 text-center text-sm text-muted">
                No cases match "{q}".
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
