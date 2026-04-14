"use client";

import { ReactNode, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAppSession } from "@/components/session-provider";
import { terminateSession } from "@/lib/api";

const navigation = [
  { href: "/",          label: "Home" },
  { href: "/analyze",   label: "Repository" },
  { href: "/issues",    label: "Issues" },
  { href: "/scan",      label: "Security" },
  { href: "/pr-review", label: "PR Review" },
  { href: "/logs",      label: "Logs" },
  { href: "/result",    label: "Result" },
  { href: "/approval",  label: "Approval" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { state, resetState } = useAppSession();
  const [terminating, setTerminating] = useState(false);
  const [terminateError, setTerminateError] = useState<string | null>(null);

  async function handleTerminateSession() {
    if (terminating || !state.sessionId) return;
    setTerminating(true);
    setTerminateError(null);
    try {
      await terminateSession(state.sessionId);
    } catch (error) {
      setTerminateError(error instanceof Error ? error.message : "Unable to terminate session.");
    } finally {
      resetState();
      setTerminating(false);
      router.push("/");
    }
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-8">

        {/* Header */}
        <header className="relative overflow-hidden rounded-[32px] border-2 border-border bg-surface p-6 shadow-[8px_8px_0px_0px] shadow-border lg:flex lg:items-end lg:justify-between">
          <div className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-primary-soft blur-2xl" />
          <div className="pointer-events-none absolute -left-8 bottom-0 h-24 w-24 rounded-full bg-accent-soft blur-2xl" />
          <div className="space-y-2">
            <p className="font-mono text-sm uppercase tracking-[0.4em] text-muted">OpenDev AI</p>
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
              Autonomous GitHub repair and security workflow
            </h1>
            <p className="max-w-3xl font-mono text-sm text-muted">
              Paste a repository URL — the agent analyses the code, fixes open issues via fork PR, scans for secrets and vulnerabilities, and reviews pull requests.
            </p>
            {terminateError && (
              <p className="max-w-2xl font-mono text-sm text-danger">{terminateError}</p>
            )}
          </div>
          <div className="mt-4 space-y-3 rounded-2xl border-2 border-border bg-white/70 p-4 font-mono text-sm text-muted backdrop-blur lg:mt-0 lg:min-w-[220px]">
            <p>Session: {state.sessionId ? state.sessionId.slice(0, 12) + "…" : "not started"}</p>
            <p className="truncate">Repo: {state.repo?.full_name ?? "none selected"}</p>
            {state.repo && (
              <p>Issues: {state.issues.length} open</p>
            )}
            <button
              type="button"
              disabled={!state.sessionId || terminating}
              onClick={handleTerminateSession}
              className="rounded-full border-2 border-border bg-danger px-4 py-2 text-xs uppercase tracking-[0.25em] text-white transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:bg-[#f3c3c3] disabled:text-white/80"
            >
              {terminating ? "Terminating…" : "Terminate session"}
            </button>
          </div>
        </header>

        {/* Nav */}
        <nav className="flex flex-wrap gap-3">
          {navigation.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full border-2 px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] transition-transform hover:-translate-y-0.5 ${
                  active
                    ? "border-border bg-primary text-white shadow-[4px_4px_0px_0px] shadow-border"
                    : "border-border bg-white text-text"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
