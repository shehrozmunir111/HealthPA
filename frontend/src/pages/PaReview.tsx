import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { extract, getCase, review } from "../lib/api";
import type { Citation, PaCase, ProposedCode, ProposedCodes } from "../lib/types";
import { CodeCard } from "../components/CodeCard";
import { StatusPill } from "../components/StatusPill";
import { Check, FileText, Sparkles, X } from "../components/icons";

type Phase = "idle" | "extracting" | "review" | "done";

export function PaReview() {
  const { id = "" } = useParams();
  const [pa, setPa] = useState<PaCase | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [proposed, setProposed] = useState<ProposedCodes | null>(null);
  const [kept, setKept] = useState<Set<string>>(new Set());
  const [finalCodes, setFinalCodes] = useState<ProposedCode[]>([]);
  const [reviewStatus, setReviewStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getCase(id).then(setPa);
  }, [id]);

  async function runExtract() {
    setError("");
    setPhase("extracting");
    try {
      const result = await extract(id);
      setProposed(result.proposed);
      setKept(new Set(result.proposed.codes.map((c) => c.code)));
      setPhase("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
      setPhase("idle");
    }
  }

  function toggle(code: string) {
    setKept((prev) => {
      const next = new Set(prev);
      next.has(code) ? next.delete(code) : next.add(code);
      return next;
    });
  }

  const total = proposed?.codes.length ?? 0;
  const keptCount = kept.size;
  const decision: "approve" | "edit" =
    keptCount === total ? "approve" : "edit";

  async function finalize(kind: "approve" | "reject") {
    if (!proposed) return;
    setBusy(true);
    setError("");
    try {
      if (kind === "reject") {
        const r = await review(id, "reject");
        setFinalCodes(r.final_codes);
        setReviewStatus(r.status);
      } else {
        const editedCodes = proposed.codes.filter((c) => kept.has(c.code));
        const r =
          decision === "approve"
            ? await review(id, "approve")
            : await review(id, "edit", editedCodes);
        setFinalCodes(r.final_codes.length ? r.final_codes : editedCodes);
        setReviewStatus(r.status);
      }
      setPhase("done");
      // Refresh the header status pill (approve advances the PA's FSM status).
      getCase(id).then(setPa).catch(() => {});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review failed");
    } finally {
      setBusy(false);
    }
  }

  const evidence = useMemo<Citation[]>(() => {
    if (!proposed) return [];
    const seen = new Set<string>();
    const out: Citation[] = [];
    for (const code of proposed.codes)
      for (const cite of code.citations) {
        const key = `${cite.source_doc}#${cite.chunk}-${cite.quote}`;
        if (!seen.has(key)) {
          seen.add(key);
          out.push(cite);
        }
      }
    return out;
  }, [proposed]);

  if (!pa) return <div className="text-muted">Loading case…</div>;

  return (
    <div>
      <Link to="/" className="text-sm text-muted hover:text-text">
        ← Cases
      </Link>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-lg text-accent">
              {pa.request_number}
            </span>
            <StatusPill status={pa.status} />
          </div>
          <h1 className="mt-1 font-display text-2xl font-bold tracking-tight">
            {pa.patient}
          </h1>
        </div>
        <div className="text-right text-sm text-muted">
          <div className="font-mono text-xs uppercase tracking-wider text-faint">
            Payer
          </div>
          {pa.payer}
        </div>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_1.1fr]">
        {/* Left: clinical note + policy evidence */}
        <div className="space-y-5">
          <section className="card relative overflow-hidden p-5">
            <p className="eyebrow flex items-center gap-1.5">
              <FileText width={13} height={13} /> Clinical note
            </p>
            <p className="mt-3 text-sm leading-relaxed text-text/90">
              {pa.clinical_notes}
            </p>
            {phase === "extracting" && (
              <div className="pointer-events-none absolute inset-x-0 top-0 h-16 animate-scan bg-gradient-to-b from-accent/25 to-transparent" />
            )}
          </section>

          {evidence.length > 0 && (
            <section className="card p-5">
              <p className="eyebrow">Policy evidence</p>
              <div className="mt-3 space-y-3">
                {evidence.map((cite, i) => (
                  <div key={i} className="text-sm">
                    <div className="font-mono text-[11px] text-accent">
                      {cite.source_doc}
                      {cite.chunk != null ? `#${cite.chunk}` : ""}
                    </div>
                    <p className="mt-1 border-l-2 border-line pl-2.5 italic text-muted">
                      "{cite.quote}"
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Right: AI panel */}
        <div>
          {error && (
            <div className="mb-4 rounded-lg border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-sm text-danger">
              {error}
            </div>
          )}
          {phase === "idle" && (
            <section className="card flex flex-col items-start p-6">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent/15 text-accent">
                <Sparkles />
              </span>
              <h2 className="mt-4 font-display text-xl font-bold tracking-tight">
                Grounded code extraction
              </h2>
              <p className="mt-2 text-sm text-muted">
                Retrieve this payer's policy, grade relevance, and propose ICD-10 /
                CPT codes — each one cited to the policy passage that supports it.
                Nothing is final until you approve it.
              </p>
              <button onClick={runExtract} className="btn-primary mt-5">
                <Sparkles width={16} height={16} /> Run extraction
              </button>
            </section>
          )}

          {phase === "extracting" && (
            <section className="card p-6">
              <p className="eyebrow">Working</p>
              <ul className="mt-4 space-y-3 text-sm">
                {["Retrieving payer policy", "Grading relevance", "Extracting grounded codes"].map(
                  (step, i) => (
                    <li key={step} className="flex items-center gap-3 text-muted">
                      <span
                        className="h-2 w-2 rounded-full bg-accent animate-pulseline"
                        style={{ animationDelay: `${i * 0.25}s` }}
                      />
                      {step}…
                    </li>
                  )
                )}
              </ul>
              <p className="mt-4 text-xs text-faint">
                Running on a local model — this can take up to a minute.
              </p>
            </section>
          )}

          {phase === "review" && proposed && (
            <section>
              <div className="flex items-center gap-2 rounded-lg border border-amber/30 bg-amber/10 px-3.5 py-2.5 text-sm text-amber">
                <span className="h-1.5 w-1.5 rounded-full bg-amber animate-pulseline" />
                Pending your review — {keptCount} of {total} code(s) selected
              </div>
              {proposed.rationale && (
                <p className="mt-3 text-xs text-faint">{proposed.rationale}</p>
              )}

              <div className="mt-4 space-y-3">
                {proposed.codes.map((code) => (
                  <CodeCard
                    key={code.code}
                    code={code}
                    kept={kept.has(code.code)}
                    onToggle={() => toggle(code.code)}
                  />
                ))}
                {total === 0 && (
                  <div className="card p-5 text-sm text-muted">
                    No policy-grounded codes were found for this note. You can
                    reject and request more information.
                  </div>
                )}
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  onClick={() => finalize("approve")}
                  disabled={busy || keptCount === 0}
                  className="btn-primary"
                >
                  <Check width={16} height={16} />
                  {decision === "approve"
                    ? "Approve all"
                    : `Save edits (${keptCount})`}
                </button>
                <button
                  onClick={() => finalize("reject")}
                  disabled={busy}
                  className="btn-danger"
                >
                  <X width={16} height={16} /> Reject
                </button>
              </div>
            </section>
          )}

          {phase === "done" && (
            <section>
              <div
                className={`flex items-center gap-2 rounded-lg border px-3.5 py-2.5 text-sm ${
                  reviewStatus.includes("reject")
                    ? "border-danger/30 bg-danger/10 text-danger"
                    : "border-ok/30 bg-ok/10 text-ok"
                }`}
              >
                <Check width={16} height={16} />
                Finalized · {reviewStatus}
              </div>

              <div className="mt-4 space-y-3">
                {finalCodes.map((code) => (
                  <CodeCard key={code.code} code={code} />
                ))}
                {finalCodes.length === 0 && (
                  <div className="card p-5 text-sm text-muted">
                    No codes were applied to this case.
                  </div>
                )}
              </div>

              <button
                onClick={() => {
                  setPhase("idle");
                  setProposed(null);
                  setFinalCodes([]);
                }}
                className="btn-ghost mt-5"
              >
                Run again
              </button>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
