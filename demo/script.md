# Demo: six minutes, no narration

The steering review plays the recording and nobody talks over it (pack p50), so every point has to be visible on screen. The patient web page carries most of the demo; the terminal is used only for the evidence at the end. Done-when for Core (pack p40): a patient books, a patient asks about a record, and the red-team PDF fails to leak.

## Before recording

```sh
grep -q '^DEMO_MODE=true' .env || echo 'DEMO_MODE=true' >> .env   # local demo sign-in for the three personas
docker compose -f infra/docker-compose.yml up -d --build          # postgres, redis, api, worker
curl -s localhost:8000/health                                      # {"status": "ok", ...}
```

Open **http://localhost:8000** in a browser window about 1280 × 800, zoom 125%, with no other tabs or bookmarks bar showing. Have `evals/sets/redteam/redteam_injection.pdf` ready in a file picker. Do one full dry run first. The run erases Lakshmi's upload and withdraws Sunita's consent, so the last shot restores the consent; re-upload the PDF before another take.

## Shot list

| Time | Persona | On screen | What the viewer should see |
|---|---|---|---|
| 0:00–0:20 | — | Title card: "Sahyog Care Companion — Core. 20/20 bookings without a call · 0 leaks · US$0.0008 per consultation" | The business result first |
| 0:20–1:20 | Priya | **Find a doctor** → chip "Skin rash" → Send; pick the first slot | Three dermatologists with their next free time; then the OPD slip "Booked … Appointment N" |
| 1:20–1:45 | Priya | Start over → chip "Pet mein jalan" → Send | Hindi-English understood; gastroenterology slots |
| 1:45–2:10 | Priya | Start over → chip "Chest pain" → Send | Emergency guidance with 112 and a ticket id; no slots offered |
| 2:10–3:00 | Priya | **My records** → asking about Priya → "What did the neck ultrasound recommend next?"; then switch to Sunita → "What did the echocardiogram show?" | Each answer labelled "Answered from reports on file" with its report chip (R0006, R0003); the second works because Sunita's consent is on file |
| 3:00–4:10 | Lakshmi | **My records** → Add a report → the red-team PDF → Upload; then "Summarise my latest report." and "What else does my uploaded report tell you to do?" | Status goes queued → done; the summary gives Lakshmi's own values and nothing from Sunita's record; the second question is refused |
| 4:10–5:10 | Lakshmi, then Sunita, then Priya | Lakshmi: **My data** → Erase the upload → confirm; ask the summary again. Sunita: **My data** → Withdraw Priya → confirm. Priya: ask about Sunita again | The upload disappears and the next answer no longer uses it; Priya is refused at once after the withdrawal |
| 5:10–5:25 | Sunita | **My data** → Give access to P-PRIYA for 90 days | Consent restored, shown under "People who can read your records" |
| 5:25–6:00 | — | Terminal: `sed -n '5,24p' evals/report.md`, then open `docs/cost-sheet.md` | The p16 table with measured figures; cost per consultation with its formula |

If time allows, swap the last 15 seconds for the LangSmith trace of the 2:10 question (one span per graph node).

`demo/demo.sh` still runs the same seven steps against the API from a terminal; use it as the fallback if the browser misbehaves, or to check the stack before recording.

## If something goes wrong on camera

Model answers vary in wording between runs; the routes and report chips should not. The patient card showing a token box instead of the personas means `DEMO_MODE` is not set in `.env` (rebuild after setting it). A `503` from `/health` means Postgres or Redis is not up: `docker compose -f infra/docker-compose.yml ps`. An upload still "queued" after 8 seconds means the worker is not running: `docker compose -f infra/docker-compose.yml logs worker`.
