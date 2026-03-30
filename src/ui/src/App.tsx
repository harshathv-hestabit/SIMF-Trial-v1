import { Card, CardContent, Chip } from "@heroui/react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { ClientsPage } from "./pages/ClientsPage";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { OpsPage } from "./pages/OpsPage";

export function App() {
  return (
    <ErrorBoundary>
      <div className="min-h-screen text-[var(--text-1)]">
        <div className="mx-auto flex min-h-screen w-full max-w-[1500px] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <header className="grid gap-4 rounded-[1.75rem] border border-[var(--border-1)] bg-[linear-gradient(180deg,rgba(14,20,38,0.88),rgba(18,24,44,0.72))] p-5 shadow-[0_18px_70px_rgba(1,5,20,0.45)] backdrop-blur-xl">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.35em] text-[var(--accent-magenta)]">
                  SMIF Control Surface
                </p>
                <h1 className="mt-1 text-3xl font-semibold tracking-[-0.04em] text-white">
                  Cosmic Operations Console
                </h1>
                <p className="mt-1 text-sm text-[var(--text-2)]">
                  React interface for ops telemetry and client intelligence workflows.
                </p>
              </div>
              <Chip
                variant="soft"
                className="border border-[var(--border-2)] bg-[rgba(255,78,184,0.12)] px-3 text-[var(--text-1)]"
              >
                HeroUI + Vite
              </Chip>
            </div>
            <nav className="flex flex-wrap gap-2 text-sm font-medium">
              <NavItem to="/ops" label="Ops Dashboard" />
              <NavItem to="/clients" label="Client Feed" />
            </nav>
          </header>

          <Card className="overflow-hidden border border-[var(--border-1)] bg-[linear-gradient(180deg,rgba(12,18,33,0.84),rgba(15,20,37,0.74))] shadow-[0_16px_60px_rgba(1,5,20,0.4)]">
            <CardContent className="p-0">
              <Routes>
                <Route path="/" element={<Navigate replace to="/ops" />} />
                <Route path="/ops" element={<OpsPage />} />
                <Route path="/clients" element={<ClientsPage />} />
                <Route path="*" element={<Navigate replace to="/ops" />} />
              </Routes>
            </CardContent>
          </Card>
        </div>
      </div>
    </ErrorBoundary>
  );
}

function NavItem(props: { to: string; label: string }) {
  return (
    <NavLink
      to={props.to}
      className={({ isActive }) =>
        [
          "rounded-full border px-4 py-2 transition",
          isActive
            ? "border-[rgba(255,78,184,0.28)] bg-[linear-gradient(90deg,rgba(96,100,255,0.42),rgba(255,78,184,0.28))] text-white"
            : "border-[var(--border-1)] bg-[rgba(255,255,255,0.03)] text-[var(--text-2)] hover:border-[rgba(115,166,255,0.3)] hover:bg-[rgba(115,166,255,0.08)] hover:text-white",
        ].join(" ")
      }
    >
      {props.label}
    </NavLink>
  );
}
