# Schichtplan-Tool

**Live frontend:** [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/)

An automated shift-scheduling tool for HR teams, built with React (frontend) and Flask (backend). HR defines employees, their availability constraints, and shift types with staffing requirements; the tool generates a full monthly schedule via backtracking search and lets HR fine-tune the result by hand — including swapping shifts between employees.

This is a standalone project living alongside the Support Ticket System in this repository, and the fourth project in a portfolio (after the portfolio website, the ticket system, and a paused API-integration project).

## Grundidee

Industry-independent shift planning for HR: define employees with constraints (e.g. "never works Wednesdays", "only early shift"), define shift types with per-weekday staffing needs, then generate a month's schedule automatically.

Two kinds of account:

- **Personalabteilung (HR)** – creates, edits and deletes everything: employees, shift types, generated plans, and accounts. Sees the whole plan.
- **Mitarbeiter (employee)** – read-only, and only their *own* shifts, with one narrow, deliberate exception: they may report their own sick/vacation days for the current month (see [Self-service sick / vacation](#self-service-sick--vacation) below). Every other write is refused by the API, not just hidden in the UI — colleagues' shifts, the staff roster, gaps in the plan and the workload comparison are never sent to them at all.

Being scheduled does not require an account — an employee only needs one if they should be able to look their own shifts up. Each employee account is linked to its roster entry, which is what makes "own shifts" meaningful, so the link is required when the account is created. Because of that link an employee cannot be deleted while an account still points at them: the account has to go first, which HR does on the Konten page. Nobody can delete the account they are signed in with, or the last remaining HR account.

The tool is usable in **German or English** – see [Language](#language) below.

## Scope

- **Role-based access** – HR manages everything; employees get a read-only view of the plan, plus self-service sick/vacation reporting
- **Sign-in required** – the first visit sets up the HR account; after that everything is behind a login
- **Monthly plans** – one schedule per calendar month
- **Backtracking scheduling algorithm** – not greedy (see below)
- **Manual post-editing by HR** – reassign any slot, or swap two shifts between employees
- **Balanced workloads** – the plan spreads shifts evenly once every shift that *can* be staffed is
- **Part-time aware** – employees can carry a weekly target-hours figure instead of only a monthly shift count
- **Rest periods** – an 11h (configurable) minimum between shifts, enforced during generation and flagged on manual edits
- **Bilingual** – German or English, switchable per browser at any time

## Features

- **Authentication and roles** – session-based login with hashed passwords (Werkzeug). Every route that touches staff data requires a session, and every route that *changes* anything requires the HR role. Registration is open only until the first account exists — a fresh install sends you straight to setup; afterwards only HR can create accounts, so nobody can sign themselves up and read the roster
- **Nobody sets anyone else's password** – whoever creates an account never chooses its password. Creating one emails that person a one-time link (valid 7 days, single use) on which they pick a password nobody else has seen; until they do, the account cannot be signed into. This applies to employee *and* HR accounts alike — an employee's invitation goes to the address on their roster entry, an HR account carries its own. The only exception is the very first account on a fresh install, which sets its own password because there is nobody yet to invite it. Re-inviting issues a fresh link and revokes the current password, which doubles as the "forgotten password" path without anyone else learning the new one
- **Two views of the plan** – a **calendar** laid out like a wall planner (one column per weekday, one row per week, each day listing its shifts and everyone working them), and a **table** for editing. HR gets both; employees get both read-only
- **Several people per shift** – each shift type carries a required headcount *per weekday*, so a weekday can need 2 on the early shift and 3 on the late one while a Sunday needs 1 of each. The scheduler fills each of those places separately and the calendar lists everyone assigned
- **Day-level changes** – beyond the shift type's usual hours (e.g. 08:00–16:30), HR can change what a shift runs on one single date without touching any other day, and can add or remove a place on a given day. Changed hours are marked with `*` in both views and can be reset to the shift type's default in one click
- **Employee management** – name, optional email, optional monthly shift cap, an optional **weekly target-hours** figure for part-time staff, a **minimum rest period** between shifts (defaults to 11h, individually adjustable), recurring weekday unavailability (e.g. no Wednesdays), one-off unavailable dates (vacation/sick leave HR enters directly), and an optional allow-list restricting an employee to specific shift types (e.g. "only early shift")
- **Shift type management** – name, start/end time, color, and required headcount per weekday (weekday and weekend staffing needs are often different)
- **Automatic monthly schedule generation** via backtracking search, respecting weekly-hours caps and rest periods as hard constraints alongside the existing ones
- **Manual editing** – reassign any shift slot to a different employee (or leave it unfilled), with non-blocking warnings if the change violates that employee's usual constraints — including a weekly-hours overrun or too little rest before/after the shift — so HR can always override, but never by accident
- **Shift swapping** – pick two shifts and swap their assigned employees in one atomic action
- **Unfilled-slot reporting** – when there isn't enough eligible staff, the tool reports exactly how many/which slots couldn't be filled instead of failing silently or crashing
- **Workload distribution panel** – shifts per employee (and weekend shifts per employee) for the month, recomputed from what's actually saved, so it stays honest as HR edits the plan by hand
- **Self-service sick/vacation** – an employee can report their own sick or vacation days for the current month; a shift they were already assigned frees up automatically for HR to cover, and HR gets ranked replacement suggestions for it (see below)
- **Bilingual UI** – every label, message and validation error is available in German and English (see below)

## Self-service sick / vacation

The one deliberate, narrow exception to "employee accounts are read-only": a signed-in employee can report their own sick or vacation days, but only for the current calendar month (checked against the server's own clock, never anything the browser sends). HR can do the same for any employee, any date, from the schedule table.

Reporting an absence for a day the employee already holds a shift on:

- **frees the shift** – it goes back to being an ordinary unfilled slot (counted in `unfilled_count`, shown in the distribution panel, reassignable from the usual dropdown)
- **keeps the context** – HR sees "Krank (war: Anna)" / "Sick (was: Anna)" instead of a bare gap, so it's clear why the slot opened up and who to ask about it
- **still shows on the employee's own calendar** – as "Krank"/"Sick" or "Urlaub"/"Vacation", not as a normal shift, even though the slot itself no longer has their name on it
- **feeds back into the scheduler** – a later regeneration of that month won't reassign the same person straight back onto a day they reported as unavailable

HR gets a **"Vorschläge"/"Suggestions"** action on any freed slot: it re-runs the same eligibility checks used for manual reassignment (weekday/date availability, allowed shift types, not already working that day, monthly cap, weekly-hours cap, rest period) against every active employee and ranks the eligible ones by current workload, so the least-loaded suitable person is offered first. Picking one is a normal reassignment — nothing special has to be undone if it turns out to be wrong.

## Language

The UI is available in German (default) and English, toggled from the navbar; the choice is remembered per browser (`localStorage`) and sent to the backend on every request via an `X-Lang` header, so validation errors and the non-blocking constraint warnings above come back in the same language as the rest of the page — not just the static labels. Adding a third language means extending `backend/i18n.py`'s translation table and `frontend/src/i18n/translations.js` the same way; both are hand-rolled (no `react-i18next`/`Flask-Babel`) to keep the near-zero-dependency footprint the rest of the project has.

## The scheduling algorithm

`backend/scheduler.py` assigns employees to shifts via **chronological backtracking with branch-and-bound**, not a greedy pass.

A greedy algorithm assigns the first workable candidate to each slot and never reconsiders. That can leave avoidable gaps: if employee A is the only one who can cover a later shift, but a greedy pass already spent them on an earlier shift that someone else could equally have covered, the later shift ends up unfilled for no good reason.

This algorithm instead explores assignments slot by slot in calendar order, and **undoes (backtracks) a choice** whenever it turns out to block a later slot with no other eligible candidate. It keeps searching after finding one complete assignment, in case a different set of choices leaves fewer slots unfilled (branch-and-bound: a running best-so-far result prunes any branch that can't beat it, and search stops early once a fully-staffed solution is found). A node/time budget acts as a safety valve on pathologically understaffed inputs, so a request always returns a best-effort result instead of hanging.

Hard constraints enforced during search: an employee can't work two shifts the same day, can't be scheduled on a weekday/date they're marked unavailable, can't be scheduled outside their allowed shift types (if restricted), can't exceed their monthly shift cap (if set), can't exceed their weekly target hours (if set — see [Part-time / weekly hours](#part-time--weekly-hours)), and can't be left with less than their minimum rest period against the shift immediately before or after (see [Rest periods](#rest-periods)).

`backend/test_scheduler.py` includes a test that constructs a scenario where a literal greedy-first-fit pass provably leaves gaps that this algorithm closes, alongside tests for each hard constraint and for graceful degradation when there isn't enough staff to fill every slot.

### Part-time / weekly hours

An employee can carry an optional `weekly_hours` target (e.g. "works 30h/week") instead of only the existing monthly shift-count cap. It's enforced as a hard ceiling in minutes over each Monday–Sunday week: once assigning another shift would push the employee past their target for that week, they stop being eligible for further shifts *that week* — which, combined with the existing one-shift-per-day rule, is what spreads a part-timer's hours across several distinct days each week rather than letting them bunch onto a few long ones. It's a ceiling and a best-effort target, not a guaranteed minimum — same "report gaps rather than force an answer" philosophy the rest of the scheduler already has for `max_shifts_per_month`.

Both this cap and the rest-period check below are inherently scoped to the month being generated (the search only ever sees one month's slots at a time, same limitation `max_shifts_per_month` already has) — but the *manual-edit* warning path (see [Rest periods](#rest-periods)) queries the actually-saved data with no such boundary, so it correctly sees a conflict that spans two calendar months.

### Rest periods

Every employee has a `min_rest_hours` setting (defaults to 11h, the German ArbZG minimum, individually editable per employee). During generation this is a hard constraint: the search won't assign a shift that would leave less than that much rest against the employee's own shift the day before or after — including across midnight, e.g. a 22:00–06:00 shift followed by an 08:00 shift the same "next day" is only 2h apart even though the two are different shift types on different dates.

Manual reassignment and swapping only ever produce a **non-blocking warning** for this (exactly like every other constraint already works) — the violation is scoped to that one employee's one shift, so HR can fix it by hand while everyone else's shift that day is completely unaffected.

### Fairness (v1.3)

The search optimizes a **lexicographic** objective:

1. minimize unfilled shifts — a fairer plan is never worth leaving a shift unstaffed
2. minimize the **sum of squared shift counts** per employee

Minimizing the sum of squares is equivalent to minimizing the variance of the workload once the number of assigned shifts is fixed, and it updates in O(1) per assignment: giving a shift to someone who already has `L` raises the cost by `2L+1`, so each extra shift for an already-busy person is penalized more than a first shift for an idle one. Both components only ever grow as the search goes deeper, so any branch whose partial cost already loses to the best complete plan can be pruned safely.

An optional `weekend_weight` applies the same idea to weekend shifts specifically — weekend duty is usually the scarce thing that quietly lands on the same few people every month.

### Slot ordering (v1.2), and why it is adaptive

The planned v1.2 feature was "most constrained first" ordering — the classic CSP minimum-remaining-values heuristic, filling the hardest-to-staff slots first so dead ends surface near the top of the search tree where backtracking is cheap.

Benchmarking it against plain calendar order produced a **result that contradicted the original plan**, and the design changed accordingly:

- On **understaffed** months it is clearly better: it left **17 shifts unstaffed where calendar order left 23**, and an exact CP-SAT solve confirmed 17 is the true minimum.
- On **comfortably staffed** months it is clearly *worse* — not for staffing (both fill everything) but for **balance**. Calendar order interleaves the days naturally, so "always pick the least-loaded eligible person" lands on an evenly balanced plan immediately. Reordering the slots scrambles that: on the 30-person hospital scenario it produced a workload spread of **9 shifts instead of 1**.

So neither ordering is right on its own, and the shipped default (`ordering='auto'`) plans chronologically first and only pays for a second, harder search if that leaves shifts unstaffed — taking whichever plan comes out better. Normal months cost one cheap pass; difficult months get the extra effort where it actually buys something.

## Comparison with other approaches

`backend/benchmark.py` runs every approach against the same seeded scenarios under identical constraints, scored on what an HR user actually cares about: unstaffed shifts, workload spread (busiest minus quietest), weekend spread, and runtime. `backend/baselines.py` contains the alternatives.

Run it with `./venv/bin/python benchmark.py` (needs `requirements-dev.txt` for the CP-SAT reference).

**Hospital ward — 30 people, 3 shifts, 372 shifts to fill:**

| approach | unfilled | spread | weekend | time |
|---|---|---|---|---|
| greedy first-fit | 0 | 31 | 10 | 0.002s |
| greedy, least-loaded | 0 | 1 | 5 | 0.004s |
| random-restart greedy (200×) | 0 | 1 | 6 | 0.849s |
| most-constrained-first only | 0 | 9 | 7 | 0.009s |
| **this tool (v1.3 auto)** | **0** | **1** | **5** | **0.006s** ✓ |
| this tool + weekend equity | 0 | 2 | **2** | 0.416s |
| CP-SAT (OR-Tools, exact) | 0 | 1 | 7 | 5.398s ✓ |

**Understaffed month — 5 heavily restricted people, 124 shifts to fill:**

| approach | unfilled | time |
|---|---|---|
| greedy, least-loaded | 25 | 0.000s |
| greedy first-fit | 18 | 0.001s |
| random-restart greedy (200×) | 17 | 0.084s |
| calendar order only | 23 | 0.380s |
| **this tool (v1.3 auto)** | **17** | 0.693s |
| CP-SAT (OR-Tools, exact) | 17 | 0.037s ✓ |

✓ = proven optimal for staffing *and* balance together.

**What the comparison actually shows:**

- **Naive greedy is not viable.** First-fit hands one person all 31 days of the month while colleagues get nothing (spread 31).
- **Greedy with a least-loaded tie-break is a surprisingly strong baseline** — it matches the optimum on easy months. Its weakness is understaffed ones, where it left 25 shifts unstaffed against the true minimum of 17. This is worth stating plainly: most of the everyday quality comes from that one heuristic, and search earns its keep specifically when staffing is tight.
- **This tool matches CP-SAT's proven optimum on unstaffed shifts in every scenario tested**, and matches it on workload spread in all but one — at ~900× the speed on the largest scenario (0.006s vs 5.4s).
- **CP-SAT is the better tool for a harder problem, not this one.** It proves optimality, which the hand-written search generally cannot, and it would absorb genuinely complex rules (rest periods between shifts, skill mixes, labor-law constraints) that would be painful to hand-code. The tradeoffs against it here are a ~100MB native dependency and a solve time that grows steeply with the roster. For monthly plans at this scale, a ~250-line dependency-free search gets the same answers fast enough to feel instant in the UI.
- **Fairness dimensions genuinely trade off.** Optimizing only total shifts can leave weekend duty lopsided (weekend spread 5 while total spread is optimal); turning on weekend equity cut it to 2 at the cost of one shift of total spread. There is no single "fair", so it's a setting rather than a hardcoded rule.

**Roadmap** (not yet built):
- **v1.1** – a guided shift-swap flow (the underlying swap capability already exists)
- Skill/qualification matching, so a shift can require a specific certification
- Generation-time weekly-hours/rest-period checks that see across a month boundary (currently only the manual-edit warning path does — see [Part-time / weekly hours](#part-time--weekly-hours))

## Tech Stack

**Frontend**
- React (with Vite)
- React Router

**Backend**
- Flask
- SQLite
- Flask-CORS

## Project Structure

```
schichtplan-tool/
├── backend/
│   ├── app.py                 # Flask app: REST routes
│   ├── db.py                   # SQLite/Postgres schema + connection
│   ├── i18n.py                  # Backend message translations (de/en) + t()
│   ├── mailer.py               # Invitation email (SMTP, or logged in dev)
│   ├── scheduler.py            # Backtracking scheduler (ordering + fairness)
│   ├── baselines.py            # Alternative algorithms, for comparison only
│   ├── benchmark.py            # Head-to-head comparison run
│   ├── test_scheduler.py       # Unit tests for the algorithm
│   ├── requirements.txt
│   └── requirements-dev.txt    # + ortools, only needed for the benchmark
└── frontend/
    └── src/
        ├── App.jsx           # Routing, navigation, auth guarding & language toggle
        ├── api.js            # Fetch helper (sends the X-Lang header)
        ├── i18n/
        │   ├── translations.js     # The full de/en dictionary + weekday/month labels
        │   ├── storage.js          # Shared localStorage key/helpers (context + api.js)
        │   ├── context.js          # useTranslation() hook (split out for Fast Refresh)
        │   └── LanguageContext.jsx # LanguageProvider, wraps <App> in main.jsx
        ├── pages/
        │   ├── Login.jsx          # Sign-in
        │   ├── Register.jsx       # First-account setup / the create-account form
        │   ├── Accounts.jsx       # HR: who can sign in, invites, removing accounts
        │   ├── SetPassword.jsx    # Where an invited employee picks their password
        │   ├── Employees.jsx     # Employee CRUD + constraints
        │   ├── ShiftTypes.jsx    # Shift type CRUD + weekday requirements
        │   └── SchedulePage.jsx  # Generate / view / edit the monthly plan
        └── components/
            ├── ScheduleGrid.jsx    # The schedule grid: reassign + swap UI
            ├── ShiftCell.jsx       # One shift/date cell: reassign, swap, suggestions, quick-log absence
            ├── CalendarView.jsx    # Read-only wall-planner view
            ├── Distribution.jsx    # Shifts-per-employee balance panel
            └── AbsenceManager.jsx  # Employee self-service: report/cancel sick & vacation
```

## Local Setup

### Backend

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py
```

Runs by default on `http://localhost:5001` (chosen so it doesn't collide with the ticket-system backend on port 5000 if both run locally at once). Uses a local SQLite file (`schichtplan.db`, gitignored); the schema is created automatically on first run.

On first launch the app has no accounts, so opening it lands on "Erstes Konto einrichten" to create one. In production also set `SECRET_KEY` (it signs the session cookie — the built-in fallback is for local use only) and `ALLOWED_ORIGINS` (comma-separated list of frontend origins allowed to call the API).

**Invitation emails.** Set `SMTP_HOST` (plus `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `MAIL_FROM`) to send them for real, and `APP_BASE_URL` so the link points at the deployed frontend. Without `SMTP_HOST` — which is the default locally — the invitation is written to the server log instead of being sent, so the flow still works end to end. The link is deliberately never returned through the API: only the recipient is supposed to learn the token.

Run the scheduler's unit tests with:

```bash
./venv/bin/python -m unittest test_scheduler -v
```

To run the algorithm comparison (installs OR-Tools for the exact CP-SAT reference):

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python benchmark.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Runs by default on `http://localhost:5173`.

Create a `.env` file in the `frontend` folder with:

```
VITE_API_URL=http://localhost:5001
```

## Deployment

**Frontend:** [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/)

The app runs on SQLite locally and **Postgres in production**, chosen automatically: set `DATABASE_URL` and it uses Postgres, leave it unset and it writes a local `schichtplan.db`. This matters more than it sounds — a free-tier container's filesystem is wiped on every restart, so deploying on SQLite would quietly lose every schedule.

**Backend (Render).** `render.yaml` in the repository root is a blueprint: pointing Render at the repo creates the web service *and* a Postgres database, wires `DATABASE_URL` between them, and generates a `SECRET_KEY`. Two values must be filled in by hand afterwards, because they depend on where the frontend lands:

- `ALLOWED_ORIGINS` – the deployed frontend's origin, e.g. `https://schichtplan.vercel.app`
- `APP_BASE_URL` – the same origin; invitation links are built from it

**Frontend (Vercel).** Import the repo, set the root directory to `frontend`, and add one environment variable:

- `VITE_API_URL` – the deployed backend's URL, e.g. `https://schichtplan-api.onrender.com`

`frontend/vercel.json` already routes client-side paths back to `index.html`, so deep links like `/set-password?token=…` resolve instead of 404ing.

**Mail.** Add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM` to the backend service to send invitations for real. Without them the app still works — invitations are written to the service log instead of being sent. `backend/.env.example` lists every variable.

**First run.** Opening the deployed frontend lands on "Erstes Konto einrichten"; that first account is HR and sets its own password. Everyone after that is invited by email.

## Operations

**Gunicorn.** `render.yaml`'s `startCommand` runs `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60 --access-logfile -`, instead of Gunicorn's single-worker, single-thread default. The scheduler can run for up to `DEFAULT_TIME_BUDGET_SECONDS` (8s, `backend/scheduler.py`) computing a plan; a single synchronous worker would leave the API unresponsive to everyone else for that whole time. Two worker processes mean a second request can make real progress in parallel past Python's GIL while one worker is busy scheduling; the four threads per worker keep the rest of the API — which is mostly waiting on the database, not the CPU — responsive underneath. `--timeout 60` gives the scheduler room without leaving a genuinely stuck worker running forever. Each request opens its own database connection (`get_db()` in `backend/app.py`), so this setup caps concurrent connections at 8 (2 workers × 4 threads) — modest for Postgres, though the free plan's exact connection ceiling hasn't been checked against these numbers.

One consequence worth knowing: `init_db()` (`backend/db.py`) runs at import time and applies any pending migrations, so every Gunicorn worker does this independently on startup. That was already true with one worker; with two it means two processes can now start applying the same pending migration at close to the same time. Each migration runs in its own transaction (see `backend/migrations.py`), which narrows the window, but the race itself is a known, deferred issue, not something this change fixes.

**Migrations.** The schema updates automatically on startup (`init_db()` delegates to `migrations.apply_pending()`). Applied as of this stage: `0001_baseline`, `0002_indexes`, `0003_login_attempts`. To manage by hand:

```bash
cd backend
./venv/bin/python migrations.py status   # what's applied
./venv/bin/python migrations.py up       # apply anything pending
./venv/bin/python migrations.py down     # roll back the most recently applied one
```

**Backup.** Render's free Postgres plan is widely described as having no automated backups and being removed after a period of inactivity or age — but that has not been verified here against Render's current terms, so check the dashboard directly before relying on either claim. What holds regardless of the exact policy: don't treat a free-tier database as durable storage for schedules the organisation depends on, and a paid plan is a precondition for real operation, not an optional upgrade. Until that's in place, back up by hand — at least weekly:

```bash
pg_dump "$DATABASE_URL" --no-owner --format=custom --file="schichtplan-$(date +%Y-%m-%d).dump"
```

Restore:

```bash
pg_restore --clean --no-owner --dbname="$DATABASE_URL" schichtplan-2026-08-16.dump
```

**Environment variables.** Full list in `backend/.env.example`. Required in production:

| Variable | Without it |
|---|---|
| `SECRET_KEY` | The app refuses to start (`backend/security.py`) — it signs the session cookie and bearer token; a known key would let anyone forge a valid login |
| `DATABASE_URL` | Falls back to a local SQLite file on a filesystem that's wiped on every restart — every schedule would be lost |
| `ALLOWED_ORIGINS` | The frontend gets a CORS error on every call |
| `APP_BASE_URL` | Invitation links point at `localhost` |
| `FLASK_ENV=production` | No secure cookie flag, no HSTS header, and `SECRET_KEY` is no longer enforced |

`APP_TIMEZONE` (default `Europe/Berlin`) is not required — it decides which calendar month counts as "current" when an employee reports their own sick/vacation day; set it only if the deployment serves a different timezone.

**Troubleshooting.** Every unexpected error response carries a `request_id`; the same identifier is written to the server log next to the exception (`app.logger.exception` in `backend/app.py`). Search the Render service's log output for that id to find the underlying stack trace — the exact path through Render's current dashboard UI hasn't been verified here.

## API Endpoints

Everything except `/`, `/register`, `/login` and `/me` needs a signed-in session (`401` without one). Everything that changes data also needs the HR role (`403` for an employee account) — **except** the three `/employees/<id>/absences` routes, which an employee account may also call, but only for its own `<id>` and (for POST/DELETE) only for a date in the current calendar month; HR is unrestricted on both. Every route's error/success messages are returned in whichever language the `X-Lang` request header names (German if omitted or unrecognized — see [Language](#language)).

| Method | Route                          | Description                                              |
|--------|----------------------------------|------------------------------------------------------------|
| POST   | `/register`                     | Create the first HR account (sets its own password), or (as HR) add an account, which is invited by email |
| GET    | `/accounts`                     | List sign-in accounts (HR)                                          |
| DELETE | `/accounts/<id>`                | Delete an account (HR; not your own, not the last HR one)           |
| POST   | `/accounts/<id>/invitation`     | Send a fresh invitation to any account, revoking its password (HR)   |
| GET    | `/invitations/<token>`          | Public: is this invitation link still valid?                         |
| POST   | `/invitations/<token>`          | Public: the invitee sets their own password                          |
| POST   | `/login`                        | Sign in                                                      |
| POST   | `/logout`                       | Sign out                                                      |
| GET    | `/me`                           | Current user, or `401` with `setup_required` on a fresh install |
| GET    | `/employees`                    | List employees (with their constraints)                    |
| POST   | `/employees`                    | Create an employee                                          |
| GET    | `/employees/<id>`               | Get one employee                                             |
| PUT    | `/employees/<id>`                | Update an employee (replaces constraints)                    |
| DELETE | `/employees/<id>`                | Delete an employee                                            |
| GET    | `/employees/<id>/absences`      | List an employee's reported sick/vacation days `?year=&month=` (self or HR) |
| POST   | `/employees/<id>/absences`      | Report sick/vacation for one date `{date, type}`; frees any shift held that day (self, current month only, or HR, any date) |
| DELETE | `/employees/<id>/absences/<date>` | Cancel a report; restores the original shift if nobody has covered it yet (self, current month only, or HR, any date) |
| GET    | `/shift-types`                  | List shift types (with per-weekday requirements)              |
| POST   | `/shift-types`                  | Create a shift type                                            |
| PUT    | `/shift-types/<id>`               | Update a shift type                                             |
| DELETE | `/shift-types/<id>`               | Delete a shift type (blocked if used by an existing schedule)   |
| POST   | `/schedules/generate`            | Generate (or regenerate) a month's schedule `{year, month}`      |
| GET    | `/schedules/<year>/<month>`      | Get a month's schedule, its assignments, absences, and the workload distribution |
| DELETE | `/schedules/<year>/<month>`      | Delete a month's schedule                                           |
| PUT    | `/schedules/<year>/<month>/shift-times` | Change a shift's hours on one date; null times reset it to the shift type's |
| POST   | `/schedules/<year>/<month>/slots` | Add one more place to a shift on a single date                      |
| DELETE | `/assignments/<id>`               | Remove a place from a shift on one date                              |
| PUT    | `/assignments/<id>`               | Reassign one shift slot to a different employee (or `null`)          |
| POST   | `/assignments/swap`               | Swap the employees on two shift assignments `{assignment_id_a, assignment_id_b}` |
| GET    | `/assignments/<id>/replacement-suggestions` | Eligible employees for this slot, ranked by current workload (HR) |

## Status

Built and tested locally through v1.4: 23 unit tests, a benchmark against four alternative algorithms plus an exact solver, scripted end-to-end API walkthroughs (registration/invitation, weekly-hours and rest-period warnings across a month boundary, the full self-service-absence → replacement-suggestion → reassignment flow, and both languages), and a full browser walkthrough — including in English — of create → generate → reassign → swap → check balance. Frontend deployed on Vercel: [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/).

## About This Project

This is the "signature project" of a portfolio built while transitioning into web development — the most involved piece technically, centered on the scheduling algorithm rather than CRUD alone.

The part worth reading is `backend/scheduler.py` together with `backend/benchmark.py`: the benchmark is what turned the planned v1.2 heuristic from "obviously an improvement" into a measured tradeoff, and changed the design from a fixed ordering to an adaptive one.
