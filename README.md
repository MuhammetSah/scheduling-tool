# Schichtplan-Tool

**Live frontend:** [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/)

An automated shift-scheduling tool for HR teams, built with React (frontend) and Flask (backend). HR defines employees, their availability constraints, and shift types with staffing requirements; the tool generates a full monthly schedule via backtracking search and lets HR fine-tune the result by hand — including swapping shifts between employees.

It lives in its own repository and is the fourth project in a portfolio, after the portfolio website, a support-ticket system and a paused API-integration project.

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
- **Several people per shift** – how many people a weekday needs comes from the **coverage bands** (e.g. "Mon 08:00–12:00 → 2, 12:00–20:30 → 3"), not from the shift type. The planner turns those bands into blocks, fills each place separately, and the calendar lists everyone assigned. Head counts used to hang on the shift type; they moved to coverage bands in stage 3 and the planner stopped reading them in stage 4 (the table is gone since migration `0010`)
- **Day-level changes** – beyond the shift type's usual hours (e.g. 08:00–16:30), HR can change what a shift runs on one single date without touching any other day, and can add or remove a place on a given day. Changed hours are marked with `*` in both views and can be reset to the shift type's default in one click
- **Employee management** – name, optional email, optional monthly shift cap, an optional **weekly target-hours** figure for part-time staff, a **minimum rest period** between shifts (defaults to 11h, individually adjustable), an **availability mode** that is either unrestricted (`anytime`, the default — every employee's behaviour before this feature and after migration) or time-windowed (`windows` — available only inside specific weekday time slots, e.g. Mon–Fri 08:00–14:00; see [Availability windows](#availability-windows) below), recurring weekday unavailability (e.g. no Wednesdays), one-off unavailable dates (vacation/sick leave HR enters directly), and an optional allow-list restricting an employee to specific shift types (e.g. "only early shift"). Marking somebody **inactive** takes them out of future generation but deliberately leaves their existing assignments alone — silently emptying a published plan would rewrite a roster behind everyone's back and shorten the working-time record § 16 Abs. 2 ArbZG requires. What was missing was saying so: HR marked a leaver inactive, got a success message, and the person stayed on twenty shifts with nothing anywhere pointing at it. Saving now answers with how many shifts from today onwards they still hold, as a warning that stays on screen until dismissed
- **Shift type management** – a *template* and nothing more: name, start/end time, colour, and the certificates the shift requires. How many people are needed is a property of the day, not of the template, and lives in the coverage bands
- **Opening hours and coverage bands** – HR can set when the business is open, per weekday, with one-off date exceptions (a holiday, a special opening), and — independently — how many people should be present across the day in absolute headcount bands (e.g. "08:00–12:00 → 2, 12:00–17:00 → 3"), validated against those opening hours. A day's bands can be **copied onto other weekdays** — Mon–Fri with the same demand is the common case, and typing it five times is five chances to mistype it. See [Opening hours and coverage requirements](#opening-hours-and-coverage-requirements) below for what these do today, and — just as important — what they deliberately don't do yet
- **Automatic monthly schedule generation** via backtracking search, respecting weekly-hours caps and rest periods as hard constraints alongside the existing ones
- **Manual editing** – reassign any shift slot to a different employee (or leave it unfilled), optionally giving that one slot its own start/end times on top of whatever the date and shift type would otherwise resolve to (see [Individual assignment times](#individual-assignment-times) below), with non-blocking warnings if the change violates that employee's usual constraints — including a weekly-hours overrun, too little rest before/after the shift, or (for a `windows`-mode employee) a shift outside their availability windows for that day — all judged against the hours the slot actually runs, so HR can always override, but never by accident
- **Shift swapping** – pick two shifts and swap their assigned employees in one atomic action; an individual time set on either slot stays with the slot, not the person
- **Unfilled-slot reporting** – when there isn't enough eligible staff, the tool reports exactly how many/which slots couldn't be filled instead of failing silently or crashing
- **Workload distribution panel** – shifts per employee (and weekend shifts per employee) for the month, recomputed from what's actually saved, so it stays honest as HR edits the plan by hand
- **Coverage gap reporting** – the monthly schedule additionally reports where actual staffing falls short of the coverage bands above, computed against every assignment's actual resolved hours (see [Individual assignment times](#individual-assignment-times)) rather than a shift type's nominal ones
- **Self-service sick/vacation** – an employee can report their own sick or vacation days for the current month; a shift they were already assigned frees up automatically for HR to cover, and HR gets ranked replacement suggestions for it (see below)
- **Bilingual UI** – every label, message and validation error is available in German and English (see below)

## Certificates a shift requires

A shift can require a certificate — first aid, medication handling, a forklift licence — and only somebody who holds it gets scheduled on it.

**The interesting half is the expiry date.** The matching itself is a link table; what makes it hold up is `valid_until`. A first-aid certificate expires after two years (DGUV Vorschrift 1 § 26 asks for the refresher), a forklift licence likewise. **A certificate without an expiry is one the roster keeps honouring years after it ended** — the same fault availability windows already avoid with their validity bounds.

Three decisions follow, each with its own test: a missing date means *does not expire*, not *expired*; the bound is **inclusive**, matching how availability windows read "until", because two neighbouring rules that read it differently are a trap; and the date is normalised on the way in, not merely validated — `20261115` passes validation and then loses every string comparison, so the certificate would simply never run out.

**Hard in the generator, a warning on the manual path** — the split the rest of the tool uses. Two different messages, because they call for different things: "does not hold it" and "theirs expired on the 31st".

**Not a blocker for a swap.** Whether a given certificate is legally required or a house rule is something only the business knows, and refusing on that basis would assert it. The same restraint as with public holidays; `ARBZG_BLOCKERS` stays what its name says.

**The requirement lives on the shift type** and applies to everybody on it — "at least one first-aider per shift" would be a headcount inside a headcount and needs its own model. The price, said rather than discovered: a block **without** a template inherits nothing, and since block planning trims blocks free of any template, those carry no requirement. Hanging it on the coverage band instead would fix that and lose the unit HR actually names and recognises.

**The counterpart to per-employee shift restrictions:** those hang on the *person* ("Anna only works early shifts") and are an arrangement. A certificate requirement hangs on the *work* and says why. Both stay, because they mean different things.

**Deleting a certificate clears it everywhere**, and the confirmation says so — from everyone holding it and from every shift requiring it. A shift requiring something nobody can hold would be unstaffable forever.

## What is still missing

An empty database and an empty schedule look the same: "no plan has been generated for November yet." True, and useless on day one — it does not say what to do about it.

`GET /setup-status` reports what actually stands between an empty database and a usable plan, and the schedule page shows it **only while something is missing**. A panel that is always there is furniture; one that disappears is an answer.

**Only what genuinely prevents a plan.** Three things qualify: no active employee (every block would be a gap), no shift type (the route refuses outright), no coverage band (since block planning, that is the only thing the planner builds from). A list that also enumerated everything configurable would be a to-do list that never empties — and a list that never empties gets ignored.

**`notes` is the other kind:** worth knowing, prevents nothing. Without a federal state the tool knows no public holiday and stays silent about them; the plan still comes out. So it sits beside the list, not in it, and *ready* stays *ready*.

**The second note came out of planning a real month.** Weekly hours are optional on an employee, and an employee without them gets no weekly ceiling at all — the daily maximum and the rest period still apply, but nothing caps the week. Four employees created with the form's defaults and a full September produced weeks of 46.5 hours, and nothing anywhere said so. That is not a rule violation and must not hold a plan up, so it is a note: *N of M active employees have no weekly hours on file.* Exactly the shape the section above argues for — the tool telling you what it is about to do, rather than you finding out from the plan.

**Deliberately in neither:** the § 10 question. "Not exempt" is not a missing answer — it is exactly what § 9 Abs. 1 says. Listing it as a defect would declare the normal case a failing.

## Draft and published

`schedules.status` existed from the first commit: set to `generated` when a plan was built, written into the response — and read by nothing. **Every plan was visible the moment it was generated**, including the half-finished one HR was rebuilding for the third time.

It now carries two states. A **draft** is HR's business alone; a **published** plan is what employees see. `published_at` records since when, which is the question that comes first in any argument about a roster.

Two transitions are deliberately asymmetric:

- **Regenerating puts a published plan back to draft.** The plan HR released is not this plan any more — regenerating discards every manual correction, and it already requires a confirmation for that reason. Leaving it published would slip employees a different roster than the one they looked at.
- **A manual correction does not.** Swapping one assignment is ordinary running repair, not a new plan; forcing every correction through a withdraw-and-republish cycle would make publishing unusable.

For an employee a draft simply is not there — a `404`, but with its own message ("not published yet") rather than the existing one ("no plan generated yet"). That difference is the whole point: *there is nothing* and *it is not ready yet* are two different answers, and the page now shows the server's wording instead of its own.

The migration sets every existing plan to **published**, not draft. A migration must not change what people could see yesterday; the other direction would have made every live roster vanish until someone released it by hand, with no clue why.

Setting the state a plan already has is not an error — that is idempotent, and `published_at` stays put rather than moving, so pressing the button twice does not rewrite the answer to "since when?".

## The change log

`published_at` answers *since when* a plan has been visible. It does not answer *who released it*, or who swapped the assignment on the 3rd. In an argument about a roster that is the second question, and there was no answer.

The log records **requests, not narrative**: time, user, method, path, response status, for every request that is not a `GET`. One `after_request` hook, complete by construction, with no route left to forget.

**And deliberately without bodies.** A narrative log ("put Anna on the early shift") would read better, but its details would write sick notes a second time — and those are health data under Art. 9 GDPR. Storing them again is the operator's decision, not a technical one, so the log stops at *that* something changed and by whom. That is the price of the request-level design, and the honest half of the trade.

**Failed requests are recorded too.** A rejected attempt to change the roster is at least as interesting as a successful one; a log that only knows successes hides exactly the cases people open it for.

**No foreign key to `users`, and the username is copied alongside.** Accounts get deleted, and with `ON DELETE CASCADE` the log would go with them — a log whose entries can be removed by deleting the account is not a log. `user_id` stays as a bare number so related entries remain findable.

**It never breaks a request.** The write sits in a `try/except` that logs the failure and lets the response through; a log that turns an otherwise fine change into a `500` would fail first in exactly the moments when something is already wrong. Two implementation details earned their comments the hard way:

- The hook **rolls back before writing**, on the request's own connection. Without that, committing the log entry also commits whatever a half-failed request left pending — an existing test caught it when an invalid employee suddenly persisted.
- The obvious alternative, a connection of its own per request, is more decoupled but doubled the test suite's runtime (68 to 134 seconds) and would mean an extra Postgres connection for every write against an instance with a limited supply.

There is **no route to clear it**. Something that empties at the press of a button is not a log. What the log does have is a *period*: it is personal data, so entries fall away with the retention clean-up described under [Data protection](#data-protection) — six months by default. That is deletion by rule, not by button.

## Exports

Two, and both without a new dependency.

**iCal** (`GET /employees/<id>/schedule.ics?year=&month=`) — one employee's shifts for a month, for their phone's calendar. Self-or-HR, the same rule the absences and availability windows follow. **Published plans only, HR included**: a draft does not exist for employees, and an export that handed one out anyway would be the back door beside that wall. The point is not who fetches the file — it is that the file leaves the building.

**CSV** (`GET /schedules/<year>/<month>/export.csv`, HR) — the whole month, for payroll or a spreadsheet, unfilled slots included with an empty name because leaving them out would make a gap disappear. Drafts *are* exported here, and the difference is the recipient: HR pulls this for itself, and exporting a draft to check it over is a sensible thing to do.

**Why no PDF or Excel.** The roadmap named them. Each needs a library, and this project keeps five runtime dependencies and wrote its own i18n, migration runner and holiday calendar rather than adding more. iCal is a text format ([RFC 5545](https://datatracker.ietf.org/doc/html/rfc5545)) and about forty lines for what is needed here; `csv` is in the standard library. PDF and Excel can wait until someone actually asks — then it is a decision with an occasion rather than one taken on spec, and anyone who wants a table can open the CSV in one.

Three details that decide whether an export works at all:

- **iCal uses CRLF line endings**, as the RFC requires. Some calendars reject the file silently otherwise — no error, just no events.
- **The CSV uses semicolons and a BOM.** Both for Excel in German-speaking locales: without the semicolon everything lands in one column, without the BOM umlauts turn to mojibake. Inelegant and correct — an export that will not open in its target program is not an export.
- **The download goes through an authenticated `fetch`, not a plain link.** The frontend and this API are on different domains, so a click on an `<a href>` would carry neither the bearer token nor, under Safari's ITP, the session cookie — and the file would come back as a `401`, or worse as an HTML error page saved under a `.ics` name.

**The break belongs in both files, and used to be in neither.** Both exports showed only a break somebody had entered by hand, on the reasoning that the statutory one would be the same number on every row. It is not: § 4 makes it a function of the span, so the same day carries a 30-minute break on an 8½-hour block and none on the four-hour one beside it. In the CSV that left a blank break column next to a working-time column that had already subtracted it — 08:00, 16:30, blank, 8.0, with half an hour unaccounted for in a document somebody reconciles against payroll. Both now carry the break that actually applies; a hand-entered one still wins over it.

**The CSV header follows the request language.** It was a German constant in `exports.py` while the weekday names beside it were already translated, so an English-speaking HR user got `Datum;Wochentag` with `Tuesday` underneath. A bilingual tool that ships its only printout in one language is monolingual at the point where it leaves the building.

**The calendar is named after the month it holds** (`Schichtplan September 2026`). It used to reuse the same fallback label a block without a template gets, so a subscribed roster showed up on the phone as, simply, "Dienst". Two purposes, two strings.

**No time zone in the iCal file.** The tool works in local time throughout and stores no zone; inventing one would be a claim the data does not support. A calendar in a different zone will therefore shift the events, which is stated here rather than left to be discovered.

## Data protection

Two decisions came from the operator: **six months** of retention, and erasure by **anonymisation**. Both shape what follows.

### Six months, and what they cannot cover

The period deliberately does **not** touch assignments or schedules. [§ 16 Abs. 2 ArbZG](https://www.gesetze-im-internet.de/arbzg/__16.html) requires the employer to record working time beyond eight hours a day, and "die Nachweise sind mindestens zwei Jahre aufzubewahren". Deleting a month with ten-hour days after six would be breaking one rule in order to keep another.

What the period does cover is everything personal *around* that record: sick and holiday reports, and the change-log entries.

**The one that gets missed:** an absence is stored in `employee_absences` *and* denormalised into the assignment it freed (`absence_type`, `absent_employee_id`). Clearing only the table would leave the health note sitting in the roster. Both are purged, and a test pins it.

There is **no scheduler** on the hosting plan in use, and the purge used to run only at application start — in practice on every deploy — plus on demand through `POST /retention/purge`.

**That was not enough, and the keepalive job is why.** A GitHub Actions workflow pings the API every fourteen minutes so the free plan never spins down, which means the process can stay up for weeks and a deploy can be just as far away. In between, nothing expired. A retention period that only runs when somebody remembers a button is not a retention period, and what it was failing to remove are sick notes — health data under Art. 9 GDPR.

The purge now runs **once a day, triggered by the first request of that day** (`run_daily_retention_purge()`). No scheduler is needed for that and none is pretended: the date of the last run lives in a row of the `settings` table, and whoever sets it to today first — decided by a single conditional `UPDATE`, so two processes cannot both win — does the work. After that the process short-circuits on a module-level date and the check costs no query at all. A failure is logged and swallowed: a clean-up that breaks somebody's roster edit would be worse than one that runs a day late, the same call the audit log makes.

That row is deliberately not one of `KNOWN_SETTINGS` and is filtered out of `GET /settings` — it is the tool's bookkeeping about itself, not a setting anybody chooses.

`POST /retention/purge` stays, because "run it now and tell me what went" is a different question from "does it run at all" — and it is the one somebody asks right after changing the period.

### Deleting a person means anonymising the row

`ON DELETE SET NULL` used to turn a deleted person's past shifts into unfilled ones. That is worse than it sounds: the past reads as understaffed, coverage gaps appear retroactively, and the working-time record § 16 requires loses the very attribution that makes it one.

Instead the employee row becomes a tombstone — name replaced, email gone, inactive, and everything personal beside it (availability windows, blocked dates and their reasons, absences, allowed shift types, certificates) removed. **That list is the place where forgetting lives**: a later stage added certificates and did not add them here, and a tombstone still holding a first-aid certificate is exactly what anonymisation is for. Any new table about a person belongs on it. **Including the absence reason denormalised into the roster**: the same two places the retention purge has to visit, for the same reason. Clearing only `employee_absences` would leave a health note with the person still attached to it, sitting in the schedule until the retention period caught it months later. The assignments stay exactly where they are and keep pointing at that row. Anonymised rows are hidden from the employee list: they are records, not staff.

**Why that satisfies Art. 17:** paragraph 3 lit. b exempts processing needed to comply with a legal obligation, and § 16 Abs. 2 ArbZG is one. What stays is the working-time record without a person; what goes is the person. `DELETE /employees/<id>` keeps its name and changes its meaning — and says so in its response, because a route that does something other than its verb promises should at least admit it.

### Access

`GET /employees/<id>/data-export`, self-or-HR, returns everything the tool knows about one person as JSON: master data, constraints, windows, absences, assignments with hours, the linked account, and that account's log entries. **Never the password hash** — the one field whose disclosure would make the export itself a security problem, and a test says so.

JSON rather than PDF: Art. 15 Abs. 3 asks for a commonly used electronic format, JSON is one, and the alternative would be a dependency bought for the sake of looking like paper.

## Login throttling

Ten failed attempts in fifteen minutes, then a 429 — high enough that a mistyping human never hits it, low enough that guessing is useless.

**Per username, not per IP.** An IP block catches every colleague behind a shared office connection, and an attacker with rotating addresses walks around it. The lockout also blocks the *correct* password while it lasts: a brake that lets the right answer through is no brake at all.

### The two ways past it, both now closed

**An invited account was free.** An account created by invitation has no password yet, and saying so plainly is a deliberate trade — the invitation went to that person's mailbox, and "wrong password" helps nobody who never set one. But that reply also confirms the username exists, unlike the identical message every other path returns, and the branch returned before recording anything. Unlimited, uncounted: a name list at no cost. The attempt is now counted like any other, so the branch runs out with everything else.

**Checking and counting were two steps.** `is_locked_out()` reads a counter that `record_attempt()` raises a moment later. Two simultaneous requests both read the same below-the-limit count and both get through — ten attempts per quarter hour becomes as many as the attacker opens connections, and the throttle stops being a limit and becomes a suggestion.

Both now happen inside a per-username Postgres advisory lock (`security.attempt_guard()`), following the same pattern the migration runner already uses. **Per username, not global** — a global lock would queue every login in the building behind every other one, and there is a counter-test for exactly that.

**Deliberately asymmetric: no lock on SQLite.** SQLite appears in this project only locally and only as a single process, so the race is not reachable there, and a lock without a reachable race is untested code on the path every developer uses daily. The same reasoning the migration runner records.

The race is not asserted by argument but reproduced: two threads, each with its own connection and therefore its own Postgres session, with half a second between reading and writing so the race happens every time rather than occasionally. A flaky concurrency test is worse than none.

## Revoking a sign-in

There are two credentials, not one. The session cookie is the ordinary one; alongside it sits a signed, stateless bearer token, because Safari/WebKit's Intelligent Tracking Prevention drops a cross-site cookie however correctly it is configured, and the frontend and this API live on two different domains. A header is not a cookie, so ITP has no opinion about it.

**Stateless meant unrevocable, and that was a hole rather than a tradeoff.** "Passwort zurücksetzen" on the Konten page empties `users.hash`, so the old password stops working immediately — and until now the token minted with that password kept authenticating every request for the rest of its thirty days. The one situation the button exists for is the one it did nothing about: a phone gone missing, somebody who has left. HR pressed it, saw a success message, and the old session went on reading the roster.

`users.token_epoch` (migration `0018`) closes it without a session table. The counter is signed into the token and compared against the column on every request; incrementing the column invalidates every token that account has out, in one statement. It is incremented in exactly the two places where the password stops being the one its holder knows: redeeming an invitation, and re-inviting.

**The cookie carries the same counter.** A rule that held on one of two sign-in paths and not the other would be the gap this change exists to close.

**A token issued before the migration reads as epoch 0,** which is the column's default, so deploying this signs nobody out. Only the next reset does — which is the point. A security fix that arrives as an outage teaches people to postpone security fixes.

**What this is still not.** Signing out is per device: it clears the cookie and discards this browser's copy of the token, and does not touch the account's other sessions. Ending *every* session is what the reset does, deliberately — "sign out here" and "lock everybody out" are different requests, and only one of them belongs on a logout button.

## The guided swap

Swapping already existed, but only through HR and only immediately: click two cells, done, warnings afterwards. Anyone who wanted to swap had to ask somebody else to do it for them.

Three steps now, and each one carries weight. The requester offers a shift **of their own** and names a colleague; the partner agrees and picks which of **their** shifts goes back; HR approves. Only then does the roster move.

### When a swap is refused rather than flagged

A swap is the only operation in this tool that changes the load on **two** people at once, and the same check runs for both. But not every finding weighs the same, and the line runs along one question: is this compulsory law, or is it a house rule?

Refused: the eleven hours of [§ 5 Abs. 1](https://www.gesetze-im-internet.de/arbzg/__5.html), the daily ceiling of § 3, the breaks of § 4, the seventh consecutive day, the yearly Sunday budget of § 11 Abs. 1 — and overlapping blocks, which are not law but physics.

Flagged and passed on to HR: a blocked weekday, an availability window, a weekly-hours target, a monthly cap. Real reasons to hesitate, none of them something the state insists on.

**Why refuse at all.** [§ 22 Abs. 1 ArbZG](https://www.gesetze-im-internet.de/arbzg/__22.html) makes a breach an administrative offence *for the employer*, and §§ 3 and 5 cannot be waived by individual agreement — only under § 7 by collective agreement, which this tool does not model. Two colleagues arranging an unlawful swap between themselves and handing HR the finished fact would move a liability the law puts on the employer into a process nobody supervises.

**Why HR's own manual swap still only warns.** They carry the responsibility, and they may know something the tool does not — an emergency under § 14, a collective agreement under § 7. Putting the same bolt across their door would take away the decision they are answerable for.

**Why a Sunday or a public holiday does not refuse**, even once the § 10 question has been answered. The setting's default is *not exempt* — a safe assumption for deciding what to report, but not a statement the operator has made. Refusing a swap on an assumption is a different thing from refusing it on a fact, and only the second is what the rest of this list rests on.

### Why the request names a person, not one of their shifts

An employee sees only their own shifts (see [Draft and published](#draft-and-published)). Letting the requester pick the other half would mean showing them everybody else's roster first — undoing a deliberate decision for the sake of a secondary one.

So the request names a colleague, and the partner picks what they give in return. They know best which of their shifts they can spare, and it makes their consent substantive rather than a rubber stamp. `GET /colleagues` returns the smallest disclosure that makes this possible: **who works here, and nothing about when.**

### Checked in the state the swap would create

The swap is carried out and *then* examined; a request that was only asking rolls the transaction back. Judging beforehand judges the wrong state — checking the partner against the requester's date while they still hold their own shift counts a block that is about to leave their hands, and two shifts on neighbouring days would report a rest-period breach the swap actually resolves. There is a test for that, and it goes red if the order is reversed.

Checked **twice**: once when the partner accepts, once when HR approves. Days pass in between, and whoever checks only once approves a swap that has since become unlawful — with the earlier check sitting in the file as proof that everything was examined.

And days change more than the law. If HR reassigns one of the two shifts by hand in the meantime, approving would swap whoever stands there *now* — a swap nobody agreed to, with an acceptance on file that appears to cover it. So approval first checks that both slots still hold the people who consented.

### Deliberately absent

**No free-text reason.** A "why do you want to swap" box collects "doctor's appointment" and "my mother is in hospital" — health data under Art. 9 GDPR, in a table with no retention rule of its own. The change log refuses request bodies for the same reason.

**No swap board.** Appealing, but it shows everyone everybody's shifts — the same rollback of data minimisation, merely volunteered.

**Nothing about works-council co-determination** (§ 87 Abs. 1 Nr. 2 BetrVG). Whether and when a works council has a say in distributing working time depends on the business and on existing agreements. That is not a question a tool may answer.

## Self-service sick / vacation

The one deliberate, narrow exception to "employee accounts are read-only": a signed-in employee can report their own sick or vacation days, but only for the current calendar month (checked against the server's own clock, never anything the browser sends). HR can do the same for any employee, any date, from the schedule table.

**The date picker's bounds were wrong east of Greenwich, which is to say here.** They were built with `toISOString()` on a local-midnight `Date`, and that converts to UTC: in Berlin the first of the month came out as the last day of the *previous* one, and the last day of the month fell outside the range entirely. So the picker offered a date the server refuses and refused a date the server accepts — **reporting sick on the last day of the month was simply not possible through the form.** Invisible on a machine running in UTC, which is why the regression test pins `TZ=Europe/Berlin` rather than trusting the runner: in UTC the broken version passes. `pages/Employees.jsx` already had the right pattern (`toLocaleDateString('sv-SE')`) and a comment explaining why; this is what it looks like when that lesson does not travel.

**The panel says why it is gone.** It only appears while the current month is on screen, because the server restricts self-service to that month anyway. Browsing forward used to make it vanish without a word, which reads as a page fault rather than a rule; in its place there is now a line saying what the limit is, and a button back to the current month.

Reporting an absence for a day the employee already holds a shift on:

- **frees the shift** – it goes back to being an ordinary unfilled slot (counted in `unfilled_count`, shown in the distribution panel, reassignable from the usual dropdown)
- **keeps the context** – HR sees "Krank (war: Anna)" / "Sick (was: Anna)" instead of a bare gap, so it's clear why the slot opened up and who to ask about it
- **still shows on the employee's own calendar** – as "Krank"/"Sick" or "Urlaub"/"Vacation", not as a normal shift, even though the slot itself no longer has their name on it
- **feeds back into the scheduler** – a later regeneration of that month won't reassign the same person straight back onto a day they reported as unavailable

HR gets a **"Vorschläge"/"Suggestions"** action on any freed slot: it re-runs the same eligibility checks used for manual reassignment (weekday/date availability, availability windows for `windows`-mode employees, allowed shift types, not already working that day, monthly cap, weekly-hours cap, rest period) against every active employee and ranks the eligible ones by current workload, so the least-loaded suitable person is offered first. Picking one is a normal reassignment — nothing special has to be undone if it turns out to be wrong.

## When the interface itself goes wrong

Two failure modes that belong to the frontend rather than to any feature.

**A component that throws used to take the whole page.** React unmounts the entire tree on an uncaught render error, and with nothing catching it the result is a blank white page: no message, no navigation, no hint that reloading would help. For an employee checking tomorrow's shift on a phone that is indistinguishable from the tool being gone. `ErrorBoundary.jsx` now wraps the routes — inside the navigation, so the header and language toggle survive — and offers a message, a retry, and a way back to the schedule. It is keyed on the path, so navigating away clears it instead of leaving one page's error standing over another. Its text is hard-coded in both languages rather than translated, because it has to render even when the thing that broke *is* the language context.

**Error messages disappeared before they could be read.** Every flash message was cleared after four seconds, including "this swap would fall below the rest period". Look away at the wrong moment and all that is left is a button that appeared to do nothing, with no way to find out why — the swap page had already grown its own exception for exactly this, which was the finding showing up in the wrong place. Successes still fade (they only confirm what you asked for); errors and warnings now stay until dismissed, and there is a close button, which there previously was not — `onClose` existed and only the timer ever called it. They also carry `role="alert"` / `role="status"`: a `div` appearing mid-tree is an event to the eye and nothing at all to a screen reader.

## Language

The UI is available in German (default) and English, toggled from the navbar; the choice is remembered per browser (`localStorage`) and sent to the backend on every request via an `X-Lang` header, so validation errors and the non-blocking constraint warnings above come back in the same language as the rest of the page — not just the static labels. Adding a third language means extending `backend/i18n.py`'s translation table and `frontend/src/i18n/translations.js` the same way; both are hand-rolled (no `react-i18next`/`Flask-Babel`) to keep the near-zero-dependency footprint the rest of the project has.

## The scheduling algorithm

`backend/scheduler.py` assigns employees to shifts via **chronological backtracking with branch-and-bound**, not a greedy pass.

A greedy algorithm assigns the first workable candidate to each slot and never reconsiders. That can leave avoidable gaps: if employee A is the only one who can cover a later shift, but a greedy pass already spent them on an earlier shift that someone else could equally have covered, the later shift ends up unfilled for no good reason.

This algorithm instead explores assignments slot by slot in calendar order, and **undoes (backtracks) a choice** whenever it turns out to block a later slot with no other eligible candidate. It keeps searching after finding one complete assignment, in case a different set of choices leaves fewer slots unfilled (branch-and-bound: a running best-so-far result prunes any branch that can't beat it, and search stops early once a fully-staffed solution is found). A node/time budget acts as a safety valve on pathologically understaffed inputs, so a request always returns a best-effort result instead of hanging.

Hard constraints enforced during search: an employee can't work two blocks that **overlap** on the same day (two blocks either side of a break are allowed — see [Split shifts and working-time law](#split-shifts-and-working-time-law)), can't exceed their maximum daily working time, can't be scheduled on a weekday/date they're marked unavailable, can't be scheduled outside their availability windows (if in `windows` mode — see [Availability windows](#availability-windows)), can't be scheduled outside their allowed shift types (if restricted), can't exceed their monthly shift cap (if set), can't exceed their weekly target hours (if set — see [Part-time / weekly hours](#part-time--weekly-hours)), and can't be left with less than their minimum rest period against the shift immediately before or after (see [Rest periods](#rest-periods)), can't work more than six days in a row, and can't be given a Sunday once their yearly budget of them is spent (both see [Rest days and free Sundays](#rest-days-and-free-sundays)).

`backend/test_scheduler.py` includes a test that constructs a scenario where a literal greedy-first-fit pass provably leaves gaps that this algorithm closes, alongside tests for each hard constraint and for graceful degradation when there isn't enough staff to fill every slot.

### Part-time / weekly hours

An employee can carry an optional `weekly_hours` target (e.g. "works 30h/week") instead of only the existing monthly shift-count cap. It's enforced as a hard ceiling in minutes over each Monday–Sunday week: once assigning another shift would push the employee past their target for that week, they stop being eligible for further shifts *that week* — which, combined with the existing one-shift-per-day rule, is what spreads a part-timer's hours across several distinct days each week rather than letting them bunch onto a few long ones. It's a ceiling and a best-effort target, not a guaranteed minimum — same "report gaps rather than force an answer" philosophy the rest of the scheduler already has for `max_shifts_per_month`.

This cap and the rest-period check below **used to** stop at the edge of the generated month, because the search only ever sees one month's slots at a time. They no longer do — see [Across the month boundary](#across-the-month-boundary). What remains scoped to the month is `max_shifts_per_month`, and that one is a monthly quota by definition.

### Rest periods

Every employee has a `min_rest_hours` setting (defaults to 11h, the German ArbZG minimum, individually editable per employee). During generation this is a hard constraint: the search won't assign a shift that would leave less than that much rest against the employee's own shift the day before or after — including across midnight, e.g. a 22:00–06:00 shift followed by an 08:00 shift the same "next day" is only 2h apart even though the two are different shift types on different dates.

Manual reassignment and swapping only ever produce a **non-blocking warning** for this (exactly like every other constraint already works) — the violation is scoped to that one employee's one shift, so HR can fix it by hand while everyone else's shift that day is completely unaffected.

### Availability windows

By default (`availability_mode = 'anytime'`) an employee has no time-of-day restriction at all — only the weekday/date unavailability above applies, exactly as before this feature existed, and every employee already in the system keeps this behaviour unchanged after upgrading. Switching an employee to `windows` mode flips the meaning: they become available **only** inside the time windows entered for them, and a weekday with no window at all means unavailable that entire day. Windows **add to** the weekday/date unavailability, they don't replace it: both are checked unconditionally and *before* the mode-dependent window check, so they can only ever forbid, never allow — an employee marked "never Wednesdays" stays unschedulable on Wednesdays even with a Wednesday window entered (which is why the employee form keeps that picker visible in `windows` mode instead of hiding it). The mode is a deliberate, explicit switch rather than something inferred from whether windows exist, because "no windows entered" would otherwise be ambiguous — available all day, or available never? Making HR pick a mode removes that ambiguity instead of guessing at it.

A window is `{weekday, start_time, end_time, valid_from, valid_until}` (weekday `0` = Monday … `6` = Sunday, times as `"HH:MM"`). `end_time <= start_time` crosses midnight the same way shift hours do (see [Rest periods](#rest-periods) above) — `20:00`–`06:00` is a valid night window. `valid_from`/`valid_until` are optional and inclusive, for cases like "this changes from September onward". An employee can hold several windows on the same weekday — e.g. a split shift covered by `08:00–12:00` and `16:00–20:00`.

A shift is only allowed for a `windows`-mode employee if it fits **entirely inside a single window** — not "overlaps a window", and not "falls inside the union of several windows" of theirs that day. With the two windows above, a shift running `11:00–17:00` is **not** allowed, even though the two windows together would cover it end to end: the model has no notion of partial coverage yet, and a shift is one indivisible block — whoever takes it works all of it. Treating "overlaps" as good enough would mean putting someone on a shift they can only partly cover and quietly calling that a success. "Fully contained" stays the condition for placing someone on an existing block. What the generator does instead, since the block-planning stage, is cut the block itself down to what the window covers, so the person can take the part they are available for and the remainder is reported as a gap — see [Block planning and automatic trimming](#block-planning-and-automatic-trimming). The weekday that decides which windows apply is always the one the shift *starts* on, including for a night shift.

Availability windows are a **hard constraint** during automatic generation, exactly like weekday/date unavailability: the search never assigns a `windows`-mode employee to a shift that doesn't fit inside one of their valid windows for that day, and a slot nobody else can take is reported unfilled rather than staffed by force. A manual reassignment by HR follows the project's usual rule instead: it goes through and saves (HTTP 200), coming back only with a non-blocking warning naming the employee's applicable windows for that day (or noting there are none) — HR stays free to override it on purpose.

### Individual assignment times

A shift's actual hours are resolved in three layers, checked in this order: the assignment's own `start_time`/`end_time` on `shift_assignments`, if set; otherwise a per-date override for the shift type (the **Day-level changes** feature above), which applies to everyone assigned to that shift on that date; otherwise the shift type's usual hours. Three layers, not two, because the middle and top ones answer different questions that both come up in practice: "the early shift ends earlier today" is a statement about the shift, true for everyone on it, while "Ben works 10:00–16:00 today" is a statement about Ben's one slot and nobody else's. Collapsing them into a single override would make it impossible to say one without accidentally also saying the other for whoever else happens to be on that shift that day.

Every check that reasons about actual clock time — the weekly-hours cap, the rest-period warning, and the availability-window check above — resolves an assignment's hours through this same three-layer rule (`assignment_hours()` in `backend/app.py`) rather than reading the shift type directly, so a person working a personally-shortened or personally-lengthened shift is judged against the hours they actually work. This only affects the manual-edit warning path: the automatic generator never sets an assignment's own times or a date override, so a freshly generated plan always runs on layer three, exactly as before this feature existed. Both new columns are either set together or left `NULL` together — a half-filled pair is rejected with `400`, and so is a pair with equal start and end times, which the project's midnight convention (`end <= start` means "runs past midnight") would otherwise silently turn into a 24-hour shift.

A slot can also exist with no shift type behind it at all (`shift_assignments.shift_type_id` is nullable) — a block that is not an instance of any template. It must carry its own start/end times, because it has no shift type and no date override to fall back to; the API rejects a template-less block that doesn't bring its own times. It shows up in both views without a template color — its own last column in the table view once the month has at least one, a neutrally-colored entry in the calendar view — and a shift-type restriction on an employee has nothing to say about it, so it never triggers that particular warning. The generator creates these routinely since the block-planning stage: demand that no template covers becomes exactly such a block. There is still deliberately no button for HR to add one by hand. Having the data model land a stage ahead of the algorithm is what kept the schema change and the scheduling change out of the same step.

### Opening hours and coverage requirements

Two concepts frame the demand the generator plans from — and since this stage they **are** what it plans from. `build_slots()` in `backend/scheduler.py` no longer runs on the generating path: `block_planner.build_month_blocks()` builds the month's blocks out of `coverage_requirements`, and the per-weekday counts on `shift_requirements` are not read at all any more (see [Block planning and automatic trimming](#block-planning-and-automatic-trimming)). The table itself is gone since migration `0010`. `build_slots()` stays, off any production path, as the comparison basis `benchmark.py` measures against and as what the 23 backward-compatibility tests in `test_scheduler.py` exercise — its per-weekday counts have to be handed in through `shift_types` now. Opening hours frame the generator too now, not just the gap report: a date closed by an exception produces no blocks, and every band is trimmed to that date's effective opening window before anything is planned against it.

**Opening hours.** `business_hours` holds exactly one row per weekday (`UNIQUE(weekday)` enforces it); `business_hours_exceptions` overrides a single date (a holiday, a special opening) and takes precedence over the weekday rule wherever both are consulted — that precedence is decided in exactly one place, `business_hours_for()` in `backend/app.py`, a pure function over already-loaded rows that every reader goes through. The migration that creates the table (`0006_coverage.py`) seeds all seven weekdays with `open_time`/`close_time` = `00:00`/`00:00` and `closed = 0` — under the project's midnight convention (`end_time <= start_time` means "runs past midnight", the same rule shift hours and availability windows already use) that reads as *open the entire day*. It's the only default in this feature that changes no existing behaviour: before this stage there were no opening hours at all, so introducing them must not forbid anything that was previously allowed. Opening hours are both a **validation boundary and, since this stage, a planning boundary** — they limit which coverage bands HR is allowed to save (in both directions: opening hours that would invalidate a band already saved are rejected too, naming the weekday and the band, so narrowing a day can never strand a stock the coverage editor then refuses to take back) and frame how they're displayed, and they bound what the generator plans, via the effective per-date window every band is trimmed to. They still never block an existing assignment and never produce a warning: nothing checks a manually-edited shift against them.

**Coverage bands.** `coverage_requirements` describes, per weekday, how many people should be present during a given stretch of the day — "08:00–12:00 → 2, 12:00–17:00 → 3". The count is **absolute headcount, not additive**: between 12:00 and 17:00 the business needs *three* people total, not 2+3=5. Bands of the same weekday may not overlap (rejected with `400`), must lie entirely inside that weekday's opening hours (`400` as well — `band_within()` in `backend/coverage_model.py`). That containment check reads the *closed* stretch of the day rather than the open one: a band is inside the opening hours exactly when it does not touch the time between closing and the next opening. The straight comparison used for [availability windows](#availability-windows) (`scheduler.window_contains_shift()`, which `band_within()` delegated to until it turned out to be wrong here) cannot answer this once a band crosses midnight — a `22:00–06:00` band is minutes `[1320, 1800)` while the all-day default `00:00–00:00` is `[0, 1440)`, so containment fails on an axis that is really a ring. Read through the closed stretch it resolves: on an all-day opening that stretch is empty, and an empty stretch can intersect nothing. Nothing legitimate is loosened by this — under a real `08:00–18:00` opening, a `07:00–12:00` band is still rejected, because the ring only dissolves the midnight crossing, and `required_count` may not be negative. Gaps between bands are allowed and mean "no requirement" for that stretch. The boundary between adjacent bands is **half-open**: `08:00–12:00` and `12:00–16:00` only touch and are both accepted — they are not treated as overlapping.

Coverage bands were derived **once**, at migration time (`0007_derive_coverage.py`), from the existing `shift_requirements` demand: for every weekday, at every point in time, the sum of `required_count` across the shift types covering it, with adjacent equal sums merged into one band (`coverage_curve()` in `backend/coverage_model.py`, an event-point sweep over the day's minute axis). After that one-time derivation, bands are maintained by hand through `PUT /coverage-requirements`. There was deliberately **no automatic recomputation** when `shift_requirements` changed afterwards — keeping two sources of truth in sync automatically would have meant them quietly overwriting each other — and since migration `0010` there is only the one source left.

**Coverage gaps.** `GET /schedules/<year>/<month>` additionally returns `coverage_gaps`: stretches of a date where fewer people are actually assigned than that day's coverage bands call for. This is computed against the **actual, resolved** hours of each assignment — the same three-layer resolution [individual assignment times](#individual-assignment-times) already established — so a shift someone personally starts later than usual shows the gap where it really is, not where the shift type's nominal hours would put it. An unfilled slot and one an absence just freed both contribute nothing to coverage (both leave `employee_id` `NULL`). Adjacent stretches with the same missing count are merged, over-coverage produces no entry, and a date closed by an exception has no demand and therefore no gap. Every band is first trimmed to the **effective** opening window of its date — the one `business_hours_for()` resolves, so an exception's own times count, not merely its closed flag, and a special opening genuinely narrows or widens that date's reported demand. A band trimmed away entirely produces no gap. Trimming is what keeps bands older than the current opening hours from demanding staff for a closed business: `0007_derive_coverage.py` writes derived bands straight past the API, and any database edited before `PUT /business-hours` began cross-checking can hold the same mismatch. The obvious N+1-per-day query trap is avoided deliberately: `coverage_gaps_for_month()` loads `coverage_requirements`, `business_hours` and the month's `business_hours_exceptions` in three queries total (eight in the whole `GET`), and `business_hours_for()` is a pure function over those three results — it takes the loaded dicts rather than a cursor, so calling it once per date of the month adds no query at all.

**Known limitation: overlap across a weekday boundary is not checked.** A Monday `22:00–06:00` band and a Tuesday `00:00–08:00` band are both accepted (verified over the API, under the all-day default opening hours — see `test_nachtband_wird_unter_ganztaegiger_oeffnung_akzeptiert` in `backend/test_api_coverage.py`). Read consistently under this project's start-anchored convention they don't even describe the same time: the Monday band's night shift ends early Tuesday morning, while the Tuesday band sits on Tuesday morning proper. A real conflict would only appear once the week is treated as a 10080-minute ring across its own weekly repetition — catching that is possible, but at the cost of error messages nobody could read at a glance, so it's left as a documented limitation instead of built here.

### Block planning and automatic trimming

The generator runs in **two stages**. Stage 1 (`backend/block_planner.py`) decides *which blocks a day must have*; stage 2 (the backtracking search above) decides *who works them*. The search core itself is unchanged in structure, objective and safety valve — stage 1 simply hands it a slot list built from the demand bands instead of from the per-weekday counts the tool used to keep.

**Stage 1, step by step.** Working from the earliest point of the day where demand is still open: if a shift type starts exactly there and runs entirely inside open demand, the longest such template is used — that is the normal case, and it is what makes a plain month still look like "3 early, 2 late". Otherwise a block is cut to reach as far right as the demand holds, capped at ten hours (§ 3 ArbZG — a longer block could not lawfully be worked by anyone, so it would become one big gap instead of workable pieces). Ties are broken by shift-type id and by start time so the same input always produces the same plan.

A template is only used when demand is open across its *whole* run. A `06:00–14:00` template against a `08:00–14:00` band is not used, because the two hours before nobody asked for: planning too little is the harmless direction, planning too much costs money and appears in no band.

**Why not "pick the template that covers the most demand".** That weighting (count × duration) is the obvious one and it is wrong: it covers the peak first and strands the shoulder. Demand of 2 people `06:00–08:00` and 3 people `08:00–14:00` comes out as three `08:00–14:00` blocks plus two `06:00–08:00` blocks — five people, and two two-hour blocks nobody wants to work. Read from the left it is two `06:00–14:00` blocks plus one `08:00–14:00`: three people, which is also the minimum, since no solution can go below the highest point of the demand curve.

**Trimming.** Once the blocks exist, stage 1 assigns them *provisionally* — cheaply, one day at a time, scarcest block first and within it the person with the fewest alternatives (the same minimum-remaining-values heuristic `order_slots()` uses). Any block nobody can carry is cut to the largest overlap with somebody's availability window; the uncovered remainder goes back into the queue as its own block, and a remainder shorter than `MIN_BLOCK_MINUTES` (180) is simply not created and becomes a reported gap instead of a sliver nobody would work. **The provisional assignment is then thrown away** — it existed only to decide the shapes. Who actually works each block is decided by stage 2, month-wide and fairly.

The provisional pass is what makes trimming correct under competition. A static test ("can *anyone* cover this block in full?") knows nothing about contention: with three places at `06:00–14:00`, two unrestricted people and one whose window is `08:00–14:00`, it answers "yes, coverable" and leaves the third place empty — where a trim would have filled six of its eight hours. `benchmark.py` measures exactly this case: the old path leaves 31 places empty over a month, the new one leaves none.

Blocks with no matching template carry `shift_type_id = NULL` and show up under a neutral "Dienst"/"Shift" heading.

### Split shifts and working-time law

Until this stage nobody could work twice in a day, which made the split shift — `08:00–12:00` **and** `16:00–20:00`, the very example the availability-window feature was designed around — impossible to plan. It is allowed now, bounded by three rules taken from the Arbeitszeitgesetz:

| | |
|---|---|
| **Blocks may not overlap** | Nobody can be in two places at once. Half-open boundaries as everywhere else in this project: `12:00` as one block's end and another's start is not an overlap. |
| **Maximum daily working time** (`employees.max_daily_hours`, default 10) | § 2 Abs. 1 ArbZG defines working time as the time from start to end of work *without the breaks*, so the day's total is the **sum of the blocks, each net of its break**, not the span from the first start to the last end. `08:00–12:00` plus `16:00–20:00` is eight hours of working time, not twelve — and two seven-hour blocks are thirteen, not fourteen (see [Breaks and net working time](#breaks-and-net-working-time)). |
| **Rest period across days** (`employees.min_rest_hours`, default 11) | § 5 Abs. 1 ArbZG grants the rest period *after the end of the daily working time*, so it is measured from the **last** block of one day to the **first** of the next. The interruption in the middle of a split shift is not a rest period — it sits inside the working day. |

Both the generator and the manual-correction path apply these, and as everywhere else the manual path **warns rather than blocks**: HR stays in charge.

**What this tool deliberately does not check**, so that it is written down rather than silently assumed:

- ~~The eight-hour average of § 3 Satz 2~~ — reported since, see [The eight-hour average](#the-eight-hour-average). The planner still does not *enforce* it, deliberately: whether ten hours today are lawful is settled by the months that follow.
- ~~The position of a break within a block, and with it § 4 Satz 3~~ — implemented since, see [Where the break falls](#where-the-break-falls-and-whether-sunday-work-is-allowed-at-all). Recording the position is optional, and the check bites where somebody has stated one. Worth noting in the other direction: an interruption of at least 30 minutes between two blocks *satisfies* § 4 in form, which makes a split shift the cleaner arrangement of the two.
- ~~Sunday rules (§ 11 ArbZG)~~ — implemented since, see [Rest days and free Sundays](#rest-days-and-free-sundays). ~~§ 9 and § 10~~ and ~~the holiday calendar~~ followed later; the operator now states the § 10 question rather than the tool guessing it.

`employees.max_daily_hours` is `NOT NULL DEFAULT 10` rather than nullable, following the same reasoning `0001_baseline.py` gives for `min_rest_hours`: a safety-relevant setting should never be unset. "No daily limit" must not be what a forgotten field quietly means.

### Breaks and net working time

Since this stage the tool distinguishes **presence** from **working time**. Someone rostered `08:00–16:00` is present for eight hours and works seven and a half: § 2 Abs. 1 ArbZG defines working time as the span *without* the breaks.

**The model is a duration, not a position.** `shift_assignments.break_minutes` is nullable, and `NULL` means *the legal minimum for this block's span* rather than "no break" — the law requires the break, so a plan that failed to subtract it would be claiming someone works eight hours straight through. A stored value wins, including an explicit `0`: that is HR stating this block runs without one, which is a different thing from not having decided. The column is nullable for exactly that reason, and deliberately unlike `max_daily_hours`, which is `NOT NULL DEFAULT 10` because a safety limit should never be unset.

This follows the same three-layer restraint the hours already use: the normal case is written nowhere and derives itself, only the deviation is stored. Every pre-existing row therefore stays valid and picks up the right break retroactively.

**The minimum is resolved onto the span, and that is subtler than it looks.** § 4 measures the break against the *working* time, and working time is the span minus the break — read literally the rule chases its own tail. A 6:30 span is 6:30 of work without a break, which is "more than six hours" and demands 30 minutes, which brings the work down to exactly 6:00, which demands nothing. `legal_break_minutes()` resolves it by asking which break is sufficient for the working time it itself produces, and taking the smallest such break:

| Span | Break |
|---|---|
| up to and including 6:00 h | 0 |
| over 6:00 h up to and including 9:30 h | 30 min |
| over 9:30 h | 45 min |

Note **9:30, not 9:00**. At a 9:30 span a 30-minute break still leaves exactly nine hours, and nine hours is not "more than nine"; only from 9:31 does 30 minutes stop being enough. Applying the law's own numbers straight to the span is the obvious mistake, and `backend/test_working_time.py` pins the four edges — checking the *property* the thresholds derive from, so a hard-coded table or a constant 45 would not pass.

**What counts net and what counts gross.** The daily cap (§ 3), the weekly target hours and both of their counterparts on the manual-correction path all count net. Everything about presence stays gross: coverage gaps, the overlap check between two blocks of a day, the rest period under § 5 (which measures end to start, not working time), and the availability-window check — someone available `08:00–16:00` is available during their break too. `backend/test_api_coverage.py` carries the counter-test for this: an assignment with a break still covers its full presence. Had coverage moved to net as well, every block would leave half an hour of gap that nobody could ever close, because every replacement would bring a break of their own.

**This loosened existing limits.** Five eight-hour days are 40 hours of presence but 37.5 hours of working time, so a 38-hour weekly target now fits where it previously did not. That is the correct reading of § 2 Abs. 1, but it changes plans nobody touched.

**§ 4 Satz 3** — "no more than six hours of work at a stretch without a break" — needs the break's *position*, not just its length. That is modelled since a later stage; see [Where the break falls](#where-the-break-falls-and-whether-sunday-work-is-allowed-at-all). Still not modelled is the law's allowance to split a break into segments of at least 15 minutes each; what is stored is one total and one position.

The one place § 4 can be broken at all is the manual-correction path: left alone the break is the legal minimum and every plan is compliant by construction, so only someone entering a shorter break by hand gets a warning — and it stays a warning.

**And it is now visible.** The break was computed, enforced in the generator, and subtracted from every hours figure — and shown nowhere unless somebody had overridden it. The reasoning was that the statutory break would be the same number on every row, so printing it would be noise; that reasoning is wrong, because § 4 makes it a function of the span and a single day routinely carries a 30-minute block beside a 0-minute one. The effect was that the person whose break it is could not see it anywhere: the calendar is the only place an employee's own duty appears, and `08:00–16:30` with no word about a break reads as eight and a half hours of work. The calendar now writes *incl. 30 min break* under the block's hours, the schedule table shows the break that applies on each slot, and a hand-entered one is set in bold so it still reads as a decision somebody made rather than as the rule.

### Where the break falls, and whether Sunday work is allowed at all

Two rules this tool used to hand to HR rather than check.

**§ 4 Satz 3 — no more than six hours in one go.** Until this stage the tool knew only the break's *duration*, never its *position*. Half an hour of break starting at the shift's first minute satisfies Satz 1 and breaches Satz 3, and both looked identical in the database.

That is a modelling gap as much as a checking one: [§ 4 Satz 1](https://www.gesetze-im-internet.de/arbzg/__4.html) asks for breaks "im voraus feststehend" — fixed in advance — and a duration without a time is not fixed. A block can now carry when its break begins.

**Optional on purpose.** For every block this tool can build — at most ten hours, at least thirty minutes of break — a lawful position always exists, so an unstated one is never a *known* breach. Flagging it would mean warning on every single block; requiring it would declare every existing roster invalid; inventing a default would assert something about a workflow the tool does not know. The check bites exactly where somebody has stated a position, and there it has teeth. Exactly six hours stays allowed — the sentence says *longer than*.

**One position per block.** § 4 Satz 2 permits splitting a break into chunks of at least fifteen minutes; modelling that would be its own table. Not modelling it makes the tool **stricter, not laxer** — record the longest chunk's position and you get more warnings than you are owed, not fewer. Worth saying rather than leaving to be discovered.

**§ 9 / § 10 — is this business exempt?** § 9 Abs. 1 forbids work on Sundays and public holidays; § 10 exempts whole industries. The tool used to warn on *every* holiday and on *no* Sunday — the first is pure noise for a hospital, and the second was missing outright even though § 9 covers Sundays just the same.

There is now a setting for it, defaulting to **not exempt**, because that is what § 9 says and because a tool that assumes the exemption falls silent on the very rule it was asked to watch.

**What the exemption does not switch off:** the fifteen free Sundays of § 11 Abs. 1 and the replacement rest day of § 11 Abs. 3. Both are the counterweight *to* § 10 and apply precisely when it does. An exemption that turned them off too would turn a permission into a dispensation — and there is a test that says so.

### Rest days and free Sundays

Two more rules bind the planner since this stage, both hard in the generator and warnings on the manual-correction path.

**No more than six days in a row.** § 11 Abs. 3 ArbZG grants a replacement rest day within two weeks of every Sunday worked, and within eight weeks of every public holiday worked on a weekday. That is a condition about the **absence** of assignments — it cannot be judged until the whole month stands, which a backtracking search handles badly. Never working more than six days in a row means a free day at least every seven, which satisfies the two-week window, and the eight-week one outright.

This is **stricter than the law reads**, deliberately: Monday through Sunday with the following Monday off is lawful, and this rejects it. It buys a condition the search can actually carry, and it is checked in *both* directions from the day in question — `MOST_CONSTRAINED` does not run in calendar order and `AUTO` uses both orderings, so counting only backwards would let a run of seven assemble itself from the back, one harmless-looking day at a time.

**At least 15 free Sundays a year.** § 11 Abs. 1. The budget is the year's Sundays (52 or 53 — computed, not assumed; the difference is one Sunday of everyone's allowance) minus 15, minus the ones already worked. A second block on a Sunday someone already works costs nothing extra: § 11 Abs. 1 asks whether the day is free, not how many blocks sit on it, and charging twice would make a split shift on a Sunday dearer than one on a weekday. A budget that already went negative in the past reads as zero — the planner stops adding Sundays, but it does not raise over data it did not cause.

**The generator now reads outside its month.** That boundary had stood since the beginning: `max_shifts_per_month` and the rest-period check both simply end at the edge of the month being generated. Both rules here reach past it, so `scheduling_history()` in `backend/app.py` loads two numbers per employee — the length of the run of days worked immediately before the month starts, and the Sundays already worked this calendar year.

That loading has one trap worth knowing about. `generate_schedule_route()` deletes the month's assignments only *after* the search has run, so they are still in the database while the history loads. Counting them would dock everyone for shifts the same request is about to take away. The history is therefore bounded by the **date range** of the target month, never by `schedule_id` — a date inside the month belongs to that month, whatever schedule row it hangs off. `test_zweimal_erzeugen_ergibt_zweimal_denselben_plan` in `backend/test_api_schedules.py` is the test for it.

Both rules are read from the employee dict (`max_consecutive_days`, `sundays_worked_in_year`) rather than applied unconditionally, exactly as `min_rest_hours` is: the law fixes the number, the planner enforces what its caller supplies. That is what leaves the 23 backward-compatibility tests in `test_scheduler.py`, which deal in shift counts and nothing else, untouched.

**§ 9 and § 10.** Sunday and public-holiday work is forbidden in principle, and § 10 exempts whole industries — restaurants, hospitals, care, transport, bakeries and a dozen more. Whether *this* business falls under one is a fact about the business, not something the tool can derive.

This section used to argue that a "Sunday work permitted" switch would do nothing the opening hours do not already do. That was half right: the opening hours settle the **demand** — a business closed on Sundays gets no Sunday blocks — but they say nothing about a shift somebody assigns *by hand*, and nothing about which warnings are worth showing. A later stage added the switch for exactly that; see [Where the break falls, and whether Sunday work is allowed at all](#where-the-break-falls-and-whether-sunday-work-is-allowed-at-all). It changes what is *reported*, never what is enforced.

**And still not known: which dates are public holidays.** A holiday calendar with per-state selection is its own stage; it changes nothing about the rules above, since the six-day rule covers the eight-week window regardless. What it would add is awareness — HR seeing that a date is a holiday before publishing.

**The manual-correction path is the stricter of the two.** It runs against saved data, so it also sees *forward* past the end of the month; the generator cannot, because next month's blocks do not exist yet when it runs.

### The eight-hour average

The last of the three rules stage 4 left open. § 3 Satz 2 allows ten-hour days **only** if the average over six calendar months or 24 weeks stays within eight hours per working day. Stage 4 introduced `max_daily_hours` with a default of 10 and said outright that the limit is not self-supporting without that proof; this is the proof.

**Reported, not enforced**, and that is the whole point: whether ten hours today are lawful is settled by the months that follow. Insisting on it while generating would mean either miscounting or restricting for no reason. `GET /schedules/<year>/<month>` returns `average_hours` beside `coverage_gaps` — only the employees over the line, the way the gap list reports only gaps.

Two things about the calculation are easy to get wrong:

- **The employer picks the reference period** — six calendar months *or* 24 weeks — and may lay it rolling; the law prescribes no calendar half-years. This computes 24 weeks, ending on the last day of the month being viewed. Six months would be just as lawful, and a setting for it would be surface nobody has asked for yet.
- **The average is per *working day*, not per day worked and not per calendar day.** Working days are Monday through Saturday. That makes for a generous denominator: five eight-hour days a week average about 6.2 hours per working day, so the limit only bites on many long days. That is the norm, not a softness here.

Working time is counted net of breaks, as everywhere since [Breaks and net working time](#breaks-and-net-working-time).

**Public holidays drop out of the denominator once a federal state is selected** (see [Public holidays](#public-holidays)). Without one the tool knows no holidays, counts them as working days, and the check is correspondingly too *lenient* — it can miss an excess, never invent one. Worth naming, because that is the more uncomfortable direction of the two.

### Public holidays

§ 9 forbids work on public holidays but **names none** — it uses the term and leaves the filling to state law. So the calendar is a table per federal state, and `backend/holidays.py` is that table: the nine nationwide holidays, ten regional ones, Easter by the anonymous Gregorian algorithm, and Buß- und Bettag as the Wednesday before 23 November. No library — Easter is twelve lines of arithmetic and the rest is a table, and the project built its own i18n and migration runner for the same reason.

**The state is a setting**, `holiday_region` in the new `settings` table. **With none selected the tool knows no holidays** and behaves as it did before; there is deliberately no default, because guessing a state would be worse than having none.

**Holidays are not closed automatically.** The opening hours decide that, as they always have — the tool cannot know whether the business falls under one of § 10's industry exemptions, and shutting a hospital or a restaurant on 3 October would simply be wrong. What the calendar does is mark and warn: dates show up in the calendar view, and assigning someone to one produces a non-blocking warning that states the situation and leaves the judgement where it belongs.

**One place it sharpens a calculation.** [The eight-hour average](#the-eight-hour-average) counts holidays as working days when no state is selected, which makes it too lenient. With a state, they drop out of the denominator — over a 24-week window that is typically four or five days, and the allowance falls accordingly.

**Not included: holidays below state level.** Corpus Christi is a holiday in Saxony and Thuringia only in predominantly Catholic municipalities, Assumption Day likewise in Bavaria, and the Augsburg Peace Festival only in the city of Augsburg. A state alone does not settle those, and a municipality list would be its own undertaking. The calendar is therefore incomplete in the lenient direction — it knows one holiday too few, never one too many. Anyone affected enters the day as an opening-hours exception, as before.

### Across the month boundary

A month is a billing period, not a unit of rest. Two rules run straight across the boundary, and until this stage they stopped at it — because both live in one search run's state, and that state started empty on the 1st.

**The eleven hours between two shifts.** A night shift ending 06:00 on the 31st and an early shift starting 06:00 on the 1st are each fine within their own month, and leave zero hours of rest between them. That is a plan which keeps every rule inside itself and breaks [§ 5 Abs. 1 ArbZG](https://www.gesetze-im-internet.de/arbzg/__5.html) at exactly one point in the year — the least conspicuous fault a roster can have.

**The weekly-hours target.** The calendar week does not end on the last of the month either. An empty counter hands everyone a fresh weekly budget on whatever weekday the 1st happens to be, and the straddling week quietly runs over.

The six-day run and the yearly Sunday budget have crossed the boundary since the working-time stage — but those are *numbers*, and numbers can be handed in ahead of the search. Rest periods and weekly hours need *times*, so the generator now receives what the neighbouring months already hold and seeds its state with it.

**Loaded from the saved plans, not guessed.** Seven days either side: the rest period only ever needs the two flanking dates, but a straddling week reaches up to six days into the neighbouring month. Assignments *inside* the month being generated are excluded — the same request is about to delete them, and counting them would dock everyone for shifts that are being replaced.

**The flanking days are deliberately kept out of the search's own day state.** Merging them would be the obvious move and the wrong one: `worked_dates()` reads those keys, and a Sunday at the edge of the month would then be charged twice — once there and once through the yearly Sunday count, which already spans the whole year.

**One direction only.** Regenerating August after September exists gives you an August that respects September, not the other way round. A plan that rewrites other plans would be a much larger decision.

### How big a month can get

Measured, not guessed — `backend/benchmark.py` ends with a scaling probe on the production path, with half the workforce in availability-window mode, which is where the two long-deferred performance notes lived.

| people | per shift | blocks | stage 1 | stage 2 | unfilled |
|---|---|---|---|---|---|
| 10 | 2 | 124 | 0.011s | 16.1s | 62 |
| 25 | 5 | 310 | 0.032s | 16.2s | 17 |
| 50 | 10 | 620 | 0.104s | 16.3s | 5 |
| 100 | 20 | 1240 | 0.346s | — | too large |
| 200 | 40 | 2480 | 1.361s | — | too large |

**Block planning is not the bottleneck.** 1.36 seconds at 2480 blocks answers the note that said "only look at `plan_day()` when the benchmark shows it" — it does not show it.

**The wall is recursion depth.** The search calls itself once per block, so a month's block count *is* the stack depth. Python's default limit of 1000 puts the ceiling near 900 blocks — roughly thirty blocks a day, which is a large ward rather than a thought experiment. Above it, generation used to fail with a `RecursionError` surfacing somewhere unrelated (during the measurement it landed in `locale.getlocale`, and the message said nothing).

It now raises a named exception and the API answers with both numbers: how many blocks this month has, and how many the search can take. The check sits where both ways of getting slots meet — the first version guarded only the caller-supplied path and left the one that builds its own slots to crash exactly as before, which the review caught. **Stating a limit is not the same as lifting it** — turning the recursion into an explicit stack is a real rewrite of branch-and-bound with six undo structures, and the compatibility tests only cover shift counts. Raising `sys.setrecursionlimit()` moves the wall and trades a clean exception for a possible hard crash. Both are decisions with a cost, and neither is taken here.

**Two full budgets, not one.** Stage 2 sits above 100% of the 8-second budget whenever gaps remain, because that is what the adaptive strategy does: a second pass with a different ordering. Sixteen seconds is the documented worst case, not an overrun.

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

## Tech Stack

**Frontend**
- React (with Vite)
- React Router
- Vitest + Testing Library (dev-only, component tests — see Local Setup below)

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
│   ├── scheduler.py            # Stage 2: backtracking search (ordering + fairness)
│   ├── block_planner.py        # Stage 1: demand bands + templates + windows -> blocks (no DB)
│   ├── coverage_model.py       # Pure coverage-curve/gap math (weekday demand bands, no DB)
│   ├── holidays.py             # Public holidays per federal state (no DB)
│   ├── exports.py              # iCal and CSV formatting (no DB)
│   ├── security.py             # Login throttling, backed by the login_attempts table
│   ├── timeutil.py             # "Current month" in the operating timezone
│   ├── migrations/              # Versioned schema migrations, 0001-0017 (see Operations below)
│   ├── baselines.py            # Alternative algorithms, for comparison only
│   ├── benchmark.py            # Head-to-head comparison run
│   ├── test_scheduler.py       # Unit tests for the algorithm (the compatibility guarantee)
│   ├── test_block_planner.py   # Unit tests for stage 1, including the trimming
│   ├── test_scheduler_split_shifts.py  # Split shifts, daily cap, rest across days
│   ├── test_working_time.py    # § 4 break thresholds and net working time
│   ├── test_holidays.py        # The holiday table, Easter, and Buß- und Bettag
│   ├── test_api_publishing.py  # Who sees which plan, and when
│   ├── test_api_audit.py       # The change log, including that it never breaks a request
│   ├── test_exports.py         # iCal escaping, CRLF, CSV for Excel
│   ├── test_api_exports.py     # Who may download what
│   ├── test_api_dsgvo.py       # Access, anonymisation, retention
│   ├── test_api_schichttausch.py  # The guided swap, and where the law says no
│   ├── test_api_arbzg_rest.py  # Break position (§ 4 Satz 3) and the § 10 exemption
│   ├── test_api_qualifikationen.py  # Certificates, and above all their expiry
│   ├── test_migrations_bestand.py  # A filled 0007 database lifted to 0017, real Postgres
│   ├── test_api_tag_eins.py     # What day one on an empty database tells the operator
│   ├── test_api_einrichtung.py  # What is still missing, and what is only worth knowing
│   ├── test_scheduler_grenze.py # The recursion ceiling, named rather than crashed into
│   ├── test_api_gesundheit.py   # A health check that actually checks
│   ├── test_api_token_widerruf.py  # That a password reset really ends the old session
│   ├── test_api_betriebsblick.py   # What the tool now says instead of staying quiet
├── docs/
│   ├── DATENBANKWECHSEL.md     # The 30-day database cycle, one pass at a time
│   ├── HANDOFF.md              # Running state, decisions and this project's traps
│   ├── entwuerfe/              # Per-stage design notes: the decision and its reasoning
│   └── plaene/                 # Per-stage implementation plans, task by task
│   ├── test_scheduler_rest_days.py     # Six-day rule and the yearly Sunday budget
│   ├── test_api_eingaben.py    # Dates, weekdays and hours that used to slip through
│   ├── test_api_security.py    # Throttling, the invited-account branch, security headers
│   ├── test_migrations_postgres.py  # The dialect layer and both advisory locks, real Postgres
│   ├── requirements.txt
│   └── requirements-dev.txt    # + ortools, only needed for the benchmark
└── frontend/
    └── src/
        ├── App.jsx           # Routing, navigation, auth guarding & language toggle
        ├── ErrorBoundary.jsx # Catches a render error so one component cannot blank the page
        ├── ErrorBoundary.test.jsx
        ├── Flash.jsx         # The one message line: errors stay, successes fade
        ├── Flash.test.jsx
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
        │   ├── ShiftTypes.jsx    # Shift type CRUD (the template: name, hours, colour)
        │   ├── ShiftTypes.test.jsx
        │   ├── BusinessHours.jsx      # Opening-hours-per-weekday + date-exception editor
        │   ├── BusinessHours.test.jsx
        │   ├── CoverageEditor.jsx     # Coverage-band editor (overlap/opening-hours validation)
        │   ├── CoverageEditor.test.jsx
        │   ├── AuditLog.jsx      # The change log, deliberately raw
        │   ├── SwapRequests.jsx  # Propose / accept / approve a shift swap
        │   ├── SwapRequests.test.jsx
        │   ├── Employees.test.jsx
        │   └── SchedulePage.jsx  # Generate / view / edit the monthly plan
        └── components/
            ├── ScheduleGrid.jsx    # The schedule grid: reassign + swap UI
            ├── ShiftCell.jsx       # One shift/date cell: reassign, swap, suggestions, quick-log absence
            ├── ShiftCell.test.jsx
            ├── CalendarView.jsx    # Read-only wall-planner view
            ├── CalendarView.test.jsx
            ├── CoverageGaps.jsx    # Renders coverage_gaps against a fetched schedule
            ├── AverageHours.jsx    # Renders average_hours: who breaks § 3's average
            ├── AverageHours.test.jsx
            ├── Distribution.jsx    # Shifts-per-employee balance panel
            ├── AbsenceManager.jsx  # Employee self-service: report/cancel sick & vacation
            └── AbsenceManager.test.jsx
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

**Tests.** The suite covers the scheduler itself plus the API, the migration runner, request throttling and timezone handling. It needs `requirements-dev.txt` (not just `requirements.txt`) for `pytest`:

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest
```

`pytest.ini` picks up every `test_*.py`, including `test_scheduler.py`'s existing `unittest.TestCase`s — pytest runs those unmodified alongside the rest, so there's no separate `unittest` invocation to remember. `.github/workflows/ci.yml` runs the same command on every push to `main` and every pull request, against Python 3.13 (the production version — see `render.yaml`) and 3.14 (so local development on a newer interpreter doesn't drift unnoticed). A separate `backend-postgres` job runs the same suite (minus `test_scheduler.py`, which is pure algorithm logic with no database access) against a real Postgres service container instead of SQLite — this is what actually exercises the Postgres dialect layer in `backend/db.py` and the migration runner, not just SQLite. A `frontend` job runs `npm run lint`, `npm run build`, and `npm test` the same way (see Frontend below).

To run the algorithm comparison instead (same `requirements-dev.txt`, which also installs OR-Tools for the exact CP-SAT reference):

```bash
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

**Tests.** The project's first frontend test infrastructure, added in this stage alongside the coverage-band editor — the overlap validation that editor does is exactly the kind of component where clicking through the UI by hand stopped being enough. Vitest, `@testing-library/react` and `@testing-library/jest-dom` are dev dependencies; test files sit next to what they test (`frontend/src/pages/*.test.jsx`).

```bash
npm test -- --run
```

Plain `npm test` starts Vitest in watch mode, which is what you want locally; `--run` makes it execute once and exit, which is what CI needs so the job actually terminates.

## Deployment

**Frontend:** [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/)

The app runs on SQLite locally and **Postgres in production**, chosen automatically: set `DATABASE_URL` and it uses Postgres, leave it unset and it writes a local `schichtplan.db`. This matters more than it sounds — a free-tier container's filesystem is wiped on every restart, so deploying on SQLite would quietly lose every schedule.

**Backend (Render).** `render.yaml` in the repository root is a blueprint: pointing Render at the repo creates the web service *and* a Postgres database, wires `DATABASE_URL` between them, and generates a `SECRET_KEY`. Two values must be filled in by hand afterwards, because they depend on where the frontend lands:

- `ALLOWED_ORIGINS` – the deployed frontend's origin, e.g. `https://schichtplan.vercel.app`
- `APP_BASE_URL` – the same origin; invitation links are built from it

**Frontend (Vercel).** Import the repo, set the root directory to `frontend`, and add one environment variable:

- `VITE_API_URL` – the deployed backend's URL, e.g. `https://schichtplan-api.onrender.com`

`frontend/vercel.json` already routes client-side paths back to `index.html`, so deep links like `/set-password?token=…` resolve instead of 404ing.

**Mail.** `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM` are declared in `render.yaml` with `sync: false`, so Render asks for them at deploy time; `SMTP_PORT` and `SMTP_USE_TLS` carry defaults. Without `SMTP_HOST` the app still starts, but invitations are only written to the service log instead of being sent — which in practice means **no employee account can be set up and nobody who forgets their password can get back in.** That used to be discoverable only by watching somebody wait for an email that never came; the app now logs a warning at startup when it is running in production without `SMTP_HOST`. `backend/.env.example` lists every variable.

**First run.** Opening the deployed frontend lands on "Erstes Konto einrichten"; that first account is HR and sets its own password. Everyone after that is invited by email.

## Operations

**Gunicorn.** `render.yaml`'s `startCommand` runs `gunicorn app:app --bind 0.0.0.0:$PORT --preload --threads 4 --timeout 60 --access-logfile -`, instead of Gunicorn's single-worker, single-thread default. The scheduler can run for up to `DEFAULT_TIME_BUDGET_SECONDS` (8s, `backend/scheduler.py`) computing a plan; a single synchronous worker would leave the API unresponsive to everyone else for that whole time. The four threads keep the rest of the API — which is mostly waiting on the database, not the CPU — responsive underneath while one of them schedules. `--timeout 60` gives the scheduler room without leaving a genuinely stuck worker running forever.

**One worker, not two,** and the reasoning is written out in `render.yaml` itself: threads share the process's memory, a second worker doubles it, and the free plan has 512 MB. The argument that originally favoured two workers — parallel progress past the GIL — was outweighed once the migration race it was paired with got closed in code by the Postgres advisory lock in `backend/migrations.py` rather than only by `--preload`. Each request opens its own database connection (`get_db()` in `backend/app.py`), so this caps concurrent connections at 4 (1 worker × 4 threads); the free plan's exact connection ceiling hasn't been checked against that number. Anyone raising the worker count should measure memory first.

**Why `--preload` is there, and why removing it would be dangerous.** `init_db()` (`backend/db.py`) runs at import time and applies any pending migrations. Without `--preload`, Gunicorn forks first and each worker imports `app.py` — and so runs `init_db()` — independently, with only a 0–100ms stagger between forks. On any deploy that ships a schema change, two workers can genuinely call `migrations.apply_pending()` at close to the same instant. The failure mode is not "one worker retries and moves on": a worker that raises during boot triggers Gunicorn's `WORKER_BOOT_ERROR`, which makes the arbiter's `reap_workers()` raise `HaltServer` — and the arbiter then shuts down **the entire service**, including the sibling worker that had already applied the migration successfully. That's a full outage on any deploy carrying a schema change, and this project has several planned. `--preload` closes it: it makes Gunicorn import the application (and therefore call `init_db()`) exactly once, in the master process, before forking any worker, so the race cannot occur. This is safe for this app specifically because `init_db()` closes its database connection before returning (see `finally: connection.close()` in `backend/migrations.py`'s `apply_pending()`), and nothing else at module level in `backend/app.py` holds a socket, file, or thread open that a fork would inherit badly — `logging.basicConfig()` only attaches a handler for stderr, which every forked child gets from Gunicorn regardless. Do not remove `--preload` as apparent clutter; it is the fix for the failure mode above, not a leftover.

**Migrations.** The schema updates automatically on startup (`init_db()` delegates to `migrations.apply_pending()`). Applied as of this stage: `0001_baseline`, `0002_indexes`, `0003_login_attempts`, `0004_employee_availability`, `0005_assignment_times`, `0006_coverage` (creates `business_hours`, `business_hours_exceptions`, `coverage_requirements`), `0007_derive_coverage` (a one-time data migration that seeds `coverage_requirements` from the existing `shift_requirements` demand — see [Opening hours and coverage requirements](#opening-hours-and-coverage-requirements) above), `0008_max_daily_hours` (adds `employees.max_daily_hours`, `NOT NULL DEFAULT 10` — see [Split shifts and working-time law](#split-shifts-and-working-time-law)), `0009_break_minutes` (adds `shift_assignments.break_minutes`, nullable — see [Breaks and net working time](#breaks-and-net-working-time)), `0010_drop_shift_requirements` (drops the old per-weekday demand table; its contents were carried into `coverage_requirements` by `0007`), `0011_settings` (a key/value table for business-wide settings; the first key is `holiday_region` — see [Public holidays](#public-holidays)), `0012_publish_state` (adds `schedules.published_at` and turns every existing plan into a published one — see [Draft and published](#draft-and-published)), `0013_audit_log` (the change log — see [The change log](#the-change-log)), `0014_anonymisation` (adds `employees.anonymized_at` — see [Data protection](#data-protection)), `0015_swap_requests` (the guided swap — see [The guided swap](#the-guided-swap)), `0016_break_position` (adds `shift_assignments.break_start`, nullable), `0017_qualifications` (the certificate catalogue and its two link tables — see [Certificates a shift requires](#certificates-a-shift-requires)), `0018_token_epoch` (adds `users.token_epoch`, `NOT NULL DEFAULT 0` — see [Revoking a sign-in](#revoking-a-sign-in)). To manage by hand:

```bash
cd backend
./venv/bin/python migrations.py status   # what's applied
./venv/bin/python migrations.py up       # apply anything pending
./venv/bin/python migrations.py down     # roll back the most recently applied one
```

**Backup.** The free Postgres plan expires after 30 days, and the operator's decision is to let it expire and raise a new one. That makes the changeover **a cycle rather than a date** — [`docs/DATENBANKWECHSEL.md`](docs/DATENBANKWECHSEL.md) is the run sheet for one pass.

**The consequence worth reading once:** a database that starts over every 30 days does not keep working-time records. § 16 Abs. 2 ArbZG asks for two years, and this whole tool is built around that — retention deliberately spares assignments, deleting a person anonymises rather than removes. A cycle without a restore undoes it. Two things resolve that: back up and restore every cycle, or pay for a plan. Running the cycle *and* skipping the backup is the one combination that does not work.

So back up by hand, and before the instance lapses rather than weekly-ish:

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_dump" "$DATABASE_URL"   --no-owner --format=custom --file="schichtplan-$(date +%Y-%m-%d).dump"
```

Restore:

```bash
"/c/Program Files/PostgreSQL/18/bin/pg_restore" --clean --no-owner   --dbname="$DATABASE_URL" schichtplan-2026-08-16.dump
```

**The full path is not decoration.** Neither binary is on `PATH` on the machine this project is developed on; a bare `pg_dump` answers "command not found", which reads like a missing program rather than a missing path. That was already written down in the handoff — and this section still spelled the bare command, which is the more instructive half of the story: a fact recorded in one place and ignored in the instructions is a fact nobody has.

**Environment variables.** Full list in `backend/.env.example`. Required in production:

| Variable | Without it |
|---|---|
| `SECRET_KEY` | The app refuses to start (`backend/security.py`) — it signs the session cookie and bearer token; a known key would let anyone forge a valid login |
| `DATABASE_URL` | Falls back to a local SQLite file on a filesystem that's wiped on every restart — every schedule would be lost |
| `ALLOWED_ORIGINS` | The frontend gets a CORS error on every call |
| `APP_BASE_URL` | Invitation links point at `localhost` |
| `FLASK_ENV=production` | No secure cookie flag, no HSTS header, and `SECRET_KEY` is no longer enforced |

`APP_TIMEZONE` (default `Europe/Berlin`) is not required — it decides which calendar month counts as "current" when an employee reports their own sick/vacation day; set it only if the deployment serves a different timezone.

**Hosting region.** `render.yaml` puts both the web service and the database in `frankfurt`. What is processed here is names, working hours and sick notes, and sick notes are health data under Art. 9 GDPR; Render's own default is a US region, which would make every one of those a third-country transfer needing a Chapter V justification. An EU region takes the question out of the documentation instead of answering it. **The line only affects newly created resources** — Render fixes a region at creation and does not move it — so for anything already running, the next database cycle is the moment it takes effect. The Art. 28 processing agreement with Render is a separate obligation and is needed either way; so is the Art. 30 record of processing activities. Neither is something code does.

**Monitoring.** `.github/workflows/keepalive.yml` pings the API every fourteen minutes so the free plan does not spin down, and swallows failures on purpose — at that cadence a blip during a deploy is not worth a message. `.github/workflows/health-check.yml` is the one that *is*: hourly, against `/health`, and it **fails the job** when the service does not report healthy. A failed Actions run mails the repository owner, which is monitoring without a second service, an account or a bill.

Both used to be one workflow that pinged `/` and ended in `|| true`. That combination meant the service counted as reachable as long as Python was running, and that the job could not fail even when it should have — it never reported anything, because it had no way to. If the database went down on a Saturday you found out on Monday from somebody who could not see their plan. `/health` actually reads from the database and answers `503` when it cannot (`backend/app.py`); `curl -f` turns that into a failure. Two attempts ninety seconds apart, because Render wakes the free plan on demand and the first call can land in the cold start.

Neither replaces a proper uptime service, and hourly is a deliberate ceiling: a monitor that fires on every deploy gets ignored after the third mail, and an ignored monitor is worse than none. `/health` already returns what such a service would need.

**Troubleshooting.** Every unexpected error response carries a `request_id`; the same identifier is written to the server log next to the exception (`app.logger.exception` in `backend/app.py`). Search the Render service's log output for that id to find the underlying stack trace — the exact path through Render's current dashboard UI hasn't been verified here.

## API Endpoints

Everything except `/`, `/health`, `/register`, `/login` and `/me` needs a signed-in session (`401` without one) — `/health` is public because a health check behind a login is one nobody can use, and it reports the schema version rather than anything about the workforce. Everything that changes data also needs the HR role (`403` for an employee account) — **except** the three `/employees/<id>/absences` routes and reading `/employees/<id>/availability`, which an employee account may also call, but only for its own `<id>` and (for POST/DELETE) only for a date in the current calendar month; HR is unrestricted on both. A handful of *reads* are HR-only too, for the same reason: `/employees`, `/setup-status`, `/audit-log`, `/accounts`, `/business-hours`, `/coverage-requirements`, `/settings` and — since it turned out no employee screen ever asked for it — `/qualifications`. What an employee account can read is its own plan, its own record, the shift types those refer to, and the colleague names a swap request needs. Every route's error/success messages are returned in whichever language the `X-Lang` request header names (German if omitted or unrecognized — see [Language](#language)).

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
| GET    | `/employees/<id>/availability`  | An employee's own working-time windows (self or HR)          |
| PUT    | `/employees/<id>/availability`  | Replace only that employee's windows, leaving their other constraints alone (HR) |
| GET    | `/employees/<id>/absences`      | List an employee's reported sick/vacation days `?year=&month=` (self or HR) |
| POST   | `/employees/<id>/absences`      | Report sick/vacation for one date `{date, type}`; frees any shift held that day (self, current month only, or HR, any date) |
| DELETE | `/employees/<id>/absences/<date>` | Cancel a report; restores the original shift if nobody has covered it yet (self, current month only, or HR, any date) |
| GET    | `/shift-types`                  | List shift types (with per-weekday requirements)              |
| POST   | `/shift-types`                  | Create a shift type                                            |
| PUT    | `/shift-types/<id>`               | Update a shift type                                             |
| DELETE | `/shift-types/<id>`               | Delete a shift type (blocked if used by an existing schedule)   |
| GET    | `/business-hours`                 | List the seven weekday opening-hours rows (HR)                       |
| PUT    | `/business-hours`                 | Replace all seven weekday rows at once `[{weekday, open_time, close_time, closed}, ...]` (HR) |
| GET    | `/business-hours/exceptions`      | List one-off date exceptions to the weekday rule (HR)                |
| POST   | `/business-hours/exceptions`      | Add an exception for one date `{date, open_time, close_time, closed, label}` (HR) |
| DELETE | `/business-hours/exceptions/<date>` | Remove a date's exception, reverting it to the weekday rule (HR)   |
| PUT    | `/schedules/<year>/<month>/status` | Publish a schedule or pull it back to a draft (HR)                  |
| GET    | `/audit-log`                      | The most recent change-log entries, newest first; `?limit=` up to 500 (HR) |
| GET    | `/employees/<id>/schedule.ics`    | One employee's shifts as iCal, `?year=&month=`; published plans only (self or HR) |
| GET    | `/schedules/<year>/<month>/export.csv` | The month as CSV, drafts included (HR)                          |
| GET    | `/employees/<id>/data-export`     | Everything stored about one person, as JSON (self or HR)             |
| GET    | `/colleagues`                     | Names and ids of the active workforce, for anyone signed in          |
| GET/POST | `/qualifications`               | The certificate catalogue (HR)                                       |
| DELETE | `/qualifications/<id>`            | Remove a certificate everywhere it appears (HR)                      |
| PUT    | `/employees/<id>/qualifications`  | What this person holds, expiry dates included (HR)                   |
| PUT    | `/shift-types/<id>/qualifications`| What this shift requires (HR)                                        |
| POST   | `/swap-requests`                  | Offer one of your shifts to a named colleague                        |
| GET    | `/swap-requests`                  | Yours and those addressed to you; HR sees all                        |
| PUT    | `/swap-requests/<id>/status`      | Accept / decline / withdraw / approve / reject                       |
| POST   | `/retention/purge`                | Remove personal extras past the retention period, reporting counts (HR) |
| GET    | `/setup-status`                   | What still prevents a usable plan, and what is only worth knowing (HR) |
| GET    | `/health`                         | Reads the database and reports the migration state; 503 when it cannot (public) |
| GET    | `/settings`                       | Business-wide settings as an object (HR)                             |
| PUT    | `/settings`                       | Sets the keys given, leaves the rest; unknown key is a `400` (HR)     |
| GET    | `/holiday-regions`                | The federal states to choose from                                    |
| GET    | `/coverage-requirements`          | List all coverage bands, every weekday (HR)                          |
| PUT    | `/coverage-requirements`          | Replace the full set of coverage bands at once; rejects a band that overlaps another on the same weekday or falls outside that weekday's opening hours (HR) |
| POST   | `/schedules/generate`            | Generate (or regenerate) a month's schedule `{year, month}`      |
| GET    | `/schedules/<year>/<month>`      | Get a month's schedule, its assignments, absences, the workload distribution, and coverage gaps against the opening-hours-bound demand bands |
| DELETE | `/schedules/<year>/<month>`      | Delete a month's schedule                                           |
| PUT    | `/schedules/<year>/<month>/shift-times` | Change a shift type's hours on one date, for everyone assigned to it; null times reset it to the shift type's default |
| POST   | `/schedules/<year>/<month>/slots` | Add one more place to a shift on a single date; `shift_type_id` may be omitted for a template-less block, which must then bring its own start/end times |
| DELETE | `/assignments/<id>`               | Remove a place from a shift on one date                              |
| PUT    | `/assignments/<id>`               | Reassign one shift slot to a different employee (or `null`), optionally setting that slot's own start/end times — every call writes both fields from the request body, so omitting them clears any individual times already set |
| POST   | `/assignments/swap`               | Swap the employees on two shift assignments `{assignment_id_a, assignment_id_b}` |
| GET    | `/assignments/<id>/replacement-suggestions` | Eligible employees for this slot, ranked by current workload (HR) |

## Status

Built and tested locally through v1.4: an automated backend test suite that grows with the feature set (602 tests at the time of writing — `cd backend && pytest` prints the current number; a further 49 are Postgres-only and skip without a Postgres instance), a frontend component test suite (Vitest + Testing Library, 68 tests, covering the coverage-band and opening-hours editors, the schedule cells' handling of blocks that run at different times on the same day, the error boundary, the message line and the self-service date bounds), a benchmark against four alternative algorithms plus an exact solver, scripted end-to-end API walkthroughs (registration/invitation, weekly-hours and rest-period warnings across a month boundary, the full self-service-absence → replacement-suggestion → reassignment flow, and both languages), and a full browser walkthrough — including in English — of create → generate → reassign → swap → check balance. Frontend deployed on Vercel: [scheduling-tool-six.vercel.app](https://scheduling-tool-six.vercel.app/).

**The most recent pass was a different kind of test:** working through the tool as HR and as an employee would, rather than as its author — over the API, then again in a real browser (Chromium, `Europe/Berlin`), from the empty database through setup, four employees, a shift type, opening hours, coverage bands, a generated and published August, the employee's own view and a swap request. It produced one security finding (a password reset that did not end the session it was meant to end), one date bug invisible in UTC and reproducible in Berlin, and a run of cases where the tool did the right thing and simply never said so — a person marked inactive who stays on next week's published shifts, a statutory break subtracted from every hour figure and shown nowhere, a retention period that only ran when somebody pressed a button. Those are written up where each belongs above; what they have in common is that no unit test would have found any of them.

**And one the browser could not have found either.** 49 of the backend tests only run against a real Postgres instance and skip silently without one, so every local run had been reporting green while `test_migrations_bestand.py` — the fixture that lifts a filled 0007 database to today — still asserted `0017_qualifications` as the newest migration. Adding `0018` broke it, and nothing said so until the suite ran against actual Postgres. It now reads the target from `available_versions()` instead of naming it: a test that has to be hand-adjusted for every new migration is not testing the migration, it is testing the adjustment.

**One thing the pass surfaced was a missing feature rather than a fault:** the coverage editor made you fill in all seven weekdays by hand. Copying a day onto others is now built in, and two decisions shape it. It **replaces** rather than appends — appending would put an overlap on every target day that already had bands, which is exactly the state the Save button refuses, and "Tuesday is like Monday" means replacement anyway. And **which days are alike is a choice, not a rule**: a hard-wired Mon–Fri would assert a working week this tool does not know about, so the days are picked, with Mon–Fri and All as shortcuts. The confirmation only appears where something is actually overwritten — one that fires on empty days too gets clicked away unread, and then so does the one that matters.

**The browser pass added two more, and both are questions of placement** — which is exactly what an API test cannot see. The `setup-status` notes hung on the same condition as the missing-items list, so they vanished the moment setup was complete: "four of four employees have no weekly hours on file" disappeared precisely when it started mattering. And the new-shift-type form rendered *after* the certificates panel, so clicking "New shift type" at the top of the page opened it two panels down, off-screen, with something unrelated in between.

## About This Project

This is the "signature project" of a portfolio built while transitioning into web development — the most involved piece technically, centered on the scheduling algorithm rather than CRUD alone.

The part worth reading is `backend/scheduler.py` together with `backend/benchmark.py`: the benchmark is what turned the planned v1.2 heuristic from "obviously an improvement" into a measured tradeoff, and changed the design from a fixed ordering to an adaptive one.

The second thing worth reading is `docs/`: `entwuerfe/` holds the design note written before each stage — the decision and, more usefully, the reasoning and the alternatives rejected — and `plaene/` the implementation plan it turned into. `HANDOFF.md` carries the running state, the traps this codebase sets, and the findings from each review round, including the ones where the implementation had already reported itself finished.
