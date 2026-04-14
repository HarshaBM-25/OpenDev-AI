"use client";

import Link from "next/link";
import { useState } from "react";
import { DiffViewer } from "@/components/diff-viewer";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { createIssuesFromFindings } from "@/lib/api";
import { Finding } from "@/lib/types";

export default function ResultPage() {
  const { state, hydrateComplete } = useAppSession();
  const [creatingIssues, setCreatingIssues] = useState(false);
  const [issuesMsg, setIssuesMsg] = useState<string | null>(null);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Result">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.result) {
    return (
      <Panel title="No result available" eyebrow="Result">
        <div className="space-y-4 font-mono text-sm text-muted">
          <p>Run an issue fix or security scan first.</p>
          <Link href="/issues" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go to issues
          </Link>
        </div>
      </Panel>
    );
  }

  const result = state.result;
  const allFindings: Finding[] = [
    ...(result.all_findings ?? []),
    ...(result.findings ?? []),
  ].filter((f, i, arr) => arr.findIndex((x) => x.id === f.id) === i);

  const statusTone =
    result.status === "failed" ? "danger" as const :
    result.status === "awaiting_approval" ? "warning" as const :
    result.status === "approved" ? "success" as const : "neutral" as const;

  const sevTone = (s: string) =>
    s === "high" ? "danger" as const : s === "medium" ? "warning" as const : "neutral" as const;

  async function handleCreateIssues() {
    if (!state.sessionId) return;
    setCreatingIssues(true);
    try {
      const r = await createIssuesFromFindings(state.sessionId);
      setIssuesMsg(`✓ Created ${r.issues_created} GitHub issue${r.issues_created !== 1 ? "s" : ""}.`);
    } catch (err) {
      setIssuesMsg(err instanceof Error ? err.message : "Failed to create issues.");
    } finally {
      setCreatingIssues(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <Panel title="Action summary" eyebrow="Result">
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <StatusPill label={result.action} tone="neutral" />
            <StatusPill label={result.status} tone={statusTone} />
            {result.fork && <StatusPill label={`fork: ${result.fork.full_name}`} tone="neutral" />}
          </div>
          <p className="font-mono text-sm leading-7 text-muted">{result.summary}</p>

          {result.pull_request && (
            <div className="rounded-[20px] border-2 border-primary bg-primary-soft p-4 font-mono text-sm">
              <p className="mb-2 text-xs uppercase tracking-[0.25em] text-primary">Pull request created</p>
              <a href={result.pull_request.url} target="_blank" rel="noreferrer" className="underline text-text">
                PR #{result.pull_request.number}: {result.pull_request.title}
              </a>
            </div>
          )}

          {result.create_issues_available && !issuesMsg && (
            <button
              type="button"
              disabled={creatingIssues}
              onClick={handleCreateIssues}
              className="rounded-full border-2 border-border bg-accent px-5 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text shadow-[3px_3px_0px_0px] shadow-border transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {creatingIssues ? "Creating GitHub issues…" : "📌 Create GitHub issues from findings"}
            </button>
          )}
          {issuesMsg && (
            <p className="rounded-2xl border-2 border-[#15803d] bg-[#bbf7d0] p-3 font-mono text-sm text-[#15803d]">
              {issuesMsg}
            </p>
          )}
        </div>
      </Panel>

      {/* Security score */}
      {result.security_score && (
        <Panel title="Security score" eyebrow="Analysis">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: "Grade", value: result.security_score.grade },
              { label: "Score", value: `${result.security_score.score}/100` },
              { label: "High severity", value: String(result.security_score.by_severity.high) },
              { label: "Total findings", value: String(result.security_score.total_findings) },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-[20px] border-2 border-border bg-bg p-4 text-center">
                <p className="text-3xl font-bold text-text">{value}</p>
                <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted mt-1">{label}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 font-mono text-sm text-muted">{result.security_score.summary}</p>
        </Panel>
      )}

      {/* Test results */}
      {result.test_results && result.test_results.length > 0 && (
        <Panel title="Test results" eyebrow="Validation">
          <div className="space-y-4">
            {result.test_results.map((item) => (
              <div key={item.command} className="rounded-[20px] border-2 border-border bg-white p-4">
                <div className="mb-3 flex flex-wrap gap-2">
                  <StatusPill label={item.command} tone="neutral" />
                  <StatusPill
                    label={item.status}
                    tone={item.status === "failed" ? "danger" : item.status === "passed" ? "success" : "neutral"}
                  />
                </div>
                {(item.stdout || item.stderr) && (
                  <pre className="max-h-32 overflow-auto font-mono text-xs leading-6 text-muted">
                    {item.stdout || item.stderr}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Findings */}
      {allFindings.length > 0 && (
        <Panel title={`Security findings (${allFindings.length})`} eyebrow="Scan output">
          <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-1">
            {allFindings.map((f) => (
              <div key={f.id} className="rounded-[16px] border-2 border-border bg-white p-4 space-y-2">
                <div className="flex flex-wrap gap-2">
                  <StatusPill label={f.type.replace(/_/g, " ")} tone={sevTone(f.severity)} />
                  <StatusPill label={f.severity} tone={sevTone(f.severity)} />
                  {f.file && (
                    <span className="font-mono text-xs text-muted">
                      {f.file}{f.line ? `:${f.line}` : ""}
                    </span>
                  )}
                </div>
                {f.description && <p className="font-mono text-xs text-muted">{f.description}</p>}
                {f.preview && (
                  <pre className="overflow-x-auto rounded-[12px] border border-border bg-bg px-3 py-2 font-mono text-xs leading-6 text-text">
                    {f.preview}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Diff */}
      <Panel title="Proposed diff" eyebrow="Git preview">
        <DiffViewer diff={result.diff} />
      </Panel>

      {/* Nav */}
      <div className="flex flex-wrap gap-3">
        <Link href="/approval" className="rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
          Approval
        </Link>
        <Link href="/logs" className="rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
          View logs
        </Link>
        <Link href="/issues" className="rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
          Back to issues
        </Link>
      </div>
    </div>
  );
}
