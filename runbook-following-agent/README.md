# Runbook Following Agent

An AI-powered **Runbook Following Agent** that reads Markdown runbooks, parses numbered instructions, safely executes approved shell commands, requests confirmation before risky operations, and generates execution logs and reports.

Built for hackathon MVP — production-quality architecture with security-first command execution.

![Tech Stack](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react)
![Tech Stack](https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi)
![Tech Stack](https://img.shields.io/badge/Tailwind-3.4-38B2AC?style=flat-square&logo=tailwindcss)

---

## Features

| Feature | Description |
|---------|-------------|
| **Upload Runbook** | Upload `.md` files with numbered steps |
| **Parse Markdown** | Extract steps into structured JSON |
| **Allowlist** | Auto-execute safe commands (`pwd`, `ls`, `mkdir`, etc.) |
| **Risky Detection** | Block `rm`, `sudo`, `shutdown`, etc. until confirmed |
| **Safe Execution** | Subprocess with injection protection |
| **Logging** | Timestamped logs stored in `backend/logs/` |
| **Reports** | Summary with success/fail/blocked counts + PDF export |
| **Live Terminal** | Real-time SSE streaming during execution |
| **Pause / Resume** | Control long-running runbooks |
| **Retry** | Re-run failed steps |

---

## Project Structure

```
runbook-following-agent/
├── frontend/                 # React + Vite + Tailwind
│   ├── src/
│   │   ├── App.jsx           # Main dashboard UI
│   │   ├── api/client.js     # Axios API client
│   │   └── ...
│   └── package.json
├── backend/
│   ├── main.py               # FastAPI routes
│   ├── parser.py             # Markdown step parser
│   ├── executor.py           # Subprocess execution
│   ├── allowlist.py          # Command validation
│   ├── logger.py             # JSON log storage
│   ├── report.py             # Report + PDF generation
│   ├── models.py             # Pydantic models
│   ├── logs/                 # Execution logs
│   └── runbooks/             # Uploaded runbooks
├── sample-maintenance.md     # Example runbook
├── requirements.txt
└── README.md
```

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **npm**

### Backend

```bash
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload
```

API available at: **http://127.0.0.1:8000**  
Interactive docs: **http://127.0.0.1:8000/docs**

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at: **http://127.0.0.1:5173**

> The Vite dev server proxies `/api/*` requests to the backend on port 8000.

---

## Sample Runbook

Use the included `sample-maintenance.md`:

```markdown
# Server Maintenance

1. pwd
2. ls
3. mkdir backup
4. echo "Backup Created"
5. rm old.log
6. whoami
7. date
```

Steps 1–4 and 6–7 execute automatically. Step 5 (`rm`) triggers a **risky command confirmation** dialog.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload a `.md` runbook |
| `POST` | `/parse` | Parse runbook into steps |
| `POST` | `/execute` | Start runbook execution |
| `POST` | `/execute/confirm` | Approve/reject risky step |
| `POST` | `/execute/pause` | Pause execution |
| `POST` | `/execute/resume` | Resume execution |
| `POST` | `/execute/retry` | Retry a failed step |
| `GET` | `/execute/state/{id}` | Poll execution state |
| `GET` | `/execute/stream/{id}` | SSE live event stream |
| `GET` | `/logs` | Fetch execution logs |
| `GET` | `/report` | Generate JSON report |
| `GET` | `/report/pdf` | Download PDF report |

---

## Authentication setup

Authentication is available as an opt-in backend security layer. Configure these
environment variables on the backend service (Render) before enabling it:

- `RUNBOOK_ADMIN_USERNAME`: the administrator's sign-in name.
- `RUNBOOK_ADMIN_PASSWORD`: a long, unique password.
- `RUNBOOK_AUTH_SECRET`: a cryptographically random secret of at least 32 characters.

Example for generating a signing secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the three values in the backend service's environment settings; never commit
them to Git or put them in a `VITE_*` frontend variable. When configured, the
API requires a signed Bearer token for operational endpoints. Tokens expire
after eight hours, the frontend keeps the token only in session storage, and
the Settings screen has a sign-out action. The login endpoints are
`GET /auth/config` and `POST /auth/login`.

**Important:** if these variables are absent or the signing secret is shorter
than 32 characters, authentication remains disabled for backwards-compatible
local development. The dashboard indicates this in Settings. Set the variables
on the hosted backend to activate the login gate.

This milestone provides a single configured administrator identity. It does
not yet provide self-service registration, multiple user accounts, or durable
per-user runbook/session ownership; those require a persistent identity store
and data-isolation migration before the app should be exposed as a multi-tenant
service.

## Security

- **Allowlist-only auto-execution** — only predefined safe commands run without confirmation
- **Risky command gate** — destructive commands require explicit user approval
- **Shell injection protection** — metacharacters (`;`, `|`, `&`, `` ` ``, `$()`) are rejected
- **Runbook-bound execution** — only parsed runbook commands are executed, never arbitrary input
- **No shell=True** — commands run via subprocess argument lists

### Allowed Commands (auto-run)

`pwd`, `ls`, `mkdir`, `cp`, `mv`, `cat`, `echo`, `whoami`, `date`

### Risky Commands (require confirmation)

`rm`, `shutdown`, `reboot`, `kill`, `sudo`, `chmod`, `systemctl stop`, `format`

---

## Fixes Applied (this build)

- **Risky-command false positives** — `allowlist.py` matched risky patterns
  (`rm`, `sudo`, `kill`, …) as raw substrings, so safe commands like
  `cat term.txt` or `echo confirm` were wrongly blocked as "risky". Now
  matched on word boundaries.
- **Duplicate/stale step results** — retrying a step or resolving a risky
  confirmation appended a second result for the same step instead of
  replacing it, so `/execute/state` and the dashboard could show a stale
  status after a retry. Results are now upserted by step number.
- **Inflated report counts** — a step that went through a confirmation
  (`waiting_confirmation` → `skipped`/`success`) was logged twice, so
  `/report` double-counted it and `total_steps` didn't match the runbook's
  real step count. The report now keeps only the latest log entry per step.
- **Event loop blocking** — `execute_command()` (subprocess, up to a
  120s timeout) and all log writes ran directly on the async event loop,
  which would freeze every other request/session while one command was
  running. Both now run in a worker thread via `asyncio.to_thread`.
- **Windows command mapping** — `cp`/`mv` weren't mapped to Windows
  equivalents, and mapped commands other than `ls` silently dropped their
  arguments (e.g. `cp a.txt b.txt` became just `copy`). Both are fixed.

### Known limitation (not changed)
`parser.py` treats *any* `N.`/`N)` line in the uploaded Markdown as a step,
not just ones under a dedicated steps section — an unrelated numbered list
elsewhere in the document would also be parsed as commands. Keep runbooks
scoped to just the step list, or open an issue if you'd like this scoped
to a heading (e.g. `## Steps`).

## License

MIT — Hackathon MVP
