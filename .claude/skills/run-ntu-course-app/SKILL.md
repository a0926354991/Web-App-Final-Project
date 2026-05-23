---
name: run-ntu-course-app
description: Launch, smoke-test, or screenshot the NTU course recommendation web app (FastAPI backend on :8000 + vanilla-JS frontend on :5500). Use this skill when asked to run, start, build, smoke-test, screenshot, or verify the app end-to-end. Drives the browser via Playwright (chromium).
---

# Run NTU Course Recommendation App

Two-process web app: FastAPI backend (:8000) + plain `python -m http.server` for the ES-module frontend (:5500). No build step. The agent path drives a headless Chromium via Playwright (`driver.py`) — that's how you take screenshots and run the E2E smoke.

All paths below are **relative to the repo root** (`Web-App-Final-Project/`).

## Prerequisites

```bash
test -x .venv/bin/uvicorn && test -x .venv/bin/playwright && echo "venv OK"
test -f backend/data/app.db && echo "db OK"
```

If `venv OK` doesn't print:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install playwright && playwright install chromium
```

If `db OK` doesn't print:
```bash
source .venv/bin/activate && python backend/scripts/ingest_csv.py
```

## Run (agent path — DO THIS)

```bash
# 1. Kill anything already on :8000 / :5500
lsof -ti:8000 | xargs kill -9 2>/dev/null; lsof -ti:5500 | xargs kill -9 2>/dev/null

# 2. Boot backend + frontend in background
source .venv/bin/activate
nohup uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 &
nohup python3 -m http.server 5500 --directory frontend/src > /tmp/http.log 2>&1 &
sleep 4

# 3. Smoke (register → search → drawer → profile → recommend → dark mode)
.venv/bin/python .claude/skills/run-ntu-course-app/driver.py
```

Expected output ends with `✅ smoke pass — 7 screenshots in .claude/skills/run-ntu-course-app/screenshots`. Exit code 0.

### Driver sub-commands

```bash
# Full smoke (default)
.venv/bin/python .claude/skills/run-ntu-course-app/driver.py

# Show the browser window (debug driver itself)
.venv/bin/python .claude/skills/run-ntu-course-app/driver.py --headed

# Screenshot one view, no register/login
.venv/bin/python .claude/skills/run-ntu-course-app/driver.py screenshot discover
# views: dashboard | discover | userinfo | history | schedule | wishlist | fit
```

Screenshots land in `.claude/skills/run-ntu-course-app/screenshots/`.

### Probe backend directly (faster than driver for API-only changes)

```bash
curl -s http://127.0.0.1:8000/health
curl -s "http://127.0.0.1:8000/courses?q=微積分&limit=3" | python3 -m json.tool | head -20
open http://127.0.0.1:8000/docs    # macOS Swagger
```

### Stop the servers

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5500 | xargs kill -9 2>/dev/null
```

## Run (human path)

```bash
# Terminal 1
source .venv/bin/activate && uvicorn backend.api.main:app --reload

# Terminal 2
cd frontend/src && python3 -m http.server 5500

# Browser
open http://localhost:5500
```

Ctrl-C each terminal to stop. Useful when you want to click through the UI yourself; useless from an agent — that's what `driver.py` is for.

## Test

No pytest suite yet. The driver IS the test.

```bash
# Python syntax sanity
source .venv/bin/activate
python3 -c "
import ast
for f in ['backend/api/main.py','backend/api/auth.py','backend/api/recommendations.py']:
    ast.parse(open(f).read()); print('OK', f)
"

# JS module syntax (16 ES modules — Node --check parses them)
for f in frontend/src/js/*.js; do node --check "$f" || break; done && echo "all js OK"
```

## Gotchas

- **The frontend MUST be served over HTTP, not opened as `file://`.** ES modules in `index.html` refuse to load from `file://`. Opening `index.html` directly = blank page with CORS errors.
- **`backend/data/app.db` is ~30 MB and gitignored.** Fresh clones must run `python backend/scripts/ingest_csv.py` first or every API call returns empty.
- **Smoke driver creates `smoke_<timestamp>` test users.** They accumulate. Clean periodically: `sqlite3 backend/data/app.db "DELETE FROM users WHERE username LIKE 'smoke_%'"`.
- **Login rate limit is per `(IP, username)`.** Running the smoke 9+ times in 60s for the same username → 429. The driver dodges this by timestamping; hard-coding a username for debug will get you rate-limited.
- **Source-map 404s in the console are harmless.** Chart.js's CDN doesn't publish `.map` files. The driver filters these out before failing.
- **`expires_at` was added to `sessions` table mid-development.** `init_auth_tables()` has a one-shot ALTER for old DBs. If `/auth/me` returns `no such column: expires_at`, restart uvicorn so the startup hook runs.
- **macOS-only on this dev machine; Linux/CI not verified.** Playwright install is the same on Linux but `lsof -ti:PORT | xargs kill` needs `--no-run-if-empty` on GNU xargs (BSD xargs is fine).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `❌ backend not reachable on http://127.0.0.1:8000` | uvicorn crashed at boot | `cat /tmp/uvicorn.log`, usually missing dep — `pip install -r requirements.txt`. |
| `❌ frontend not reachable on http://127.0.0.1:5500` | http.server not running or wrong dir | `cat /tmp/http.log`. Re-run with `--directory frontend/src`. |
| Driver hangs on `wait_for_selector("#results-body tr[data-id]")` | DB is empty | `python backend/scripts/ingest_csv.py`. |
| Screenshots all show blank white page | http.server started from repo root, JS modules 404 | Must be `--directory frontend/src`. Browser console would show 404 on `js/main.js`. |
| Register fails with 429 | Rate-limited | Wait 60s OR delete `smoke_*` users from DB (see Gotchas). |
| Driver passes but drawer screenshot shows no PTT reviews | Course with `n_reviews=0` was first hit | Not broken — search for `微積分` (driver default) reliably hits reviewed courses. |