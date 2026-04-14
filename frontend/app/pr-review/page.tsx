"use client";

import Link from "next/link";
import { useState } from "react";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";
import { reviewPR, PRReviewResponse } from "@/lib/api";

export default function PRReviewPage() {
  const { state, hydrateComplete } = useAppSession();
  const [repoUrl, setRepoUrl] = useState(state.repoUrl || "");
  const [prNumber, setPrNumber] = useState("");
  const [postComment, setPostComment] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewData, setReviewData] = useState<PRReviewResponse | null>(null);

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="PR Review">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  async function handleReview() {
    if (!state.sessionId) { setError("Load a repository first."); return; }
    const num = parseInt(prNumber, 10);
    if (!num || num < 1) { setError("Enter a valid PR number."); return; }
    setLoading(true);
    setError(null);
    setReviewData(null);
    try {
      const data = await reviewPR(state.sessionId, repoUrl, num, postComment);
      setReviewData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review failed.");
    } finally {
      setLoading(false);
    }
  }

  const review = reviewData?.review;
  const pr = reviewData?.pr_details;

  const recTone = (r: string) =>
    r === "MERGE" ? "success" as const : r === "REQUEST_CHANGES" ? "danger" as const : "warning" as const;

  const recLabel = { MERGE: "✓ Merge", REQUEST_CHANGES: "✗ Request changes", COMMENT: "◎ Comment only" };

  const sevTone = (s: string) =>
    s === "critical" || s === "major" ? "danger" as const : s === "minor" ? "warning" as const : "neutral" as const;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        {/* Input panel */}
        <Panel title="Review a pull request" eyebrow="PR Review">
          <div className="space-y-5">
            <p className="font-mono text-sm leading-7 text-muted">
              Enter any GitHub repository URL and PR number. The AI will analyse the diff, changed files, commits, and existing reviews — then recommend MERGE, REQUEST_CHANGES, or COMMENT with detailed reasoning.
            </p>

            <label className="block space-y-2">
              <span className="font-mono text-xs uppercase tracking-[0.25em] text-muted">Repository URL</span>
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="w-full rounded-2xl border-2 border-border bg-white px-4 py-3 font-mono text-sm text-text outline-none transition focus:border-primary"
              />
            </label>

            <label className="block space-y-2">
              <span className="font-mono text-xs uppercase tracking-[0.25em] text-muted">PR number</span>
              <input
                type="number"
                min="1"
                value={prNumber}
                onChange={(e) => setPrNumber(e.target.value)}
                placeholder="123"
                className="w-full rounded-2xl border-2 border-border bg-white px-4 py-3 font-mono text-sm text-text outline-none transition focus:border-primary"
              />
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={postComment}
                onChange={(e) => setPostComment(e.target.checked)}
                className="h-4 w-4 accent-[#3b82f6]"
              />
              <span className="font-mono text-sm text-muted">Post review comment to GitHub</span>
            </label>

            <button
              type="button"
              disabled={loading || !repoUrl || !prNumber}
              onClick={handleReview}
              className="rounded-full border-2 border-border bg-primary px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:shadow-none disabled:opacity-60"
            >
              {loading ? "Analysing PR…" : "Analyse pull request"}
            </button>

            {error && (
              <p className="rounded-2xl border-2 border-danger bg-white p-4 font-mono text-sm text-danger">{error}</p>
            )}
          </div>
        </Panel>

        {/* Recommendation */}
        {review ? (
          <Panel title="Recommendation" eyebrow="AI verdict">
            <div className="space-y-4">
              <div className="rounded-[20px] border-2 border-border bg-bg p-5 text-center space-y-2">
                <StatusPill
                  label={recLabel[review.recommendation] || review.recommendation}
                  tone={recTone(review.recommendation)}
                />
                <p className="font-mono text-xs text-muted">
                  {(review.confidence * 100).toFixed(0)}% confidence · {review.overall_quality} quality
                </p>
              </div>
              <p className="font-mono text-sm leading-7 text-muted">{review.summary}</p>
              {reviewData?.post_result?.posted && (
                <p className="font-mono text-xs text-[#15803d]">✓ Review posted to GitHub</p>
              )}
              {review.positives && review.positives.length > 0 && (
                <div className="space-y-1">
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">Positives</p>
                  {review.positives.map((p, i) => (
                    <p key={i} className="font-mono text-xs text-[#15803d]">✓ {p}</p>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        ) : (
          <Panel title="Results" eyebrow="AI verdict">
            <p className="font-mono text-sm text-muted">Submit a PR URL and number to see the review.</p>
          </Panel>
        )}
      </div>

      {/* PR details + issues */}
      {pr && review && (
        <>
          {/* PR info */}
          <Panel title={`PR #${pr.number}: ${pr.title}`} eyebrow={`by ${pr.author}`}
            actions={<a href={pr.url} target="_blank" rel="noreferrer" className="rounded-full border-2 border-border bg-white px-3 py-1 font-mono text-xs uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5">View ↗</a>}
          >
            <div className="space-y-4 font-mono text-sm">
              <div className="flex flex-wrap gap-2">
                <StatusPill label={pr.merged ? "merged" : pr.state} tone={pr.merged ? "success" : pr.state === "open" ? "primary" : "neutral"} />
                <StatusPill label={`+${pr.additions} -${pr.deletions}`} tone="neutral" />
                <StatusPill label={`${pr.changed_files.length} files`} tone="neutral" />
                <StatusPill label={`${pr.head_branch} → ${pr.base_branch}`} tone="neutral" />
              </div>
              {pr.commits.length > 0 && (
                <div>
                  <p className="mb-2 text-xs uppercase tracking-[0.25em] text-muted">Commits</p>
                  {pr.commits.slice(0, 5).map((c, i) => (
                    <p key={i} className="text-muted">· {c}</p>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          {/* Issues found */}
          {review.issues && review.issues.length > 0 && (
            <Panel title={`Issues found (${review.issues.length})`} eyebrow="Code review">
              <div className="space-y-4">
                {review.issues.map((issue, i) => (
                  <div key={i} className="rounded-[20px] border-2 border-border bg-white p-4 space-y-3">
                    <div className="flex flex-wrap gap-2">
                      <StatusPill label={issue.severity} tone={sevTone(issue.severity)} />
                      <StatusPill label={issue.category} tone="neutral" />
                      {issue.file && (
                        <span className="font-mono text-xs text-muted">
                          {issue.file}{issue.line ? `:${issue.line}` : ""}
                        </span>
                      )}
                    </div>
                    <p className="font-mono text-sm text-text">{issue.description}</p>
                    {issue.suggestion && (
                      <div className="rounded-[14px] border-2 border-primary bg-primary-soft p-3">
                        <p className="font-mono text-xs uppercase tracking-[0.2em] text-primary mb-1">Suggestion</p>
                        <p className="font-mono text-sm text-text">{issue.suggestion}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Changed files */}
          <Panel title={`Changed files (${pr.changed_files.length})`} eyebrow="Diff summary">
            <div className="space-y-2">
              {pr.changed_files.map((f) => (
                <div key={f.filename} className="flex items-center justify-between rounded-[14px] border-2 border-border bg-white p-3">
                  <span className="font-mono text-xs text-text truncate flex-1 mr-4">{f.filename}</span>
                  <div className="flex gap-2 shrink-0">
                    <StatusPill label={`+${f.additions}`} tone="success" />
                    <StatusPill label={`-${f.deletions}`} tone="danger" />
                    <StatusPill label={f.status} tone="neutral" />
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          {/* Review comment */}
          {review.review_comment && (
            <Panel title="Generated review comment" eyebrow="GitHub comment">
              <pre className="max-h-64 overflow-auto border-2 border-border bg-bg p-5 font-mono text-sm leading-7 text-text whitespace-pre-wrap">
                {review.review_comment}
              </pre>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
