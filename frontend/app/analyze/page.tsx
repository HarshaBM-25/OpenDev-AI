"use client";

import Link from "next/link";
import { Panel } from "@/components/panel";
import { StatusPill } from "@/components/status-pill";
import { useAppSession } from "@/components/session-provider";

export default function AnalyzePage() {
  const { state, hydrateComplete } = useAppSession();

  if (!hydrateComplete) {
    return (
      <Panel title="Loading session" eyebrow="Repository">
        <p className="font-mono text-sm text-muted">Restoring session…</p>
      </Panel>
    );
  }

  if (!state.sessionId || !state.repo) {
    return (
      <Panel title="No repository loaded" eyebrow="Repository">
        <div className="space-y-4 font-mono text-sm text-muted">
          <p>Enter a GitHub URL on the home page first.</p>
          <Link href="/" className="inline-flex rounded-full border-2 border-border bg-primary px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border">
            Go home
          </Link>
        </div>
      </Panel>
    );
  }

  const repo = state.repo;
  const a = state.repoAnalysis;
  const hasIssues = state.issues.length > 0;

  return (
    <div className="space-y-6">
      {/* Repo header */}
      <div className="rounded-[32px] border-2 border-border bg-white/80 p-6 shadow-[8px_8px_0px_0px] shadow-border">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="space-y-1">
              <p className="font-mono text-xs uppercase tracking-[0.35em] text-muted">Loaded repository</p>
              <h2 className="text-3xl font-bold tracking-tight">{repo.full_name}</h2>
            </div>
            <p className="max-w-2xl text-base leading-7 text-muted">{repo.description ?? "No description provided."}</p>
            <div className="flex flex-wrap gap-2">
              {repo.language && <StatusPill label={repo.language} tone="primary" />}
              <StatusPill label={`⭐ ${repo.stars}`} tone="neutral" />
              <StatusPill label={`🍴 ${repo.forks}`} tone="neutral" />
              <StatusPill label={`${repo.default_branch} branch`} tone="neutral" />
              <StatusPill
                label={`${repo.open_issues_count} open issues`}
                tone={repo.open_issues_count > 0 ? "warning" : "success"}
              />
            </div>
          </div>
          <a
            href={repo.html_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 rounded-full border-2 border-border bg-white px-4 py-2 font-mono text-sm uppercase tracking-[0.25em] text-text transition hover:-translate-y-0.5"
          >
            View on GitHub ↗
          </a>
        </div>
      </div>

      {/* Analysis panels */}
      {a && (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Project identity */}
          <Panel title="Project identity" eyebrow="Analysis">
            <div className="space-y-3 font-mono text-sm">
              {[
                { label: "Project type", value: a.project_type },
                { label: "Primary language", value: a.primary_language },
                { label: "Total files", value: a.file_count.toLocaleString() },
                { label: "Directories", value: a.directory_count.toLocaleString() },
                { label: "Test suite", value: a.has_tests ? "✓ Present" : "✗ Missing" },
                { label: "Docker", value: a.has_docker ? "✓ Configured" : "–" },
                { label: "CI / CD", value: a.has_ci ? "✓ Configured" : "–" },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center justify-between gap-4 border-b border-border/30 pb-2">
                  <span className="text-muted">{label}</span>
                  <span className={`font-medium ${
                    value.startsWith("✓") ? "text-[#15803d]" : value.startsWith("✗") ? "text-danger" : "text-text"
                  }`}>{value}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* Tech stack */}
          <Panel title="Tech stack" eyebrow="Frameworks & tools">
            <div className="space-y-4">
              {a.frameworks.length > 0 && (
                <div className="space-y-2">
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">Frameworks</p>
                  <div className="flex flex-wrap gap-2">
                    {a.frameworks.map((f) => <StatusPill key={f} label={f} tone="primary" />)}
                  </div>
                </div>
              )}
              {a.tech_stack.length > 0 && (
                <div className="space-y-2">
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">Technologies</p>
                  <div className="flex flex-wrap gap-2">
                    {a.tech_stack.slice(0, 10).map((t) => <StatusPill key={t} label={t} tone="neutral" />)}
                  </div>
                </div>
              )}
              {Object.keys(a.languages).length > 0 && (
                <div className="space-y-2">
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">Languages</p>
                  {Object.entries(a.languages).slice(0, 5).map(([lang, count]) => (
                    <div key={lang} className="flex items-center gap-3">
                      <div className="flex-1 h-2 rounded-full border border-border bg-bg overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${Math.min(100, (count / a.file_count) * 100)}%` }}
                        />
                      </div>
                      <span className="w-28 font-mono text-xs text-muted">{lang}</span>
                      <span className="font-mono text-xs font-bold text-text">{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          {/* Code quality */}
          <Panel title="Code quality" eyebrow="Health score">
            <div className="space-y-4">
              <div className="flex items-center gap-4 rounded-[20px] border-2 border-border bg-bg p-4">
                <div className={`text-6xl font-bold tracking-tight ${
                  a.code_quality.grade === "A" ? "text-[#15803d]" :
                  a.code_quality.grade === "B" ? "text-primary" :
                  a.code_quality.grade === "C" ? "text-[#b45309]" : "text-danger"
                }`}>
                  {a.code_quality.grade}
                </div>
                <div>
                  <p className="text-3xl font-bold text-text">{a.code_quality.score}</p>
                  <p className="font-mono text-xs uppercase tracking-[0.25em] text-muted">/ 100</p>
                </div>
              </div>
              <div className="space-y-2">
                {a.code_quality.signals.map((s, i) => (
                  <p key={i} className={`font-mono text-xs ${s.startsWith("✓") ? "text-[#15803d]" : "text-danger"}`}>{s}</p>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      )}

      {/* Key files */}
      {a?.key_files && a.key_files.length > 0 && (
        <Panel title="Key files detected" eyebrow="Structure">
          <div className="flex flex-wrap gap-2">
            {a.key_files.map((f) => (
              <span key={f} className="rounded-full border-2 border-border bg-white px-3 py-1 font-mono text-xs text-text">
                {f}
              </span>
            ))}
          </div>
        </Panel>
      )}

      {/* README */}
      {a?.readme_excerpt && (
        <Panel title="README preview" eyebrow="Documentation">
          <pre className="max-h-48 overflow-auto font-mono text-sm leading-7 text-muted whitespace-pre-wrap">
            {a.readme_excerpt}
          </pre>
        </Panel>
      )}

      {/* CTA */}
      <div className="rounded-[28px] border-2 border-border bg-surface p-6 shadow-[6px_6px_0px_0px] shadow-border">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <h3 className="text-xl font-semibold">
              {hasIssues ? `${state.issues.length} open issue${state.issues.length !== 1 ? "s" : ""} found` : "No open issues"}
            </h3>
            <p className="font-mono text-sm text-muted">
              {hasIssues
                ? "Select an issue to fork-fix, or run a security scan to find vulnerabilities."
                : "No issues found. Run a security scan to detect secrets and vulnerabilities."}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {hasIssues && (
              <Link href="/issues" className="rounded-full border-2 border-border bg-primary px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
                Fix Issues →
              </Link>
            )}
            <Link href="/scan" className="rounded-full border-2 border-border bg-danger px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-white shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
              Security Scan
            </Link>
            <Link href="/pr-review" className="rounded-full border-2 border-border bg-white px-5 py-3 font-mono text-sm uppercase tracking-[0.25em] text-text shadow-[4px_4px_0px_0px] shadow-border transition hover:-translate-y-0.5">
              Review a PR
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
