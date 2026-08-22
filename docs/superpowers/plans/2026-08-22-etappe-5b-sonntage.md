# Etappe 5b — Sechstageregel und freie Sonntage: Umsetzungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHE SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`. Die Schritte nutzen Checkbox-Syntax (`- [ ]`) zur Nachverfolgung.

**Ziel:** Höchstens sechs Tage in Folge (§ 11 Abs. 3 über die Implikation) und mindestens 15 beschäftigungsfreie Sonntage im Kalenderjahr (§ 11 Abs. 1), beide hart im Generator und als Warnung auf dem Handkorrektur-Pfad.

**Architektur:** Zwei Prüfungen in `eligible_candidates()`, die auf den in Etappe 4 eingeführten Tagesstrukturen aufsetzen. Neu ist, dass der Generator erstmals Vorgeschichte bekommt: `app.py` lädt zwei Zahlen je Mitarbeiter und gibt sie im Mitarbeiter-Dict mit.

**Tech Stack:** Python 3.13/3.14, Flask, SQLite lokal / Postgres in Produktion. Frontend unverändert.

**Spec:** [`docs/superpowers/specs/2026-08-22-etappe-5b-sonntage-design.md`](../specs/2026-08-22-etappe-5b-sonntage-design.md)

## Globale Randbedingungen

- **Kein literales `?` in SQL, auch nicht in Kommentaren.**
- **Die 23 Tests in `backend/test_scheduler.py` bleiben unverändert.**
- **Kommentarsprache folgt der Datei.** `app.py` und `scheduler.py` englisch, die neueren Testdateien deutsch.
- **Commit-Nachrichten deutsch, ohne Umlaute.** Jeder Commit endet mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Vor jedem Commit:** *Würde dieser Test fehlschlagen, wenn ich das Feature lösche?*
- **Kein Schemaeingriff.** Wenn diese Etappe eine Migration braucht, stimmt etwas nicht.
- **Testlauf:** `cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning`.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `backend/test_scheduler_rest_days.py` | Sechstageregel und Sonntagsbudget im Suchkern | **neu** |
| `backend/scheduler.py` | Die zwei Prüfungen, das Hilfsprädikat `works_on()` | geändert |
| `backend/app.py` | Vorgeschichte laden, zwei neue Warnungen | geändert |
| `backend/i18n.py` | Zwei neue Warnungstexte | geändert |

**Reihenfolge:** Task 1 und 2 arbeiten am Suchkern und sind gegen von Hand gebaute Mitarbeiter-Dicts prüfbar. Task 3 verdrahtet sie mit echten Daten. Task 4 zieht den Handkorrektur-Pfad nach.

---

## Task 1: Sechstageregel im Suchkern

**Files:**
- Modify: `backend/scheduler.py` — `_search()`, neben `day_is_free()` und `rest_period_ok()`
- Test: `backend/test_scheduler_rest_days.py` (neu)

**Interfaces:**
- Consumes: `day_hours` und `day_untimed` aus Etappe 4 — beide haben `(employee_id, date)` als Schlüssel.
- Produces: `MAX_CONSECUTIVE_DAYS = 6` als Modulkonstante; `emp['days_worked_before_month']` optional, Standard 0.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
"""Sechstageregel und freie Sonntage im Suchkern.

Paragraph 11 Abs. 3 ArbZG verlangt fuer jeden gearbeiteten Sonntag einen
Ersatzruhetag binnen zwei Wochen. Das ist eine Bedingung ueber das FEHLEN von
Zuweisungen und fuer einen Backtracking-Suchlauf schlecht greifbar. Wer nie
mehr als sechs Tage in Folge arbeitet, hat aber spaetestens alle sieben Tage
frei - damit ist die Norm erfuellt, und die Bedingung ist lokal.

Paragraph 11 Abs. 1 verlangt mindestens 15 beschaeftigungsfreie Sonntage im
Kalenderjahr.
"""


def test_der_siebte_tag_in_folge_bleibt_offen():
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0) for tag in range(1, 8)]

    ergebnis = plan(bloecke, [person(1)])

    assert ergebnis['unfilled_count'] == 1


def test_sechs_tage_in_folge_gehen():
    """Gegenprobe: ohne sie waere eine Umsetzung gruen, die schon bei sechs sperrt."""
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0) for tag in range(1, 7)]

    ergebnis = plan(bloecke, [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_die_kette_baut_sich_auch_von_hinten_auf():
    """Der Fall, den eine Nur-nach-links-Zaehlung durchliesse.

    Die Bloecke werden in umgekehrter Kalenderreihenfolge angeboten. Wer die
    Kette nur nach links zaehlt, sieht bei jedem einzelnen Block eine kurze
    Kette und laesst alle sieben zu.
    """
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0)
               for tag in range(7, 0, -1)]

    ergebnis = plan(bloecke, [person(1)])

    assert ergebnis['unfilled_count'] == 1


def test_eine_luecke_setzt_die_kette_zurueck():
    """Sieben Tage mit einem freien Tag in der Mitte sind zwei kurze Ketten."""
    tage = [1, 2, 3, 5, 6, 7, 8]
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0) for tag in tage]

    ergebnis = plan(bloecke, [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_die_vorgeschichte_verlaengert_die_kette_ueber_den_monatsanfang():
    """Wer schon vier Tage im Vormonat gearbeitet hat, darf nur noch zwei."""
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0) for tag in range(1, 4)]

    ergebnis = plan(bloecke, [person(1, days_worked_before_month=4)])

    assert ergebnis['unfilled_count'] == 1


def test_ohne_vorgeschichte_bleibt_alles_wie_bisher():
    """Rueckwaertskompatibilitaet: der Schluessel fehlt, die Kette beginnt am
    Monatsersten. Das ist der Zweig, der test_scheduler.py gruen haelt."""
    bloecke = [block(f'2026-09-{tag:02d}', '08:00', '16:00', 0) for tag in range(1, 4)]

    ergebnis = plan(bloecke, [person(1)])

    assert ergebnis['unfilled_count'] == 0
```

`person()` und `block()` werden aus `test_scheduler_split_shifts.py` übernommen — dieselbe Form, und die dortigen Helfer sind bereits erprobt. **Nicht importieren**: zwei Testmodule, die einander importieren, sind schwerer zu lesen als zwanzig Zeilen Wiederholung, und `person()` bekommt hier ein zusätzliches Feld.

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_scheduler_rest_days.py -q`
Erwartet: FAIL bei den vier Tests, die eine Sperre erwarten; die zwei Gegenproben sind grün.

- [ ] **Schritt 3: Umsetzen**

Modulkonstante neben den anderen:

```python
# § 11 Abs. 3 ArbZG grants a replacement rest day within two weeks of every
# Sunday worked - a condition about the *absence* of assignments, which a
# backtracking search handles badly. Never working more than six days in a row
# means a free day at least every seven, which satisfies that window (and the
# eight-week one for public holidays outright). Stricter than the law reads,
# and deliberately so: it is a condition the search can actually carry.
MAX_CONSECUTIVE_DAYS = 6
```

In `_search()`, neben `day_is_free()`:

```python
    def works_on(eid, iso_date):
        """Does this employee already hold a block on that calendar date?

        Reads the two structures Etappe 4 introduced rather than adding a
        third: day_hours for blocks with known times, day_untimed for the ones
        without. Either one means the day is taken.
        """
        key = (eid, iso_date)
        return bool(day_hours.get(key)) or bool(day_untimed.get(key))

    def consecutive_days_with(emp, iso_date):
        """Length of the unbroken run of worked days this assignment would join.

        Counted in *both* directions. Chronological ordering would make a
        leftward count enough, but MOST_CONSTRAINED does not run in calendar
        order and AUTO uses both - counting only leftwards would let a run
        build itself from the back. Same reasoning as rest_period_ok(), which
        checks the day before *and* the day after.

        Leftwards the run ends at the first of the month and carries on into
        days_worked_before_month: the previous month is already saved and
        cannot be replanned, so its tail is a fact rather than a choice.
        """
        d = date.fromisoformat(iso_date)
        run = 1

        cursor = d - timedelta(days=1)
        while cursor.month == d.month and works_on(emp['id'], cursor.isoformat()):
            run += 1
            cursor -= timedelta(days=1)
        if cursor.month != d.month:
            run += emp.get('days_worked_before_month') or 0

        cursor = d + timedelta(days=1)
        while works_on(emp['id'], cursor.isoformat()):
            run += 1
            cursor += timedelta(days=1)

        return run
```

In `eligible_candidates()`, vor der Ruhezeitprüfung:

```python
            if consecutive_days_with(emp, slot['date']) > MAX_CONSECUTIVE_DAYS:
                continue
```

**Achtung:** die Rechtsschleife läuft ohne Monatsgrenze, weil der Folgemonat im Suchlauf ohnehin leer ist — `works_on()` liefert dort `False` und die Schleife endet sofort. Die Linksschleife braucht die Grenze, weil dort die Vorgeschichte anschließt.

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning`
Erwartet: PASS, die 23 Bestandstests unverändert.

- [ ] **Schritt 5: Commit**

```bash
git add backend/scheduler.py backend/test_scheduler_rest_days.py
git commit -m "feat: hoechstens sechs Tage in Folge im Suchkern"
```

---

## Task 2: Sonntagsbudget im Suchkern

**Files:**
- Modify: `backend/scheduler.py`
- Test: `backend/test_scheduler_rest_days.py` (erweitert)

**Interfaces:**
- Produces: `MIN_FREE_SUNDAYS_PER_YEAR = 15`; `emp['sundays_worked_in_year']` optional, Standard 0.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_das_sonntagsbudget_bindet():
    """2026 hat 52 Sonntage; 52 - 15 = 37 duerfen gearbeitet werden. Wer 37
    schon hinter sich hat, bekommt keinen weiteren."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=37)])

    assert ergebnis['unfilled_count'] == 1


def test_ein_sonntag_unter_dem_budget_geht():
    """Gegenprobe: ohne sie waere eine Umsetzung gruen, die jeden Sonntag sperrt."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=36)])

    assert ergebnis['unfilled_count'] == 0


def test_ein_zweiter_block_am_selben_sonntag_kostet_kein_zweites_budget():
    """Ein geteilter Dienst macht aus einem Sonntag keine zwei.

    Beschaeftigungsfrei heisst: kein einziger Block an dem Tag. Ohne diese
    Ausnahme waere ein geteilter Dienst am Sonntag teurer als einer unter der
    Woche - wofuer es im Gesetz keinen Grund gibt.
    """
    ergebnis = plan(
        [block('2026-09-06', '08:00', '12:00', 0),
         block('2026-09-06', '16:00', '20:00', 1)],
        [person(1, sundays_worked_in_year=36)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_zwei_verschiedene_sonntage_kosten_zwei():
    """Gegenprobe zum Test darueber: verschiedene Daten zaehlen sehr wohl
    einzeln."""
    ergebnis = plan(
        [block('2026-09-06', '08:00', '16:00', 0),
         block('2026-09-13', '08:00', '16:00', 0)],
        [person(1, sundays_worked_in_year=36)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_ein_negatives_budget_sperrt_nur_und_wirft_nicht():
    """Wer die Grenze in der Vergangenheit schon gerissen hat, wird nicht
    weiter eingeplant - aber der Planer wirft keinen Fehler ueber Daten, die
    er nicht verursacht hat."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=99)])

    assert ergebnis['unfilled_count'] == 1


def test_werktage_beruehrt_das_budget_nicht():
    ergebnis = plan([block('2026-09-07', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=99)])

    assert ergebnis['unfilled_count'] == 0
```

- [ ] **Schritt 2: Fehlschlag prüfen, umsetzen**

```python
# § 11 Abs. 1 ArbZG: at least 15 Sundays a year must stay free of work.
MIN_FREE_SUNDAYS_PER_YEAR = 15
```

In `_search()`, einmal je Lauf:

```python
    sundays_in_year = sum(
        1 for day in range(1, 366 + 1)
        if (start_of_year := date(year, 1, 1) + timedelta(days=day - 1)).year == year
        and start_of_year.weekday() == 6
    )
```

*(Beim Umsetzen gerne kürzer — entscheidend ist nur, dass 52 bzw. 53 korrekt herauskommt und ein Test die Jahre 2026 und ein 53-Sonntage-Jahr abdeckt.)*

Die Prüfung in `eligible_candidates()`:

```python
            if slot['weekday'] == 6:
                budget = max(0, sundays_in_year - MIN_FREE_SUNDAYS_PER_YEAR
                             - (emp.get('sundays_worked_in_year') or 0))
                # The current date is excluded on purpose: a second block on a
                # Sunday someone already works does not make that Sunday any
                # less worked, so it must not cost a second slot of budget.
                already = sum(1 for (eid, iso) in day_hours
                              if eid == emp['id'] and iso != slot['date']
                              and date.fromisoformat(iso).weekday() == 6)
                if already >= budget:
                    continue
```

**Die Zählung über `day_hours` allein reicht nicht** — Blöcke ohne Zeiten stehen in `day_untimed`. Beim Umsetzen beide Mengen vereinigen, oder besser: eine kleine Hilfsfunktion `worked_dates(eid)`, die beide Schlüsselmengen zusammenführt, und die auch `works_on()` aus Task 1 benutzen kann.

- [ ] **Schritt 3: Tests laufen lassen und committen**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
git add backend/scheduler.py backend/test_scheduler_rest_days.py
git commit -m "feat: mindestens 15 beschaeftigungsfreie Sonntage im Jahr"
```

---

## Task 3: Die Vorgeschichte laden

**Files:**
- Modify: `backend/app.py` — `load_employees_for_scheduling()` (~1228), Aufruf in `generate_schedule_route()`
- Test: `backend/test_api_schedules.py` (erweitert)

**Interfaces:**
- Produces: `load_employees_for_scheduling(cursor, year=None, month=None)`. Ohne Jahr/Monat werden beide Felder auf 0 gesetzt — der bestehende Aufrufer in `replacement_suggestions()` (falls vorhanden) bleibt damit unverändert gültig.

- [ ] **Schritt 1: Der Test, der die Falle aus Spec §5.1 stellt**

```python
def test_zweimal_erzeugen_ergibt_zweimal_denselben_plan(hr_client):
    """Die Vorgeschichte darf den eigenen Monat nicht mitzaehlen.

    generate_schedule_route() loescht die Zuweisungen des Monats erst NACH dem
    Suchlauf; beim Laden der Vorgeschichte stehen sie also noch da. Wuerden sie
    mitgezaehlt, kuerzte der Planer jedem das Sonntagsbudget um Schichten, die
    er ihm gerade wegnimmt - und der zweite Lauf faellt aermer aus als der
    erste.

    Diskriminierend nur, weil der Bedarf Sonntage einschliesst: ohne
    Sonntagsschichten koennte die Vorgeschichte gar nichts falsch machen.
    """
    plan_vorbereiten(hr_client)

    erster = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3,
                                                          'confirm': True}).json
    zweiter = hr_client.post('/schedules/generate', json={'year': 2026, 'month': 3,
                                                          'confirm': True}).json

    assert len(zweiter['assignments']) == len(erster['assignments'])
    assert zweiter['unfilled_count'] == erster['unfilled_count']
```

`plan_vorbereiten()` muss dafür Sonntagsbedarf enthalten — der Helfer setzt heute Montag bis Freitag. Ihn zu erweitern ändert die drei Bestandstests dieser Datei nicht in ihrer Aussage, aber es gehört geprüft.

- [ ] **Schritt 2: Fehlschlag prüfen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_api_schedules.py -q`
Erwartet: der neue Test ist **grün**, solange Task 3 nicht umgesetzt ist (ohne Vorgeschichte kann sie nichts falsch machen). Er wird erst nach Schritt 3 aussagekräftig — deshalb **nach** dem Verdrahten noch einmal laufen lassen und, falls er dann bricht, die Abgrenzung reparieren statt den Test.

- [ ] **Schritt 3: Die Vorgeschichte laden**

```python
def scheduling_history(cursor, employee_id, year, month):
    """The two facts about an employee's past that the planner needs.

    Bounded by the *date range* of the month being planned, never by
    schedule_id: generate_schedule_route() deletes the month's assignments only
    after the search has run, so they are still in the database while this
    loads. Counting them would dock everyone for shifts the same request is
    about to take away. A date inside the target month belongs to that month,
    whatever schedule row it hangs off.
    """
```

Rückgabe `(days_worked_before_month, sundays_worked_in_year)`.

- `days_worked_before_month`: rückwärts vom Letzten des Vormonats, solange ein Tag belegt ist. Höchstens `MAX_CONSECUTIVE_DAYS` weit zählen — mehr braucht niemand zu wissen, und es begrenzt die Schleife.
- `sundays_worked_in_year`: `SELECT DISTINCT date` im Kalenderjahr, außerhalb des Zielmonats, `employee_id = ?`, davon die Sonntage. Der Wochentag lässt sich in SQL nicht dialektfrei bestimmen — die Daten kommen als Liste zurück und werden in Python gefiltert. Bei höchstens 366 Zeilen je Person ist das kein Thema.

- [ ] **Schritt 4: Volle Suite, dann den Test aus Schritt 1 gezielt prüfen**

- [ ] **Schritt 5: Commit**

```bash
git add backend/app.py backend/test_api_schedules.py
git commit -m "feat: der Generator bekommt Vorgeschichte ueber den Monatsrand"
```

---

## Task 4: Warnungen auf dem Handkorrektur-Pfad

**Files:**
- Modify: `backend/app.py` — `constraint_warnings()`
- Modify: `backend/i18n.py`
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Produces: `warn_seventh_consecutive_day`, `warn_sunday_budget_exhausted`.

- [ ] **Schritt 1: Tests schreiben, Fehlschlag prüfen**

Je eine Warnung mit Gegenprobe. Der Handkorrektur-Pfad rechnet gegen gespeicherte Daten und sieht **auch nach vorn** über den Monatsrand — ein Test hält genau das fest, weil es der Unterschied zum Generator ist.

- [ ] **Schritt 2: Umsetzen**

- DE `warn_seventh_consecutive_day`: „{name} käme damit auf {days} Tage in Folge; nach § 11 Abs. 3 ArbZG ist spätestens nach sechs ein Ersatzruhetag fällig"
- DE `warn_sunday_budget_exhausted`: „{name} hätte damit nur noch {free} freie Sonntage in {year}; § 11 Abs. 1 ArbZG verlangt mindestens 15"

- [ ] **Schritt 3: Volle Suite und Commit**

---

## Task 5: Dokumentation

**Files:**
- Modify: `README.md` — der Abschnitt zum Arbeitszeitrecht um beide Regeln; die Liste des Nichtgeprüften kürzen; `Project Structure` um die neue Testdatei; Testzahl im Status
- Modify: `docs/HANDOFF.md` — 5b eintragen, 5d (Feiertagskalender) als neues Teilstück aufnehmen, neue zurückgestellte Befunde

**Ausdrücklich hervorheben:** dass die Sechstageregel strenger ist als § 11 Abs. 3, und dass der Generator erstmals Daten außerhalb seines Monats liest.

- [ ] **Schritt 1: README**
- [ ] **Schritt 2: HANDOFF**
- [ ] **Schritt 3: Commit**

---

## Selbstdurchsicht

**Spec-Abdeckung:**

| Spec-Abschnitt | Aufgabe |
|---|---|
| §2 Sechstageregel | Task 1 |
| §5 Vorgeschichte, §5.1 die Falle | Task 3 |
| §5.2 ein Sonntag zählt einmal | Task 2, dritter Test |
| §6.1 Kette in beide Richtungen | Task 1, dritter Test |
| §6.2 Sonntagsbudget, negatives Budget | Task 2 |
| §7 Handkorrektur | Task 4 |
| §9 Tests | in jeder Aufgabe |
| §3, §4, §8 — was nicht gebaut wird | Task 5 (Dokumentation) |

**Offen gelassen:** Task 2 Schritt 2 skizziert die Zählung der Sonntage über `day_hours` und merkt selbst an, dass `day_untimed` fehlt. Das ist Absicht — die saubere Form ist eine gemeinsame Hilfsfunktion mit `works_on()` aus Task 1, und wie die genau aussieht, entscheidet sich am Code der vorigen Aufgabe.
