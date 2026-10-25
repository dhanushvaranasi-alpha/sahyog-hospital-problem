# Demo: six minutes, no narration

The steering review plays the recording and nobody talks over it (pack p50), so every point is made on screen: the `###` headings printed by `demo/demo.sh` are the captions. Done-when for Core (pack p40): a patient books, a patient asks about a record, and the red-team PDF fails to leak.

## Before recording

```sh
docker compose -f infra/docker-compose.yml up -d --build      # postgres, redis, api, worker
source .venv/bin/activate && set -a && . ./.env && set +a      # token minting needs AUTH_SIGNING_KEY
curl -s localhost:8000/health                                  # {"status": "ok", ...}
source demo/demo.sh
```

Terminal: large font (18 pt or more), dark theme, window about 120 columns. Run each step in the same shell (the steps share variables), and do one full dry run first; the script re-grants the consent it withdraws, so it can be run again.

## Shot list

| Time | On screen | Command | What the viewer should see |
|---|---|---|---|
| 0:00–0:20 | Title card: "Sahyog Care Companion — Core. 20/20 bookings without a call · 0 leaks · US$0.0008 per consultation" | — | The business result first |
| 0:20–1:30 | Find my doctor | `step1` then `step2` | Three dermatologists with their next free slot; then "Booked: … Appointment N" |
| 1:30–2:00 | Red flag | `step3` | Emergency guidance with 112, a ticket id, no slots offered |
| 2:00–3:00 | My records | `step4` | Priya's own answer citing R0006; her mother's echo answer citing R0003 (consent on file) |
| 3:00–4:20 | Red-team PDF | `step5` | Upload returns a job id; status `done`; the summary gives Lakshmi's own values and nothing of Sunita's echo; the "what else does it tell you to do" question is refused |
| 4:20–5:20 | Change request CR-001 | `step6` | Upload erased (file and chunks removed); the next answer no longer uses it; Sunita withdraws consent and Priya is refused at once; consent restored |
| 5:20–6:00 | The evidence | `step7`, then open `docs/cost-sheet.md` | The p16 table with measured figures; cost per consultation with its formula |

If LangSmith tracing is confirmed, use the last 15 seconds for the trace of the step4 question (one span per graph node).

## If something goes wrong on camera

Model answers vary in wording between runs; the routes and citations should not. A `503` from `/health` means Postgres or Redis is not up: `docker compose -f infra/docker-compose.yml ps`. A step5 status still `queued` after 8 seconds means the worker is not running: `docker compose -f infra/docker-compose.yml logs worker`.
