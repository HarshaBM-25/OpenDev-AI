"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { fetchLogs } from "@/lib/api";

export default function LogsPage() {
  const { state, hydrateComplete, mergeState } = useAppSession();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!state.sessionId) return;
    const id = state.sessionId;
    let active = true;
    async function poll() {
      try {
        const data = await fetchLogs(id);
        if (!active) return;
        mergeState({ logs: data.logs, pendingApproval: data.pending_action });
      } catch { /* ignore */ }
    }
    poll();
    const t = setInterval(poll, 3000);
    return () => { active = false; clearInterval(t); };
  }, [state.sessionId, mergeState]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.logs]);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Logs">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.sessionId) {
    return (
      <Panel title="No logs available" eyebrow="Logs">
        <div className="space-y-4 font-mono text-sm text-muted">
          <p>Start a session and run an action to see logs here.</p>
          <Link href="/" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go home
          </Link>
        </div>
      </Panel>
    );
  }

  const levelColor: Record<string, string> = {
    info: "text-primary",
    warn: "text-[#b45309]",
    warning: "text-[#b45309]",
    error: "text-danger",
    debug: "text-muted",
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
      {/* Terminal log */}
      <Panel title="Execution logs" eyebrow={`${state.logs.length} entries · auto-refreshing`}>
        <pre className="max-h-[42rem] overflow-auto border-2 border-primary bg-bg p-5 font-mono text-xs leading-7 text-text">
          {state.logs.length === 0 ? (
            "Waiting for agent output…"
          ) : (
            state.logs.map((entry, i) => {
              const ts = new Date(entry.timestamp).toLocaleTimeString();
              return (
                <span key={i} className="block">
                  <span className="text-muted">[{ts}]</span>
                  {" "}
                  <span className={levelColor[entry.level] || "text-muted"}>[{entry.level.toUpperCase()}]</span>
                  {" "}
                  <span className="text-muted">[{entry.step}]</span>
                  {" "}
                  <span>{entry.message}</span>
                </span>
              );
            })
          )}
          <div ref={bottomRef} />
        </pre>
      </Panel>

      {/* Sidebar */}
      <div className="space-y-6">
        <Panel title="Run state" eyebrow="Summary">
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <StatusPill label={state.result?.action ?? "idle"} tone="neutral" />
              <StatusPill
                label={state.result?.status ?? "waiting"}
                tone={
                  state.result?.status === "failed"
                    ? "danger"
                    : state.pendingApproval
                    ? "warning"
                    : state.result?.status === "approved"
                    ? "success"
                    : "neutral"
                }
              />
            </div>
            <p className="font-mono text-sm leading-7 text-muted">
              {state.result?.summary ?? "Trigger a fix or scan from the issues or security pages."}
            </p>
            {state.pendingApproval && (
              <div className="rounded-[16px] border-2 border-accent bg-accent-soft p-4">
                <p className="font-mono text-xs uppercase tracking-[0.25em] text-text mb-2">
                  Action pending approval
                </p>
                <p className="font-mono text-sm text-muted">
                  Review the diff and approve or reject the PR.
                </p>
              </div>
            )}
          </div>
        </Panel>

        <Panel title="Navigation" eyebrow="Quick links">
          <div className="flex flex-wrap gap-3">
            {state.pendingApproval && (
              <Link href="/approval" className="rounded-full border-2 border-border bg-accent px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
                Approve PR
              </Link>
            )}
            <Link href="/result" className="rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
              View result
            </Link>
            <Link href="/approval" className="rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white transition hover:-translate-y-0.5">
              Approval
            </Link>
            <Link href="/issues" className="rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
              Issues
            </Link>
            <Link href="/scan" className="rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
              Security
            </Link>
          </div>
        </Panel>
      </div>
    </div>
  );
}
