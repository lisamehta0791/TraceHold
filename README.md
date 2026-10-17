# TraceHold

**Trace the stolen money. Hold only what the records support.**

TraceHold is a decision-support tool for cyber-fraud account holds, built on **Exasol Personal** for
ExaThon India 2026 (Track 01: Money, Risk & Regulation).

When a fraud victim reports, the police ask banks to freeze the accounts that received the money. By then
the money has usually been split, mixed with other money and moved on, so banks often freeze whole
balances, including the savings of people who received a single payment. TraceHold reconstructs where the
reported money went and calculates, for every account, **how much of its balance the transaction records
can actually trace to the fraud**, as a range with the full calculation shown.

> TraceHold never freezes or releases anything, never decides guilt, and never labels anyone. A person decides.
> AI is used only at the edges (reading letters, answering questions, rewording a letter) and **never produces a figure**.
> All data in this project is **synthetic**.

---

## Contents

- [Features](#features)
- [AI at the edges](#ai-at-the-edges)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running TraceHold](#running-tracehold)
- [Using the app](#using-the-app)
- [Tests and evaluation](#tests-and-evaluation)
- [Results on the synthetic data](#results-on-the-synthetic-data)
- [API](#api)
- [Troubleshooting](#troubleshooting)
- [Responsible use](#responsible-use)
- [Licence](#licence)

---

## Features

Every core feature (CF) and additional feature (AF) from the project document, and where to find it.

| # | Feature | Where it is |
|---|---|---|
| CF1 | Request completeness and consistency check, with a clarification draft | Live analysis step ①; case page → *Request check* |
| CF2 | Money-trail reconstruction (splits, merges, loops, reversals, duplicates, clock skew) | Live analysis step ②; case page → *Money path* |
| CF3 | Traceable-amount sizing: pro-rata and FIFO, range, traceable share; accounts in several cases also reported combined | Live analysis step ③; case page account list and side panel |
| CF4 | Layer-dilution analysis | Case page → *Layer dilution* |
| CF5 | Scope-versus-evidence review, with exceptional-case facts (no scores) | Live analysis step ④; case page → *Scope review* |
| CF6 | Statuses and abstention: Determined, Range, Undeterminable, Out of scope | Every account figure |
| CF7 | Evidence packet (HTML and JSON) and neutral account-holder explanation | Case page → *Open evidence packet*, *Plain-language explanation* |
| CF8 | Forwarded-request drafts for money that left the records | Case page → *Forwarded requests*; Live analysis step ④ |
| CF9 | **AI-assisted reading of free-text police letters**, checked by rules and confirmed by a person | Live analysis → *Read a police letter (AI)*; case page → *Request check* → *The letter as received* |
| AF1 | Lien review queue (over-hold, closed but held, past 90 days, past review, escalate) | *Lien review* |
| AF2 | Convention sensitivity (LIFO as a bounding case) | Account side panel; *System → Insights* |
| AF3 | Policy simulation | *System → Insights* |
| AF4 | Speed-of-movement analysis | *System → Insights* |
| AF5 | Oversight summary | *Lien review* (bottom) |
| AF6 | Audit log and reproducible re-runs with checksums | *System → Runs & audit log* |
| AF7 | **Governed questions over the results through Exasol's MCP server** | *Ask* |
| AF8 | **Checked AI rewording of the account-holder explanation** | Case page → *Plain-language explanation* → *Reword with AI (checked)* |

Also on every result: **What it is based on**, showing the rules applied, every SQL script that ran in Exasol
(readable on the page), how many passes the trail needed, time per step and the run checksum.

## AI at the edges

| Area | AI? | How it is kept honest |
|---|---|---|
| Reading letters (CF9) | Yes, optional | The model must quote the exact text each value came from. Fixed rules then check that the quote is in the letter, that the value follows from it (amounts re-read in digits, English, Hinglish or Devanagari), formats, and the transaction records. Failed values are not used; two different values are a conflict and never resolved silently; a person confirms every field. |
| Trail, sizing, statuses, packet (CF1–CF8) | **No** | Set-based SQL in Exasol with a conservation check. |
| Questions (AF7) | Yes, optional | The query runs through **Exasol's MCP server** as a read-only database user that can see only results views (`TH_RESULTS`), never raw transactions or the answer key. The SQL and the rows are always shown; any number in the wording must appear in the rows. |
| Rewording (AF8) | Yes, optional | A check confirms every amount, date, account and reference is unchanged and no claim is added; otherwise the template letter is kept. |

The model (Groq, `openai/gpt-oss-120b`) runs with temperature 0 and a fixed seed. Every call is logged in Exasol
(`AI_LOG`). Only synthetic data is ever sent. **With no API key, or with `TRACEHOLD_AI=off`, TraceHold works fully**
and every figure is identical (tested).

## How it works

```
 synthetic data generator ──► Exasol Personal ──► SQL analysis engine (runs inside Exasol) ──► result tables
   (backend/generator)          (all data)          (database/*.sql)                            │
                                                                                                 ▼
                                               website (frontend) ◄── FastAPI (backend/app) ◄────┘
                                                                         │  ▲
                                          Groq model (letters, wording) ─┘  └─ Exasol MCP server (read-only questions)
```

1. **Generate**: a synthetic banking economy (about 136,000 accounts, 2.4 million transactions) with 2,400 fraud
   cases in nine patterns, injected data defects, synthetic police letters, and a separate answer key.
2. **Load**: the files are bulk-loaded into Exasol.
3. **Analyse inside Exasol**: set-based SQL cleans the postings, rebuilds every account's running balance, follows
   the stolen money layer by layer, allocates it under the pro-rata, FIFO and LIFO methods, checks every request
   and compares it with the evidence. No row-by-row processing happens outside the database.
4. **Serve**: the API reads the result tables; the website shows and explains them.

The method, the AI boundary and the known limitations are in [docs/method.md](docs/method.md).

## Tech stack

| Layer | Technology |
|---|---|
| Database and analytics | Exasol Personal (nano runtime in Docker) |
| Analysis | SQL (window functions, set-based iteration), orchestrated from Python |
| Backend | Python 3.11+, FastAPI, pyexasol |
| AI (optional) | Groq API (`openai/gpt-oss-120b`), Exasol's open-source MCP server (`exasol-mcp-server`, in the project's `.venv-mcp`) |
| Frontend | React 18, TypeScript, Vite, Motion, Recharts |
| Tests | pytest (unit, property, determinism, separation, AI-off), Playwright for browser checks |

## Project structure

```
TraceHold/
├── backend/
│   ├── app/            FastAPI app, analysis orchestrator, loader, live-analysis engine, evaluation
│   │   └── ai/         AI at the edges: Groq client and log, letter reading, questions via MCP, rewording
│   ├── generator/      synthetic data, police letters, and the independent ground-truth ledger
│   ├── benchmark/      benchmark harness
│   ├── results/        evaluation, AI evaluation and benchmark results (JSON / Markdown)
│   ├── tests/          pytest suite
│   └── requirements.txt
├── database/           every SQL script that runs inside Exasol (schema, analysis steps, AI tables and views)
├── frontend/           the website (src/pages, src/components)
├── docs/method.md      method, rules, AI boundary and known limitations
├── data/               generated datasets (created locally, not committed)
├── .env.example        settings template (copy to .env; never commit .env)
├── .venv-mcp/          Exasol's MCP server, installed by the AI setup (not committed)
├── setup.ps1           optional one-command start (Windows)
└── stop.ps1            stops the database cleanly
```

## Requirements

- Windows 10/11 with **Docker Desktop**
- **Exasol Personal starter kit**: https://github.com/exasol/exasol-personal (creates the database password file
  `%USERPROFILE%\.exasol-starter-kit\credentials\nano_sys_password`)
- **Python 3.11+** and **Node.js 20+**
- About 8 GB RAM and 3 GB free disk space
- For the AI features (optional): a **Groq API key** (https://console.groq.com). Exasol's open-source MCP server is
  installed automatically inside the project (`.venv-mcp`) by the AI setup step

## Installation

Run these once, in PowerShell, from the project folder.

**1. Start the Exasol database (first time only)**

```powershell
$pw = "$env:USERPROFILE\.exasol-starter-kit\credentials\nano_sys_password"
docker volume create lienlens-exasol-data
docker run -d --name exasol-nano --shm-size=512m -m 3g -p 127.0.0.1:8563:8563 `
  -v lienlens-exasol-data:/exa -v "${pw}:/run/secrets/sys_password:ro" `
  exasol/nano:2026.2.0-nano.3-amd64 init sys_password_file=/run/secrets/sys_password
docker logs -f exasol-nano        # wait for "Database is now up and running", then Ctrl+C
```

The `init` command is only valid the first time, so recreate the container without it:

```powershell
docker stop -t 180 exasol-nano; docker rm exasol-nano
docker run -d --name exasol-nano --restart unless-stopped --stop-timeout 180 --shm-size=512m -m 3g `
  -p 127.0.0.1:8563:8563 -v lienlens-exasol-data:/exa exasol/nano:2026.2.0-nano.3-amd64
```

**2. Install the backend and the frontend**

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

**3. Generate the data, load it and run the analysis**

```powershell
python backend\generator\generate.py --scale 1.0 --seed 2026 --out data\L     # 2-3 minutes
python backend\generator\letters.py data\L                                     # synthetic police letters
cd backend
..\.venv\Scripts\python -m app.load ..\data\L --fresh                         # about 1 minute
..\.venv\Scripts\python -m app.engine                                         # 2-4 minutes
..\.venv\Scripts\python -m app.evaluation                                     # about 1 minute
cd ..
```

Use `--scale 0.2` for a smaller, faster dataset. The analysis prints each step as it runs.

**4. Set up the AI features (optional)**

Copy `.env.example` to `.env` and put your Groq key in it:

```
GROQ_API_KEY=your_key_here
```

Then install Exasol's MCP server in the project, create the AI tables, load the letters and create the read-only
question user:

```powershell
cd backend
..\.venv\Scripts\python -m app.ai_setup
cd ..
```

It prints a check that the question user can read the results views and **cannot** read raw transactions or the
answer key. Its password is stored in `.env`. Reloading the data with `--fresh` removes the AI tables; TraceHold
recreates them (and reloads the letters) automatically the next time an AI feature is used.

## Running TraceHold

The website needs the **backend API** running, and the backend needs **Exasol** running.

**1. Make sure Exasol is running**

```powershell
docker start exasol-nano
```

**2. Start the backend API** (terminal 1, keep it open)

```powershell
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Restart it (`Ctrl+C`, then the same command) whenever the backend code changes.

**3. Open the website**, either way:

- **Built website, served by the backend:** build once, then open http://127.0.0.1:8000

  ```powershell
  cd frontend
  npm run build
  ```

- **Development server with hot reload** (terminal 2): open http://localhost:5173

  ```powershell
  cd frontend
  npm run dev
  ```

  The development server forwards `/api` to the backend on port 8000. If the backend is not running, it prints
  one message saying how to start it, and the pages show the same message.

**Stopping:** press `Ctrl+C` in the backend and frontend terminals, then stop the database cleanly:

```powershell
docker stop -t 180 exasol-nano      # or: .\stop.ps1
```

Always give Exasol time to shut down (`-t 180`). Killing it mid-write can corrupt its storage.

**Optional shortcut:** `.\setup.ps1` performs the steps above automatically: it starts Docker and Exasol, installs
what is missing, loads data and runs the analysis only if they are missing, sets up the AI features, builds the
website and starts the backend. Run it with `powershell -ExecutionPolicy Bypass -File .\setup.ps1`.

## Using the app

| Page | Use it to |
|---|---|
| **Home** (`/`) | Read what TraceHold does and why. |
| **Live analysis** | Pick a demo scenario, enter your own accounts and transfers, or **read a police letter with AI**. Press **Run analysis in Exasol**: the verdict comes first (asked to hold vs supported), then six explained steps ending with the rules and SQL used. |
| **Cases** | Browse the 2,400 stored cases (*All cases*) or the totals (*At a glance*). Open a case, click an account, and open **How it was calculated** or **What it is based on**. **Open evidence packet** gives the printable report. |
| **Lien review** | Filter existing holds by problem and open the case behind any hold. |
| **Ask** | Ask a question in plain English or click a suggested one. The answer shows the SQL that ran through Exasol's MCP server and the rows. |
| **System** | *Accuracy*, *Insights*, *Runs & audit log* (re-run the analysis in Exasol), *Benchmark*, *AI* (boundary, measured AI results, AI call log). |

A short demo path: **Live analysis → Read a police letter (AI)** → pick *Split, merge and cash-out* and the
*Hinglish message* → **Read the letter with AI** → confirm → **Run analysis in Exasol**. The missing contact and
legal provision are flagged, the over-broad lien is shown, and every number links to its SQL.

## Tests and evaluation

```powershell
cd backend
..\.venv\Scripts\python -m pytest tests          # 34 tests; database tests are skipped if Exasol is not running
..\.venv\Scripts\python -m app.evaluation        # accuracy against the generator's answer key
..\.venv\Scripts\python -m app.ai_eval           # AI features on held-out letters (needs GROQ_API_KEY; 20-30 min)
```

The tests cover the worked example to the paisa, conservation on random cases, determinism (same case twice, same
evidence packet twice), that the analysis never reads the answer key, that the calculation path never imports the
AI package, the AI-off test, the read-only question user, and every rule check that runs after an AI call.

## Results on the synthetic data

Large dataset: 2,395,178 transactions and 2,400 cases (`backend/results/evaluation.json`):

| Measure | Result |
|---|---|
| Worked example from the project document | reproduced to the paisa |
| Conservation (every rupee accounted for) | 7,200 / 7,200 checks pass |
| Amounts vs an independent ledger | 99.85% (pro-rata) and 99.91% (FIFO) of account figures within one paisa |
| Request-defect detection | 100% precision, 100% recall (946 planted defects, 14 types) |
| Money-trail reconstruction | 99.4% precision, 99.9% recall |
| Over-broad requests flagged | 3,588 of 3,589, no false flags |
| Reproducibility | re-runs on the same data give the same results checksum |

AI features (`backend/results/ai_evaluation.json`; prompts tuned on 24 development letters, results on 60 held-out letters):

| Measure | Result |
|---|---|
| CF9 field extraction | 98.8% precision, 99.2% recall; 90% of letters with every field right |
| CF9 values used without a quote from the letter | 0 |
| CF9 planted conflicting amounts flagged | 4 of 4 |
| CF9 fields a person would have to correct | 1.2% |
| AF7 questions answered with the same rows as hand-written SQL | 10 of 10, plus 2 of 2 out-of-scope questions refused |
| AF7 wordings rejected by the number check | 0 of 12 |
| AF8 rewordings that kept every fact | 8 of 8 |
| AI-off test | figures identical with AI off and on |

These figures describe synthetic data only. They are not evidence of real-world performance.

**Benchmark.** `backend/results/benchmark.md` has Exasol timings for the same workloads at 241k and 958k
transactions; the *System → Benchmark* page adds the full analysis run on all 2.4 million. A PostgreSQL comparison
was planned, but both databases do not fit in this laptop's memory at the same time, so no comparison is claimed.

## API

The backend serves JSON under `/api` (interactive docs at http://127.0.0.1:8000/docs).

| Endpoint | Returns |
|---|---|
| `GET /api/health` | database status and row counts |
| `GET /api/overview` | totals across all cases |
| `GET /api/cases`, `GET /api/cases/{id}` | case list (search, filter, pages) and one case with trail and sizing |
| `GET /api/cases/{id}/explain/{account}` | step-by-step calculation for one account |
| `GET /api/cases/{id}/basis`, `GET /api/basis/sql/{script}` | rules, run steps and the SQL text behind a result |
| `GET /api/cases/{id}/packet`, `/packet.html`, `/explanation/{account}` | evidence packet and account-holder explanation |
| `GET /api/playground/scenarios`, `POST /api/playground/run` | live analysis demos and runs |
| `GET /api/lien-review`, `GET /api/oversight` | existing holds ranked for review |
| `GET /api/evaluation`, `GET /api/policy-sim`, `GET /api/speed`, `GET /api/sensitivity` | accuracy and insights |
| `GET /api/runs`, `POST /api/runs`, `GET /api/runs/{id}` | analysis runs (start one, follow its steps) |
| `GET /api/ai/status`, `GET /api/ai/log`, `GET /api/ai/evaluation` | AI set-up, call log and measured results |
| `GET /api/ai/letters`, `GET /api/cases/{id}/letter`, `POST /api/ai/extract`, `POST /api/ai/extract/{id}/confirm` | CF9 letters, reading and confirmation |
| `GET /api/ai/ask/templates`, `POST /api/ai/ask` | AF7 questions through Exasol's MCP server |
| `POST /api/cases/{id}/explanation/{account}/reword` | AF8 checked rewording |

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| `npm run dev` prints proxy / `ECONNREFUSED` errors, pages say the API is not running | The backend is not running. Start it (see [Running TraceHold](#running-tracehold), step 2). |
| A page shows "This part of the page could not be shown" | The backend is older than the website. Restart the backend and reload the page. |
| Page says "analysis results are not in Exasol yet" | Run the analysis once: `cd backend` then `..\.venv\Scripts\python -m app.engine`. |
| Page says "an analysis run is rebuilding the results" | A run is in progress; the page reloads by itself when it finishes (about 3 minutes). |
| AI buttons say "AI is off" | Add `GROQ_API_KEY` to `.env` and restart the backend. Everything else works without it. |
| *Ask* says the read-only user or the MCP server is not set up | Run `python -m app.ai_setup` from the `backend` folder. |
| AI calls are slow | Groq's free tier allows about 8,000 tokens a minute; TraceHold waits and retries automatically. |
| Backend cannot connect to Exasol | `docker start exasol-nano` and wait about a minute; check `docker logs --tail 20 exasol-nano`. |
| Exasol stops or crashes under load | Give Docker more memory (Docker Desktop → Settings → Resources, or `memory=` in `%USERPROFILE%\.wslconfig`). |
| Port 8000 is busy | Find it with `netstat -ano \| findstr :8000`, or start the backend with `--port 8010` and run the dev server with `$env:TRACEHOLD_API_PORT=8010; npm run dev`. |

## Responsible use

- Decision support only: the system never places, changes or releases a hold.
- Results are ranges with a status; the system abstains when records are incomplete.
- No model produces or changes a figure; AI output always carries its evidence and is checked by rules.
- Neutral wording for account holders; no suspicion scores or labels.
- Only synthetic data is processed or sent to any model.
- References to court directions and procedures are context, not legal advice.

## Licence

[MIT](LICENSE) © 2026 Lisa Mehta
