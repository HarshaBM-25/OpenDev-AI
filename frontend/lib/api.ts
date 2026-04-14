import { ActionResult, Issue, LogEntry, RepoDetails, RepoAnalysis } from "@/lib/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (
    typeof window !== "undefined" &&
    !["localhost", "127.0.0.1"].includes(window.location.hostname) &&
    API_URL.includes("localhost")
  ) {
    throw new Error("NEXT_PUBLIC_API_URL is still pointing to localhost. Update it to your deployed backend URL and redeploy.");
  }
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new Error(`Unable to reach backend at ${API_URL}. Check NEXT_PUBLIC_API_URL and CORS settings.`);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json();
}

// ── Response types ────────────────────────────────────────────────────────────

export type RepoResponse = {
  session_id: string;
  repo: RepoDetails;
  issues: Issue[];
  repo_analysis: RepoAnalysis;
  logs: LogEntry[];
  has_issues: boolean;
};

export type IssuesResponse = {
  session_id: string;
  repo: RepoDetails;
  issues: Issue[];
  repo_analysis: RepoAnalysis | null;
};

export type LogsResponse = {
  session_id: string;
  logs: LogEntry[];
  pending_action: boolean;
};

export type CreateIssuesResponse = {
  status: string;
  created: Array<{
    finding: { type: string; severity: string; file?: string };
    issue: { number: number; title: string; url: string; state: string };
  }>;
  errors: string[];
  issues_created: number;
  total_findings: number;
};

export type PRReviewResponse = {
  pr_details: {
    number: number; title: string; body: string; author: string;
    state: string; merged: boolean; mergeable: boolean | null;
    base_branch: string; head_branch: string;
    additions: number; deletions: number;
    changed_files: Array<{ filename: string; status: string; additions: number; deletions: number; patch: string }>;
    commits: string[]; url: string;
  };
  review: {
    summary: string;
    recommendation: "MERGE" | "REQUEST_CHANGES" | "COMMENT";
    confidence: number;
    overall_quality: "excellent" | "good" | "fair" | "poor";
    issues: Array<{
      severity: "critical" | "major" | "minor" | "suggestion";
      file?: string; line?: number | null;
      category: string; description: string; suggestion: string;
    }>;
    positives: string[];
    review_comment: string;
  };
  post_result: { posted?: boolean; error?: string };
};

// ── API functions ─────────────────────────────────────────────────────────────

export const createRepoSession = (repoUrl: string) =>
  request<RepoResponse>("/repo", { method: "POST", body: JSON.stringify({ repo_url: repoUrl }) });

export const fetchIssues = (sessionId: string) =>
  request<IssuesResponse>(`/issues?session_id=${encodeURIComponent(sessionId)}`);

export const forkFixIssue = (sessionId: string, issueNumber: number) =>
  request<ActionResult>("/fork-fix", { method: "POST", body: JSON.stringify({ session_id: sessionId, issue_number: issueNumber }) });

export const fixIssue = (sessionId: string, issueNumber: number) =>
  request<ActionResult>("/fix", { method: "POST", body: JSON.stringify({ session_id: sessionId, issue_number: issueNumber }) });

export const runSecurityScan = (sessionId: string) =>
  request<ActionResult>("/scan", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });

export const createIssuesFromFindings = (sessionId: string, findingIds?: number[]) =>
  request<CreateIssuesResponse>("/create-issues", { method: "POST", body: JSON.stringify({ session_id: sessionId, finding_ids: findingIds ?? null }) });

export const reviewPR = (sessionId: string, repoUrl: string, prNumber: number, postComment: boolean = false) =>
  request<PRReviewResponse>("/pr-review", { method: "POST", body: JSON.stringify({ session_id: sessionId, repo_url: repoUrl, pr_number: prNumber, post_comment: postComment }) });

export const approveAction = (sessionId: string, approved: boolean) =>
  request<ActionResult>("/approve", { method: "POST", body: JSON.stringify({ session_id: sessionId, approved }) });

export const fetchLogs = (sessionId: string) =>
  request<LogsResponse>(`/logs?session_id=${encodeURIComponent(sessionId)}`);

export const terminateSession = (sessionId: string) =>
  request<{ session_id: string; status: string }>("/terminate", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
