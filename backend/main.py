"""
main.py — OpenDev AI v4 FastAPI application

Endpoint map:
  POST /repo              load repo + analyze codebase
  GET  /issues            list issues + repo analysis
  POST /fork-fix          fork → fix issue → PR to original owner
  POST /fix               alias for fork-fix
  POST /scan              deep security scan (vulns + secrets)
  POST /create-issues     open GitHub issues for findings
  POST /pr-review         analyze a PR + optional post review
  POST /approve           approve/reject staged PR
  GET  /logs              execution logs
  GET  /security-score    cached score from last scan
  GET  /rl-stats          Q-learning stats
  POST /pr-feedback       feed PR merge result to RL
  POST /terminate         end session
  GET  /health            health check
"""
from __future__ import annotations
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agent import AgentError, OpenDevAgent
from config import settings
from reward import calculate_reward

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="OpenDev AI", version="4.0.0",
    description="Autonomous GitHub agent: scan, fix, PR, review — powered by Q-learning + LLMs")

# Always allow localhost origins on any port for local development.
local_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\\d+)?"
combined_origin_regex = f"({settings.frontend_origin_regex})|({local_origin_regex})"

app.add_middleware(CORSMiddleware,
    allow_origins=[*settings.frontend_origins, "http://127.0.0.1:3000", "http://localhost:3000"],
    allow_origin_regex=combined_origin_regex,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

agent = OpenDevAgent(settings)

class RepoRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)

class FixRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    issue_number: int = Field(..., ge=1)

class ScanRequest(BaseModel):
    session_id: str = Field(..., min_length=1)

class ApprovalRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    approved: bool = True

class SessionRequest(BaseModel):
    session_id: str = Field(..., min_length=1)

class CreateIssuesRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    finding_ids: list[int] | None = None

class PRReviewRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    repo_url: str = Field(..., min_length=1)
    pr_number: int = Field(..., ge=1)
    post_comment: bool = False

class PRFeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    pr_number: int = Field(..., ge=1)
    rl_state: dict = Field(..., example={"type":"sql_injection","severity":"high","source":"code","language":"python"})
    rl_action: str = Field(..., example="prepared_statement")
    pr_merged: bool = False
    issue_closed: bool = False
    tests_passed: bool = False
    build_failed: bool = False

@app.get("/")
def root() -> dict:
    return {"name":"OpenDev AI","version":"4.0.0","status":"ok","docs":"/docs",
            "endpoints":["POST /repo","GET /issues","POST /fork-fix","POST /scan",
                         "POST /create-issues","POST /pr-review","POST /approve",
                         "GET /logs","GET /security-score","GET /rl-stats","POST /pr-feedback"]}

@app.get("/health")
def health() -> dict:
    return {"status":"ok","github":bool(settings.github_token),
            "gemini":bool(settings.gemini_api_key),"groq":bool(settings.groq_api_key),
            "llm_available":settings.has_llm_provider}

@app.post("/repo", summary="Load repository, analyze codebase, fetch issues")
def load_repo(payload: RepoRequest) -> dict:
    try: return agent.create_repo_session(payload.repo_url)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.get("/issues", summary="List open issues + repo analysis")
def get_issues(session_id: str = Query(..., min_length=1)) -> dict:
    try: return agent.get_issues(session_id)
    except AgentError as exc: raise HTTPException(404, detail=str(exc)) from exc

@app.post("/fork-fix", summary="Fork repo → fix issue → PR to original owner")
def fork_fix(payload: FixRequest) -> dict:
    try: return agent.fork_and_fix_issue(payload.session_id, payload.issue_number)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/fix", summary="Fix issue (alias for /fork-fix)")
def fix_issue(payload: FixRequest) -> dict:
    try: return agent.fix_issue(payload.session_id, payload.issue_number)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/scan", summary="Deep security scan: vulnerabilities + secrets")
def run_scan(payload: ScanRequest) -> dict:
    try: return agent.deep_security_scan(payload.session_id)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/create-issues", summary="Open GitHub issues for detected findings")
def create_issues(payload: CreateIssuesRequest) -> dict:
    try: return agent.create_issues_from_findings(payload.session_id, payload.finding_ids)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/pr-review", summary="AI-powered PR review with merge/reject recommendation")
def pr_review(payload: PRReviewRequest) -> dict:
    try: return agent.review_pull_request(payload.session_id, payload.repo_url, payload.pr_number, payload.post_comment)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/approve", summary="Approve or reject staged PR")
def approve(payload: ApprovalRequest) -> dict:
    try: return agent.approve(payload.session_id, payload.approved)
    except AgentError as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.get("/logs", summary="Execution logs (poll every 3s)")
def get_logs(session_id: str = Query(..., min_length=1)) -> dict:
    try: return agent.get_logs(session_id)
    except AgentError as exc: raise HTTPException(404, detail=str(exc)) from exc

@app.get("/security-score")
def security_score(session_id: str = Query(..., min_length=1)) -> dict:
    try: return agent.get_security_score(session_id)
    except AgentError as exc: raise HTTPException(404, detail=str(exc)) from exc

@app.get("/rl-stats")
def rl_stats() -> dict:
    return agent.get_rl_stats()

@app.post("/pr-feedback", summary="Feed PR merge outcome back to RL agent")
def pr_feedback(payload: PRFeedbackRequest) -> dict:
    try:
        exec_result = {"tests_passed":payload.tests_passed, "tests_failed": not payload.tests_passed and not payload.build_failed,
                       "build_failed":payload.build_failed, "issue_fixed":payload.issue_closed, "secret_removed":False, "no_change":False}
        pr_status = {"merged":payload.pr_merged, "state":"closed" if payload.issue_closed else "open", "issue_closed":payload.issue_closed}
        rv, ri = calculate_reward(exec_result, pr_status)
        agent.rl.update(payload.rl_state, payload.rl_action, rv)
        return {"status":"ok","pr_number":payload.pr_number,"reward":rv,"reward_info":ri,"rl_stats":agent.rl.get_stats()}
    except Exception as exc: raise HTTPException(400, detail=str(exc)) from exc

@app.post("/terminate")
def terminate(payload: SessionRequest) -> dict:
    try: return agent.terminate_session(payload.session_id)
    except AgentError as exc: raise HTTPException(404, detail=str(exc)) from exc
