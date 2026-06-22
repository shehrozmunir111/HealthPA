import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Activity, Shield, Sparkles } from "../components/icons";

export function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const DEMO_EMAIL = "demo@healthpa.local";
  const DEMO_PASSWORD = "demo12345";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const registered = searchParams.get("registered");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signIn(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Thesis panel — what this product actually does */}
      <div className="relative hidden flex-col justify-between overflow-hidden border-r border-line p-12 lg:flex">
        <div className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
            <Activity />
          </span>
          <span className="font-display text-lg font-bold tracking-tight">
            HealthPA
          </span>
        </div>

        <div className="max-w-md">
          <p className="eyebrow">Grounded medical coding</p>
          <h1 className="mt-3 font-display text-4xl font-bold leading-[1.1] tracking-tight">
            Every code earns its place in the&nbsp;
            <span className="text-accent">policy.</span>
          </h1>
          <p className="mt-4 text-muted">
            AI proposes ICD-10 and CPT codes from your payer policy, cites the
            exact passage, and a human signs off before anything is final.
          </p>

          {/* a single grounded code, as the product shows it */}
          <div className="card mt-8 max-w-sm p-4">
            <div className="flex items-center gap-2">
              <span className="rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
                ICD10
              </span>
              <span className="rounded-md border border-ok/30 bg-ok/10 px-1.5 py-0.5 text-[11px] font-medium text-ok">
                grounded
              </span>
            </div>
            <div className="mt-2 font-mono text-2xl font-bold">J18.9</div>
            <p className="mt-1 text-sm text-muted">
              Pneumonia, unspecified organism
            </p>
            <p className="mt-3 border-l-2 border-line pl-2.5 text-xs italic text-muted">
              "Pneumonia, unspecified organism is coded J18.9 under ICD-10-CM."
            </p>
          </div>
        </div>

        <div className="flex gap-6 text-xs text-faint">
          <span className="flex items-center gap-1.5">
            <Shield width={14} height={14} /> Tenant-isolated
          </span>
          <span className="flex items-center gap-1.5">
            <Sparkles width={14} height={14} /> Human-in-the-loop
          </span>
        </div>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center p-6">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          {/* Compact brand header — only on small screens (the left panel is hidden there) */}
          <div className="mb-6 lg:hidden">
            <div className="flex items-center gap-2.5">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
                <Activity />
              </span>
              <span className="font-display text-lg font-bold tracking-tight">
                HealthPA
              </span>
            </div>
            <p className="eyebrow mt-4">Grounded medical coding</p>
            <h1 className="mt-2 font-display text-2xl font-bold leading-tight tracking-tight">
              Every code earns its place in the&nbsp;
              <span className="text-accent">policy.</span>
            </h1>
          </div>

          {/* Demo credentials box — sits above the "Sign in" heading */}
          <div className="mb-5 rounded-lg border border-accent/30 bg-accent/5 p-3.5 text-sm">
            <div className="mb-1.5 font-medium text-accent">Try the demo account</div>
            <div className="space-y-0.5 font-mono text-xs text-muted">
              <div>Email: <span className="text-text">{DEMO_EMAIL}</span></div>
              <div>Password: <span className="text-text">{DEMO_PASSWORD}</span></div>
            </div>
            <button
              type="button"
              onClick={() => {
                setEmail(DEMO_EMAIL);
                setPassword(DEMO_PASSWORD);
              }}
              className="mt-2 text-xs font-medium text-accent hover:underline"
            >
              Fill demo credentials
            </button>
          </div>

          <h2 className="font-display text-2xl font-bold tracking-tight">
            Sign in
          </h2>
          {registered && (
            <div className="mt-4 rounded-lg border border-ok/30 bg-ok/10 px-3.5 py-2.5 text-sm text-ok">
              Account created. Please sign in.
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-sm text-danger">
              {error}
            </div>
          )}

          <p className="mt-1 text-sm text-muted">
            Continue to the coding console.
          </p>

          <label className="mt-7 block text-sm text-muted" htmlFor="email">
            Work email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field mt-1.5"
            autoComplete="username"
          />

          <label className="mt-4 block text-sm text-muted" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field mt-1.5"
            autoComplete="current-password"
          />

          <button type="submit" disabled={busy} className="btn-primary mt-6 w-full">
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="mt-5 text-center text-sm text-muted">
            Don't have an account?{" "}
            <Link to="/register" className="text-accent hover:underline">
              Sign up
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
