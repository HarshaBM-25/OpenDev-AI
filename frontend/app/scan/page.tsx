"use client";

import Link from "next/link";
import { useState } from "react";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { createIssuesFromFindings, fetchLogs, runSecurityScan } from "@/lib/api";
import { Finding } from "@/lib/types";

export default function ScanPage() {
  const { state, hydrateComplete, mergeState } = useAppSession();
  const [scanning, setScanning] = useState(false);
  const [creatingIssues, setCreatingIssues] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [issuesCreated, setIssuesCreated] = useState<number | null>(null);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Security">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.sessionId) {
    return (
      <Panel title="No session" eyebrow="Security">
        <div className="space-y-4">
          <p className="font-mono text-sm text-muted">Load a repository first.</p>
          <Link href="/" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go home
          </Link>
        </div>
      </Panel>
    );
  }

  const result = state.result?.action === "security_scan" ? state.result : null;
  const allFindings: Finding[] = result?.all_findings ?? [];
  const vulnFindings: Finding[] = result?.vuln_findings ?? [];
  const secretFindings: Finding[] = result?.secret_findings ?? [];
  const score = result?.security_score;

  async function handleScan() {
    setScanning(true);
    setError(null);
    setInfo(null);
    setIssuesCreated(null);
    try {
      const r = await runSecurityScan(state.sessionId!);
      const logs = await fetchLogs(state.sessionId!);
      mergeState({ result: r, logs: logs.logs });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed.");
    } finally {
      setScanning(false);
    }
  }

  async function handleCreateIssues() {
    setCreatingIssues(true);
    setError(null);
    setInfo(null);
    try {
      const r = await createIssuesFromFindings(state.sessionId!);
      setIssuesCreated(r.issues_created);
      if (r.status === "nothing_to_create") {
        setInfo("No high/medium severity findings to convert into GitHub issues.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create issues.");
    } finally {
      setCreatingIssues(false);
    }
  }

  const sevTone = (s: string) =>
    s === "high" ? "danger" as const : s === "medium" ? "warning" as const : "neutral" as const;

  const gradeColor = (g: string) =>
    g === "A" ? "text-[#15803d]" : g === "B" ? "text-primary" : g === "C" || g === "D" ? "text-[#b45309]" : "text-danger";

  return (
    <div className="space-y-6">
      {/* Header + scan trigger */}
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Panel title="Security scan" eyebrow={state.repo?.full_name ?? "Repository"}>
          <div className="space-y-4">
            <p className="font-mono text-sm leading-7 text-muted">
              Deep scan for SQL injection, XSS, unsafe eval, command injection, path traversal, hardcoded Firebase configs, MongoDB URIs, AWS keys, Stripe tokens, private keys, and committed <code>.env</code> files. Skips <code>.env.example</code> safely.
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                disabled={scanning}
                onClick={handleScan}
                className="rounded-full border-2 border-border bg-danger px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:shadow-none disabled:opacity-60"
              >
                {scanning ? "Scanning repository…" : result ? "Re-scan" : "Run security scan"}
              </button>

              {result?.create_issues_available && issuesCreated === null && (
                <button
                  type="button"
                  disabled={creatingIssues}
                  onClick={handleCreateIssues}
                  className="rounded-full border-2 border-border bg-accent px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-text shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-x-0.5 hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {creatingIssues
                    ? "Creating GitHub issues…"
                    : `📌 Create GitHub issues (${allFindings.filter(f => f.severity !== "low").length})`}
                </button>
              )}
            </div>

            {issuesCreated !== null && (
              <p className="rounded-2xl border-2 border-[#15803d] bg-[#bbf7d0] p-3 font-mono text-sm text-[#15803d]">
                ✓ Created {issuesCreated} GitHub issue{issuesCreated !== 1 ? "s" : ""} in {state.repo?.full_name}
              </p>
            )}
            {info && (
              <p className="rounded-2xl border-2 border-border bg-white p-4 font-mono text-sm text-muted">{info}</p>
            )}
            {error && (
              <p className="rounded-2xl border-2 border-danger bg-white p-4 font-mono text-sm text-danger">{error}</p>
            )}
          </div>
        </Panel>

        {/* Score panel */}
        {score ? (
          <Panel title="Security score" eyebrow="Results">
            <div className="space-y-4">
              <div className="flex items-center gap-6 rounded-[20px] border-2 border-border bg-bg p-4">
                <div className={`text-7xl font-bold ${gradeColor(score.grade)}`}>{score.grade}</div>
                <div>
                  <p className="text-4xl font-bold text-text">{score.score}</p>
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">/ 100</p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {(["high", "medium", "low"] as const).map((s) => (
                  <div key={s} className="rounded-[16px] border-2 border-border bg-white p-3 text-center">
                    <p className="text-2xl font-bold text-text">{score.by_severity[s]}</p>
                    <p className="font-mono text-xs uppercase tracking-[0.2em] text-muted">{s}</p>
                  </div>
                ))}
              </div>
              <p className="font-mono text-xs text-muted">{score.summary}</p>
            </div>
          </Panel>
        ) : (
          <Panel title="Results" eyebrow="Scan output">
            <p className="font-mono text-sm text-muted">Run a scan to see results here.</p>
          </Panel>
        )}
      </div>

      {/* Findings breakdown */}
      {result && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Vulnerabilities */}
          <Panel title={`Vulnerabilities (${vulnFindings.length})`} eyebrow="Code analysis">
            {vulnFindings.length === 0 ? (
              <p className="font-mono text-sm text-muted">✓ No vulnerabilities detected.</p>
            ) : (
              <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-1">
                {vulnFindings.map((f) => (
                  <FindingCard key={f.id} finding={f} sevTone={sevTone} />
                ))}
              </div>
            )}
          </Panel>

          {/* Secrets */}
          <Panel title={`Secrets & credentials (${secretFindings.length})`} eyebrow="Secret scan">
            {secretFindings.length === 0 ? (
              <p className="font-mono text-sm text-muted">✓ No secrets or credentials detected.</p>
            ) : (
              <div className="max-h-[32rem] space-y-3 overflow-y-auto pr-1">
                {secretFindings.map((f) => (
                  <FindingCard key={f.id} finding={f} sevTone={sevTone} />
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {/* By type */}
      {score && Object.keys(score.by_type).length > 0 && (
        <Panel title="Findings by type" eyebrow="Breakdown">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(score.by_type).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between rounded-[16px] border-2 border-border bg-white p-3">
                <span className="font-mono text-xs text-muted">{type.replace(/_/g, " ")}</span>
                <span className="font-mono text-sm font-bold text-text">{count}</span>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function FindingCard({
  finding: f,
  sevTone,
}: {
  finding: Finding;
  sevTone: (s: string) => "danger" | "warning" | "neutral";
}) {
  return (
    <div className="rounded-[16px] border-2 border-border bg-white p-4 space-y-2">
      <div className="flex flex-wrap gap-2">
        <StatusPill label={f.severity} tone={sevTone(f.severity)} />
        <StatusPill label={f.type.replace(/_/g, " ")} tone="neutral" />
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
  );
}
