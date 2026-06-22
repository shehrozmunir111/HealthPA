import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listHospitals, register as apiRegister } from "../lib/api";
import type { Hospital } from "../lib/types";
import { Activity, Shield, Sparkles } from "../components/icons";

export function Register() {
  const navigate = useNavigate();
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [hospitalId, setHospitalId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listHospitals().then(setHospitals);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiRegister({
        email,
        password,
        first_name: firstName,
        last_name: lastName,
        hospital_id: hospitalId,
      });
      navigate("/login?registered=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
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

          <h2 className="font-display text-2xl font-bold tracking-tight">
            Create account
          </h2>
          <p className="mt-1 text-sm text-muted">
            Join your hospital's coding console.
          </p>

          {error && (
            <div className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-sm text-danger">
              {error}
            </div>
          )}

          <div className="mt-6 grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-muted" htmlFor="firstName">
                First name
              </label>
              <input
                id="firstName"
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="field mt-1.5"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-muted" htmlFor="lastName">
                Last name
              </label>
              <input
                id="lastName"
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="field mt-1.5"
                required
              />
            </div>
          </div>

          <label className="mt-4 block text-sm text-muted" htmlFor="regEmail">
            Work email
          </label>
          <input
            id="regEmail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="field mt-1.5"
            autoComplete="off"
            required
          />

          <label className="mt-4 block text-sm text-muted" htmlFor="regPassword">
            Password
          </label>
          <input
            id="regPassword"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="field mt-1.5"
            autoComplete="new-password"
            minLength={8}
            required
          />

          <label className="mt-4 block text-sm text-muted" htmlFor="hospitalId">
            Hospital
          </label>
          <select
            id="hospitalId"
            value={hospitalId}
            onChange={(e) => setHospitalId(e.target.value)}
            className="field mt-1.5"
            required
          >
            <option value="">Select a hospital…</option>
            {hospitals.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name} ({h.code})
              </option>
            ))}
          </select>

          <button type="submit" disabled={busy || !hospitalId} className="btn-primary mt-6 w-full">
            {busy ? "Creating account…" : "Create account"}
          </button>

          <p className="mt-5 text-center text-sm text-muted">
            Already have an account?{" "}
            <Link to="/login" className="text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
