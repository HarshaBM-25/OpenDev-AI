"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { fetchLogs, forkFixIssue } from "@/lib/api";
import { Issue } from "@/lib/types";

export default function IssuesPage() {
  const router = useRouter();
  const { state, hydrateComplete, mergeState } = useAppSession();
  const [loadingIssue, setLoadingIssue] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Issues">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.sessionId || !state.repo) {
    return (
      <Panel title="No repository session" eyebrow="Issues">
        <div className="space-y-4 font-mono text-sm text-muted">
          <p>Start from the home page first.</p>
          <Link href="/" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go home
          </Link>
        </div>
      </Panel>
    );
  }

  const issues = state.issues;

  async function handleForkFix(issue: Issue) {
    setLoadingIssue(issue.number);
    setError(null);
    mergeState({ selectedIssue: issue });
    try {
      const result = await forkFixIssue(state.sessionId!, issue.number);
      const logPayload = await fetchLogs(state.sessionId!);
      mergeState({
        result,
        logs: logPayload.logs,
        pendingApproval: result.status === "awaiting_approval",
      });
      router.push("/logs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fork-fix failed.");
    } finally {
      setLoadingIssue(null);
    }
  }

  if (issues.length === 0) {
    return (
      <div className="space-y-6">
        <Panel title="No open issues" eyebrow="Issues">
          <div className="space-y-4 font-mono text-sm text-muted">
            <p>This repository has no open issues. Run a security scan to find vulnerabilities and exposed secrets.</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/scan" className="inline-flex rounded-full border-2 border-border bg-danger px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
                Run security scan
              </Link>
              <Link href="/pr-review" className="inline-flex rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
                Review a PR
              </Link>
            </div>
          </div>
        </Panel>
      </div>
    );
  }

  const complexityTone = (c: string) =>
    c === "complex" ? "danger" as const : c === "simple" ? "success" as const : "neutral" as const;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
      {/* Issue list */}
      <Panel title="Open issues" eyebrow={`${state.repo.full_name} · ${issues.length} issues`}>
        <div className="space-y-4">
          {issues.map((issue) => {
            const isSelected = state.selectedIssue?.number === issue.number;
            const isLoading = loadingIssue === issue.number;
            return (
              <div
                key={issue.number}
                className={`rounded-[20px] border-2 p-4 transition ${
                  isSelected ? "border-primary bg-primary-soft" : "border-border bg-white"
                }`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs text-muted">#{issue.number}</span>
                      <h3 className="font-semibold text-text">{issue.title}</h3>
                      <StatusPill label={issue.complexity} tone={complexityTone(issue.complexity)} />
                    </div>
                    {issue.body && (
                      <p className="line-clamp-2 font-mono text-sm leading-6 text-muted">{issue.body}</p>
                    )}
                    {issue.labels.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {issue.labels.map((l) => <StatusPill key={l} label={l} tone="neutral" />)}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <a
                      href={issue.url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-full border-2 border-border bg-white px-3 py-1.5 font-mono text-xs uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5"
                    >
                      View ↗
                    </a>
                    <button
                      type="button"
                      disabled={loadingIssue !== null}
                      onClick={() => handleForkFix(issue)}
                      className="rounded-full border-2 border-border bg-primary px-4 py-1.5 font-mono text-xs uppercase tracking-[0.25em] text-white shadow-[3px_3px_0px_0px] shadow-border transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:bg-surface-strong disabled:text-muted disabled:shadow-none"
                    >
                      {isLoading ? "Fixing…" : "🔀 Fork & Fix"}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {error && (
            <p className="rounded-2xl border-2 border-danger bg-white p-4 font-mono text-sm text-danger">{error}</p>
          )}
        </div>
      </Panel>

      {/* Sidebar */}
      <div className="space-y-6">
        <Panel title="Repository" eyebrow="Active session">
          <div className="space-y-3 font-mono text-sm text-muted">
            <div className="rounded-[16px] border-2 border-border bg-bg p-4">
              <p className="mb-1 text-xs uppercase tracking-[0.25em]">Repository</p>
              <p className="text-lg font-semibold text-text">{state.repo.full_name}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusPill label={state.repo.language ?? "unknown"} tone="neutral" />
              <StatusPill label={`${state.repo.open_issues_count} issues`} tone="neutral" />
              <StatusPill label={state.repo.default_branch} tone="neutral" />
            </div>
            <p className="leading-7">{state.repo.description ?? "No description."}</p>
            <div className="flex flex-wrap gap-2">
              <Link href="/analyze" className="rounded-full border-2 border-border bg-white px-3 py-1 text-xs uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
                ← Analysis
              </Link>
              <Link href="/scan" className="rounded-full border-2 border-border bg-danger px-3 py-1 text-xs uppercase tracking-[0.25em] text-white transition hover:-translate-y-0.5">
                Security scan
              </Link>
            </div>
          </div>
        </Panel>

        <Panel title="How Fork & Fix works" eyebrow="Workflow">
          <div className="space-y-3 font-mono text-sm text-muted">
            {[
              "Forks the repo into the bot account",
              "Clones the fork, creates a fix branch",
              "LLM generates a production-safe patch",
              "Runs the project's test suite",
              "Stages commit — awaits your approval",
              "On approve: pushes to fork, opens cross-fork PR to original owner",
            ].map((step, i) => (
              <div key={i} className="flex gap-3">
                <span className="rounded-full border-2 border-border bg-accent-soft px-2 py-0.5 text-xs font-bold text-text shrink-0">
                  {i + 1}
                </span>
                <span className="leading-6">{step}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
