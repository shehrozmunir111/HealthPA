import { useEffect, useRef, useState, type FormEvent } from "react";
import { ask, listCases } from "../lib/api";
import type { AskResult, PaCase } from "../lib/types";
import { Message, Sparkles } from "../components/icons";

interface Turn {
  q: string;
  a: AskResult | null;
}

const SUGGESTIONS = [
  "Which CPT applies to a two-view chest x-ray?",
  "How is pneumonia, unspecified organism coded?",
  "What are the knee MRI authorization criteria?",
];

export function Ask() {
  const [cases, setCases] = useState<PaCase[]>([]);
  const [caseId, setCaseId] = useState("");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listCases().then((rows) => {
      setCases(rows);
      if (rows[0]) setCaseId(rows[0].id);
    });
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    setInput("");
    setTurns((t) => [...t, { q: text, a: null }]);
    setBusy(true);
    try {
      const a = await ask(caseId || "demo", text);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, a } : turn)));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setTurns((t) =>
        t.map((turn, i) =>
          i === t.length - 1
            ? { ...turn, a: { answer: msg, grounded: false, sources: [], status: "error" } }
            : turn
        )
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Policy assistant</p>
          <h1 className="mt-1.5 font-display text-3xl font-bold tracking-tight">
            Ask the policy
          </h1>
          <p className="mt-1 text-sm text-muted">
            Answers are grounded in your hospital's ingested payer policy and
            cite their source.
          </p>
        </div>
        <label className="text-sm">
          <span className="mr-2 text-faint">Context</span>
          <select
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            className="field w-48"
          >
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.request_number} · {c.payer}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-5 flex-1 space-y-5 overflow-y-auto pr-1">
        {turns.length === 0 && (
          <div className="card p-6">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-accent/15 text-accent">
              <Message />
            </span>
            <p className="mt-4 text-sm text-muted">Try a question:</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="btn-ghost text-xs"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent/15 px-4 py-2.5 text-sm text-text">
                {turn.q}
              </p>
            </div>
            <div className="card max-w-[85%] p-4">
              {turn.a ? (
                <>
                  <div className="flex items-center gap-2">
                    <span className="text-accent">
                      <Sparkles width={15} height={15} />
                    </span>
                    {turn.a.grounded ? (
                      <span className="rounded-md border border-ok/30 bg-ok/10 px-1.5 py-0.5 text-[11px] text-ok">
                        grounded
                      </span>
                    ) : (
                      <span className="rounded-md border border-amber/30 bg-amber/10 px-1.5 py-0.5 text-[11px] text-amber">
                        no policy match
                      </span>
                    )}
                  </div>
                  <p className="mt-2.5 whitespace-pre-line text-sm leading-relaxed text-text/90">
                    {turn.a.answer}
                  </p>
                  {turn.a.sources.length > 0 && (
                    <div className="mt-3 border-t border-line pt-3">
                      <p className="font-mono text-[10px] uppercase tracking-wider text-faint">
                        Sources
                      </p>
                      <div className="mt-2 space-y-1.5">
                        {turn.a.sources.map((s, j) => (
                          <div key={j} className="text-xs text-muted">
                            <span className="font-mono text-accent">
                              {s.source_doc ?? s.tool}
                              {s.chunk != null ? `#${s.chunk}` : ""}
                            </span>
                            {" — "}
                            {s.detail.slice(0, 120)}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <span className="text-sm text-muted">Thinking…</span>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-4 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about coding policy…"
          className="field flex-1"
        />
        <button type="submit" disabled={busy} className="btn-primary">
          Ask
        </button>
      </form>
    </div>
  );
}
