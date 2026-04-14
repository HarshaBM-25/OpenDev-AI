export type RepoDetails = {
  name: string;
  full_name: string;
  description: string | null;
  default_branch: string;
  clone_url: string;
  html_url: string;
  language: string | null;
  stars: number;
  forks: number;
  open_issues_count: number;
  is_fork?: boolean;
  private?: boolean;
};

export type RepoAnalysis = {
  primary_language: string;
  languages: Record<string, number>;
  frameworks: string[];
  project_type: string;
  tech_stack: string[];
  dependencies: string[];
  has_tests: boolean;
  has_docker: boolean;
  has_ci: boolean;
  file_count: number;
  directory_count: number;
  key_files: string[];
  structure_summary: string;
  code_quality: { score: number; grade: string; signals: string[] };
  readme_excerpt: string;
};

export type Issue = {
  number: number;
  title: string;
  body: string;
  url: string;
  labels: string[];
  state: string;
  complexity: "simple" | "medium" | "complex";
  created_at?: string;
};

export type LogEntry = {
  timestamp: string;
  level: string;
  step: string;
  message: string;
};

export type TestResult = {
  command: string;
  status: "passed" | "failed" | "skipped";
  stdout: string;
  stderr: string;
  duration?: number;
};

export type Finding = {
  id: number;
  source?: "code" | "issue";
  type: string;
  severity: "high" | "medium" | "low";
  description?: string;
  file?: string;
  line?: number | null;
  preview?: string;
  fixable?: boolean;
  fix_types?: string[];
  language?: string;
  _chosen_action?: string;
  _confidence?: number;
};

export type SecurityScore = {
  score: number;
  grade: "A" | "B" | "C" | "D" | "F";
  total_findings: number;
  by_severity: { high: number; medium: number; low: number };
  by_type: Record<string, number>;
  summary: string;
};

export type PullRequestInfo = {
  number: number;
  url: string;
  title: string;
  state: string;
};

export type ForkInfo = {
  full_name: string;
  html_url: string;
  owner: string;
  already_existed: boolean;
};

export type PRReviewIssue = {
  severity: "critical" | "major" | "minor" | "suggestion";
  file?: string;
  line?: number | null;
  category: string;
  description: string;
  suggestion: string;
};

export type PRReview = {
  summary: string;
  recommendation: "MERGE" | "REQUEST_CHANGES" | "COMMENT";
  confidence: number;
  overall_quality: "excellent" | "good" | "fair" | "poor";
  issues: PRReviewIssue[];
  positives: string[];
  review_comment: string;
};

export type PRDetails = {
  number: number;
  title: string;
  body: string;
  author: string;
  state: string;
  merged: boolean;
  mergeable: boolean | null;
  base_branch: string;
  head_branch: string;
  additions: number;
  deletions: number;
  changed_files: Array<{
    filename: string;
    status: string;
    additions: number;
    deletions: number;
    patch: string;
  }>;
  commits: string[];
  url: string;
};

export type ActionResult = {
  action: "fork_fix" | "fix" | "security_scan" | "autonomous" | "scan";
  status: string;
  summary: string;
  diff: string;
  issue_number?: number;
  touched_files?: string[];
  test_results?: TestResult[];
  findings?: Finding[];
  vuln_findings?: Finding[];
  secret_findings?: Finding[];
  all_findings?: Finding[];
  branch_name?: string;
  pull_request?: PullRequestInfo;
  fork?: ForkInfo;
  security_score?: SecurityScore;
  create_issues_available?: boolean;
  fork_full_name?: string;
};

export type AppState = {
  sessionId: string | null;
  repoUrl: string;
  repo: RepoDetails | null;
  repoAnalysis: RepoAnalysis | null;
  issues: Issue[];
  selectedIssue: Issue | null;
  logs: LogEntry[];
  result: ActionResult | null;
  pendingApproval: boolean;
};

export const initialAppState: AppState = {
  sessionId: null,
  repoUrl: "",
  repo: null,
  repoAnalysis: null,
  issues: [],
  selectedIssue: null,
  logs: [],
  result: null,
  pendingApproval: false,
};
