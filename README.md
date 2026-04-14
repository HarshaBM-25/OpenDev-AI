# OpenDev AI — v4

> Autonomous GitHub agent: understands code, fixes issues via fork PR, scans for secrets & vulnerabilities, and reviews pull requests — powered by Q-learning + LLMs.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Features](#features)
3. [Project structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Local development](#local-development)
6. [Environment variables](#environment-variables)
7. [Production deployment](#production-deployment)
   - [Render (backend)](#render--backend)
   - [Vercel (frontend)](#vercel--frontend)
   - [Docker Compose (self-hosted)](#docker-compose--self-hosted)
8. [API reference](#api-reference)
9. [Troubleshooting](#troubleshooting)

---

## How it works

```
User pastes GitHub URL
        │
        ▼
  /repo  →  clone + analyze codebase
             (language, frameworks, quality score)
        │
  ┌─────┴─────┐
  │           │
Issues?      No issues?
  │           │
  ▼           ▼
/issues    /scan  →  vuln scan + secret scan
  │           │       (Firebase, MongoDB, AWS,
  │           │        .env files, private keys…)
  ▼           ▼
Fork repo   Create GitHub issues for findings
Clone fork
LLM patch
Run tests
        │
        ▼
  /approval  →  you review diff → Approve
                                      │
                                      ▼
                              push to fork
                              cross-fork PR → original owner

/pr-review  →  paste any PR URL + number
               LLM analyses diff, files, commits
               recommendation: MERGE / REQUEST_CHANGES / COMMENT
               optional: post review comment to GitHub
```

---

## Features

| Feature | Details |
|---|---|
| **Repo Analysis** | Detects language, frameworks (Next.js, Django, Flutter…), tech stack, code quality grade |
| **Fork & Fix** | Forks repo → LLM patch → tests → cross-fork PR to original owner |
| **Security Scan** | SQL injection, XSS, eval(), command injection, path traversal, 25+ secret types |
| **Secret Detection** | AWS/GCP/Azure keys, GitHub tokens, Firebase config, MongoDB URIs, Supabase keys, OpenAI keys, private keys, `.env` files (skips `.env.example`) |
| **Scan → Issues** | One click opens GitHub issues for every finding with severity labels |
| **PR Reviewer** | AI reviews any PR: bugs, security, style, logic — with merge recommendation |
| **Q-learning RL** | Learns which fix strategy works best; Q-table persists across sessions |
| **Review Gate** | Every fix requires your approval before pushing |

---

## Project structure

```
OpenDev-AI/
├── backend/
│   ├── main.py              # FastAPI app — all endpoints
│   ├── agent.py             # Orchestrates full workflow
│   ├── repo_analyzer.py     # Codebase analysis (NEW)
│   ├── pr_reviewer.py       # PR review engine (NEW)
│   ├── scanner.py           # Vulnerability scanner
│   ├── secret_scanner.py    # Secret/credential scanner
│   ├── issue_analyzer.py    # LLM issue classifier
│   ├── github_service.py    # GitHub API (fork, PR, create-issues)
│   ├── llm.py               # Gemini + Groq
│   ├── executor.py          # Patch application + test runner
│   ├── rl_agent.py          # Q-learning agent
│   ├── rules.py             # Vuln type → fix strategy mapping
│   ├── reward.py            # Reward calculator
│   ├── config.py            # Settings from .env
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── page.tsx          # Home — repo URL input
    │   ├── analyze/          # Repo analysis dashboard
    │   ├── issues/           # Issue list + fork-fix
    │   ├── scan/             # Security scan + create-issues
    │   ├── pr-review/        # PR reviewer
    │   ├── logs/             # Live execution logs
    │   ├── result/           # Action result + diff
    │   └── approval/         # Approve/reject staged PR
    ├── components/
    │   ├── app-shell.tsx     # Nav + header
    │   └── session-provider.tsx
    └── lib/
        ├── api.ts            # All API calls typed
        └── types.ts          # Full TypeScript types
```

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| Git | any | Repo cloning in agent |
| GitHub Token | classic PAT | API + fork + PR creation |
| Gemini API key | — | Primary LLM (free tier) |
| Groq API key | — | Fallback LLM (free tier) |

### GitHub token scopes

Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**

Required scopes:
- `repo` — full repo access (read, write, PR creation)
- `workflow` — push workflow files
- `read:org` — list org repos

---

## Local development

### 1. Extract and enter the project

```bash
unzip OpenDev-AI-v4.zip
cd OpenDev-AI
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Open .env and fill in:
#   GITHUB_TOKEN=ghp_...
#   GEMINI_API_KEY=...
#   GROQ_API_KEY=...

# Run
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend: **http://localhost:8000**  
Swagger: **http://localhost:8000/docs**

### 3. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure
cp .env.example .env.local
# Set: NEXT_PUBLIC_API_URL=http://localhost:8000

# Run
npm run dev
```

Frontend: **http://localhost:3000**

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | ✅ | — | GitHub classic PAT |
| `GEMINI_API_KEY` | ⚠️ one required | — | Google Gemini API key |
| `GROQ_API_KEY` | ⚠️ one required | — | Groq API key |
| `GEMINI_MODEL` | ❌ | `gemini-2.0-flash` | Gemini model ID |
| `GROQ_MODEL` | ❌ | `llama-3.3-70b-versatile` | Groq model ID |
| `FRONTEND_ORIGIN` | ❌ | `http://localhost:3000` | CORS allowed origins (comma-separated) |
| `FRONTEND_ORIGIN_REGEX` | ❌ | `https://.*\.vercel\.app` | Regex for Vercel preview URLs |
| `GIT_AUTHOR_NAME` | ❌ | `OpenDev AI` | Git commit author name |
| `GIT_AUTHOR_EMAIL` | ❌ | `opendev-ai@users.noreply.github.com` | Git commit email |
| `COMMAND_TIMEOUT_SECONDS` | ❌ | `300` | Command timeout |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | ✅ | Backend URL (e.g. `https://your-app.onrender.com`) |

---

## Production deployment

### Render — backend

1. Push the project to a GitHub repository

2. Go to [render.com](https://render.com) → **New Web Service**

3. Connect your repo and set:
   - **Root directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. Under **Environment**, add all variables from the table above

5. **Important:** Add a **Disk** (under Advanced) mounted at `/opt/render/project/src` with at least 1 GB to persist `q_table.json` across deploys

6. Deploy — Render gives you a URL like `https://opendev-ai.onrender.com`

> **Free tier note:** Render free instances sleep after 15 min of inactivity. Use the paid tier or add an uptime monitor.

---

### Vercel — frontend

1. Go to [vercel.com](https://vercel.com) → **New Project** → import your repo

2. Set **Root Directory** to `frontend`

3. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL = https://your-backend.onrender.com
   ```

4. Deploy — Vercel handles the Next.js build automatically

5. After deploy, copy your Vercel URL (e.g. `https://opendev-ai.vercel.app`) and add it to the backend's `FRONTEND_ORIGIN` variable on Render, then redeploy backend

---

### Docker Compose — self-hosted

Create `docker-compose.yml` in the project root:

```yaml
version: "3.9"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GROQ_API_KEY: ${GROQ_API_KEY}
      FRONTEND_ORIGIN: http://localhost:3000
    volumes:
      - rl_data:/app

  frontend:
    build:
      context: ./frontend
      args:
        NEXT_PUBLIC_API_URL: http://backend:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  rl_data:
```

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/public ./public
RUN npm ci --omit=dev
CMD ["npm", "start"]
```

Start:

```bash
GITHUB_TOKEN=xxx GEMINI_API_KEY=xxx docker compose up --build
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/repo` | Load repo + analyze codebase |
| `GET` | `/issues` | List open GitHub issues + repo analysis |
| `POST` | `/fork-fix` | Fork → LLM fix → staged PR |
| `POST` | `/scan` | Deep security scan |
| `POST` | `/create-issues` | Open GitHub issues for findings |
| `POST` | `/pr-review` | AI PR review (+ optional post to GitHub) |
| `POST` | `/approve` | Approve or reject staged PR |
| `GET` | `/logs` | Live execution logs (poll every 3s) |
| `GET` | `/security-score` | Cached score from last scan |
| `GET` | `/rl-stats` | Q-learning stats + learned policy |
| `POST` | `/pr-feedback` | Feed PR outcome to RL agent |
| `POST` | `/terminate` | End session |
| `GET` | `/health` | Health + config check |
| `GET` | `/docs` | Swagger UI |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `NEXT_PUBLIC_API_URL is still localhost` | Set the env var on Vercel and redeploy |
| `GitHub client is not configured` | Check `GITHUB_TOKEN` in backend env |
| `No LLM provider configured` | Set `GEMINI_API_KEY` or `GROQ_API_KEY` |
| Fork PR returns 422 | Fork may already be ahead on the same branch; delete the fork branch manually |
| `No changes were produced` | LLM returned empty `changes` — retry or switch model |
| CORS error in browser | Add your Vercel URL to `FRONTEND_ORIGIN` in backend env |
| Q-table not persisting on Render | Add a Disk at the build path |
| Render backend is slow to start | It sleeps on free tier; upgrade or add uptime pinger |
| `.env.example` flagged as secret | This is a bug — update to latest `secret_scanner.py` which explicitly skips safe template files |

---

*OpenDev AI — Autonomous GitHub maintenance powered by LLMs and Q-learning.*
