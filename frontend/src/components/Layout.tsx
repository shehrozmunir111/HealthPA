import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Activity, Grid, LogOut, Message } from "./icons";

const nav = [
  { to: "/", label: "Cases", icon: Grid, end: true },
  { to: "/ask", label: "Policy Q&A", icon: Message, end: false },
];

export function Layout() {
  const { email, signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface/60 px-3 py-5 backdrop-blur md:flex">
        <div className="flex items-center gap-2.5 px-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent/15 text-accent">
            <Activity />
          </span>
          <div className="leading-tight">
            <div className="font-display text-[15px] font-bold tracking-tight">
              HealthPA
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-faint">
              coding console
            </div>
          </div>
        </div>

        <nav className="mt-7 flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  isActive
                    ? "bg-accent/12 text-accent"
                    : "text-muted hover:bg-surface-2 hover:text-text"
                }`
              }
            >
              <Icon />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto rounded-lg border border-line bg-surface-2/60 p-3">
          <div className="truncate text-sm text-text">{email ?? "Reviewer"}</div>
          <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-faint">
            medical coder
          </div>
          <button
            type="button"
            onClick={() => {
              signOut();
              navigate("/login");
            }}
            className="mt-2.5 flex items-center gap-2 text-xs text-muted hover:text-danger"
          >
            <LogOut width={14} height={14} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
