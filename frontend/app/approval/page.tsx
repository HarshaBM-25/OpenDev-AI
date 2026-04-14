"use client";

import Link from "next/link";
import { useState } from "react";
import { ApprovalActions } from "@/components/approval-actions";
import { DiffViewer } from "@/components/diff-viewer";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { approveAction, fetchLogs } from "@/lib/api";

export default function ApprovalPage() {
  const { state, hydrateComplete, mergeState } = useAppSession();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Approval">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.sessionId) {
    return (
      <Panel title="No approval context" eyebrow="Approval">
        <div className="space-y-4 font-mono text-sm text-muted">
          <p>Run a fix or security scan before attempting approval.</p>
          <Link href="/" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go home
          </Link>
        </div>
      </Panel>
    );
  }

  async function handleApproval(approved: boolean) {
    setLoading(true);
    setError(null);
    try {
      const result = await approveAction(state.sessionId!, approved);
      const logPayload = await fetchLogs(state.sessionId!);
      mergeState({
        result,
        logs: logPayload.logs,
        pendingApproval: logPayload.pending_action,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval request failed.");
    } finally {
      setLoading(false);
    }
  }

  const result = state.result;
  const pending = state.pendingApproval;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
      {/* Gate */}
      <Panel title="Approval gate" eyebrow="Approval">
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <StatusPill label={result?.action ?? "none"} tone="neutral" />
            <StatusPill
              label={pending ? "awaiting approval" : result?.status ?? "idle"}
              tone={pending ? "warning" : result?.status === "rejected" ? "danger" : result?.status === "approved" ? "success" : "neutral"}
            />
            {result?.fork && <StatusPill label={`fork: ${result.fork.full_name}`} tone="neutral" />}
          </div>

          <p className="font-mono text-sm leading-7 text-muted">
            {result?.summary ?? "Run a fix or security scan to produce a branch candidate before approval."}
          </p>

          {pending && (
            <div className="rounded-[20px] border-2 border-accent bg-accent-soft p-4 space-y-2">
              <p className="font-mono text-xs uppercase tracking-[0.25em] text-text">Ready to push</p>
              <p className="font-mono text-sm text-muted">
                Approve to push the branch to your fork and open a cross-fork PR to the original repo owner.
                Reject to discard the branch.
              </p>
            </div>
          )}

          <ApprovalActions
            disabled={!pending}
            loading={loading}
            onApprove={() => handleApproval(true)}
            onReject={() => handleApproval(false)}
          />

          {error && (
            <p className="rounded-2xl border-2 border-danger bg-white p-4 font-mono text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      </Panel>

      {/* Status + links */}
      <div className="space-y-6">
        <Panel title="Current outcome" eyebrow="Status">
          <div className="space-y-4 font-mono text-sm text-muted">
            {result?.pull_request ? (
              <div className="rounded-[16px] border-2 border-primary bg-primary-soft p-4">
                <p className="mb-2 text-xs uppercase tracking-[0.25em] text-primary">Pull request created</p>
                <a href={result.pull_request.url} target="_blank" rel="noreferrer" className="underline text-text">
                  PR #{result.pull_request.number}: {result.pull_request.title}
                </a>
                {result.fork_full_name && (
                  <p className="mt-1 text-xs text-muted">via fork: {result.fork_full_name}</p>
                )}
              </div>
            ) : (
              <div className="rounded-[16px] border-2 border-border bg-bg p-4">
                <p className="mb-2 text-xs uppercase tracking-[0.25em]">Branch status</p>
                <p>{result?.branch_name ?? "No pending branch"}</p>
              </div>
            )}

            <div className="flex flex-wrap gap-3">
              <Link href="/logs" className="rounded-full border-2 border-border bg-white px-4 py-2 text-xs uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">
                View logs
              </Link>
              <Link href="/result" className="rounded-full border-2 border-border bg-primary px-4 py-2 text-xs uppercase tracking-[0.25em] text-white shadow-[3px_3px_0px_0px] shadow-border transition hover:-translate-y-0.5">
                View result
              </Link>
            </div>
          </div>
        </Panel>

        {result?.diff && (
          <Panel title="Diff preview" eyebrow="Git preview">
            <DiffViewer diff={result.diff} />
          </Panel>
        )}
      </div>
    </div>
  );
}
