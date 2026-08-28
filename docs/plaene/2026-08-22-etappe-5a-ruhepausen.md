# Etappe 5a — Ruhepausen und Netto-Arbeitszeit: Umsetzungsplan

**Ziel:** Das Tool kennt Ruhepausen nach § 4 ArbZG und rechnet Arbeitszeit netto — die Spanne minus der Pause, wie § 2 Abs. 1 sie definiert.

**Architektur:** Eine nullbare Spalte `shift_assignments.break_minutes`, deren `NULL` die gesetzliche Mindestpause für die Blocklänge bedeutet. Zwei reine Funktionen in `scheduler.py` lösen die zirkuläre Ableitung der Mindestpause auf. Fünf Stellen, die heute Arbeitszeit rechnen, rechnen danach netto; alle Stellen, die Anwesenheit rechnen, bleiben unverändert.

**Tech Stack:** Python 3.13/3.14, Flask, SQLite lokal / Postgres in Produktion über die Dialektschicht in `backend/db.py` (kein ORM). Frontend React 19 + Vite, Tests pytest und Vitest.

**Spec:** [`docs/entwuerfe/2026-08-22-etappe-5a-ruhepausen-design.md`](../specs/2026-08-22-etappe-5a-ruhepausen-design.md)

## Globale Randbedingungen

- **Kein literales `?` in SQL, auch nicht in Kommentaren.** `_PostgresCursor` ersetzt es bedingungslos durch `%s`.
- **Keine Semikolons in SQL-Kommentaren.**
- **`ADD COLUMN` gehört in eine `.py`-Migration mit `table_columns()`-Wächter**, Muster aus `0001_baseline.py` und `0008_max_daily_hours.py`. Rundlauftest up → down → up ist Pflicht.
- **Die 23 Tests in `backend/test_scheduler.py` bleiben unverändert.** Werden sie rot, ist die Änderung falsch, nicht der Test.
- **Kommentarsprache folgt der Datei.** `app.py`, `db.py`, `scheduler.py`, `test_scheduler.py` englisch; `block_planner.py`, `coverage_model.py`, `security.py`, `timeutil.py`, `migrations.py` und die neueren Testdateien deutsch.
- **Commit-Nachrichten deutsch, ohne Umlaute.** README englisch.
- **Vor jedem Commit die Frage:** *Würde dieser Test fehlschlagen, wenn ich das Feature lösche?* Fünf wertlose Tests gab es im Projekt schon, einer davon in Etappe 4.
- **Alle neuen Texte in beiden Sprachen**, `backend/i18n.py` und `frontend/src/i18n/translations.js`.
- **Testlauf:** `cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning`. Frontend: `cd frontend && npm test -- --run`.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `backend/test_working_time.py` | Die Schwellen von `legal_break_minutes()` und die Nettorechnung | **neu** |
| `backend/migrations/0009_break_minutes.py` | Spalte `shift_assignments.break_minutes` | **neu** |
| `backend/scheduler.py` | Die zwei neuen Funktionen; `working_minutes` im Slot; drei Grenzen auf netto | geändert |
| `backend/block_planner.py` | `working_minutes` im Monatsaufbau | geändert |
| `backend/app.py` | `break_minutes` lesen/schreiben, zwei Grenzen auf netto, eine neue Warnung | geändert |
| `frontend/src/components/ShiftCell.jsx` | Pause je Person, Nettozeit in der Anzeige | geändert |

---

## Aufgabe 1: Die zwei Rechenfunktionen

Der Kern. § 4 bemisst die Pause an der Arbeitszeit, die Arbeitszeit ist die Spanne minus der Pause — die Ableitung ist zirkulär und wird über „die kleinste Pause, die für die dabei herauskommende Arbeitszeit ausreicht" aufgelöst.

**Files:**
- Modify: `backend/scheduler.py`, direkt hinter `shift_duration_minutes()` (Zeile 116)
- Test: `backend/test_working_time.py` (neu)

**Interfaces:**
- Produces:
  ```python
  legal_break_minutes(duration_minutes) -> int      # 0 | 30 | 45
  net_working_minutes(duration_minutes, break_minutes) -> int
  ```
  `break_minutes = None` heißt „die gesetzliche Mindestpause"; `net_working_minutes(None, ...)` gibt `None` zurück, damit Aufrufer ohne bekannte Zeiten weiterlaufen wie bisher.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
"""Arbeitszeit und Ruhepause: die Rechnung hinter Paragraph 2 Abs. 1 und Paragraph 4 ArbZG.

Reine Rechentests ohne Datenbank. Die interessanten Faelle sind die Kanten -
und die liegen nicht dort, wo das Gesetz seine Zahlen nennt.
"""

import pytest

from scheduler import legal_break_minutes, net_working_minutes

STUNDE = 60


@pytest.mark.parametrize('spanne, erwartet', [
    (4 * STUNDE, 0),
    (6 * STUNDE, 0),            # genau sechs Stunden sind NICHT "mehr als sechs"
    (6 * STUNDE + 1, 30),
    (7 * STUNDE, 30),
    (9 * STUNDE, 30),
    (9 * STUNDE + 30, 30),      # 9:30 minus 30 Min = genau 9:00 Arbeitszeit
    (9 * STUNDE + 31, 45),      # 9:31 minus 30 Min waeren 9:01 - zu viel fuer 30
    (12 * STUNDE, 45),
])
def test_gesetzliche_mindestpause(spanne, erwartet):
    assert legal_break_minutes(spanne) == erwartet


def test_die_kante_liegt_bei_neuneinhalb_stunden_nicht_bei_neun():
    """Der Fall, an dem eine naive Umsetzung falsch liegt.

    Wer die Schwelle des Gesetzes (mehr als neun Stunden) direkt auf die
    Spanne anwendet, springt bei 9:01 auf 45 Minuten. Richtig ist 9:31: bei
    9:30 Spanne bleiben nach 30 Minuten Pause genau neun Stunden Arbeitszeit,
    und neun Stunden sind nicht "mehr als neun".
    """
    assert legal_break_minutes(9 * STUNDE + 1) == 30
    assert legal_break_minutes(9 * STUNDE + 30) == 30
    assert legal_break_minutes(9 * STUNDE + 31) == 45


def test_die_zurueckgegebene_pause_ist_fuer_ihr_eigenes_ergebnis_ausreichend():
    """Die Eigenschaft, aus der sich die Schwellen ueberhaupt ergeben.

    Diskriminierend gegenueber jeder fest verdrahteten Tabelle: geprueft wird
    nicht, dass bestimmte Zahlen herauskommen, sondern dass das Ergebnis die
    Bedingung erfuellt, aus der es abgeleitet ist.
    """
    for spanne in range(0, 16 * STUNDE + 1):
        pause = legal_break_minutes(spanne)
        arbeitszeit = spanne - pause
        gefordert = (0 if arbeitszeit <= 6 * STUNDE
                     else 30 if arbeitszeit <= 9 * STUNDE else 45)
        assert pause >= gefordert, (spanne, pause, arbeitszeit, gefordert)


def test_kleinere_pause_wuerde_nicht_reichen():
    """Gegenprobe: die zurueckgegebene Pause ist nicht nur ausreichend,
    sondern auch die kleinste ausreichende. Ohne diesen Test waere ein
    konstantes 45 fuer alles ebenfalls gruen."""
    for spanne in range(1, 16 * STUNDE + 1):
        pause = legal_break_minutes(spanne)
        if pause == 0:
            continue
        kleiner = 0 if pause == 30 else 30
        arbeitszeit = spanne - kleiner
        gefordert = (0 if arbeitszeit <= 6 * STUNDE
                     else 30 if arbeitszeit <= 9 * STUNDE else 45)
        assert kleiner < gefordert, (spanne, kleiner, arbeitszeit, gefordert)


def test_netto_zieht_die_gesetzliche_pause_ab_wenn_keine_gesetzt_ist():
    assert net_working_minutes(8 * STUNDE, None) == 8 * STUNDE - 30


def test_netto_nimmt_die_gesetzte_pause_auch_wenn_sie_kleiner_ist():
    """HR darf weniger eintragen - dann wird auch weniger abgezogen. Gewarnt
    wird darueber an anderer Stelle (constraint_warnings), gerechnet wird mit
    dem, was dasteht."""
    assert net_working_minutes(8 * STUNDE, 0) == 8 * STUNDE
    assert net_working_minutes(8 * STUNDE, 60) == 7 * STUNDE


def test_netto_ohne_bekannte_dauer_bleibt_unbekannt():
    """Rueckwaertskompatibel zu Aufrufern, die nur mit Schichtzahlen arbeiten."""
    assert net_working_minutes(None, None) is None


def test_netto_wird_nicht_negativ():
    """Eine Pause laenger als der Block ist Unsinn, darf aber keine negative
    Arbeitszeit erzeugen - die wuerde sich durch die Wochensumme fressen."""
    assert net_working_minutes(2 * STUNDE, 180) == 0
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_working_time.py -q`
Erwartet: FAIL mit `ImportError: cannot import name 'legal_break_minutes'`.

- [ ] **Schritt 3: Umsetzen**

```python
# § 4 ArbZG, resolved onto the span rather than onto working time.
#
# The law measures the break against the *working* time, and working time is
# the span minus the break - so read literally the rule chases its own tail: a
# 6:30 span is 6:30 of work without a break, which is "more than six hours" and
# demands 30 minutes, which brings the work down to exactly 6:00, which demands
# nothing. Resolved by asking which break is sufficient for the working time it
# itself produces, and taking the smallest such break. On the span that lands
# on 6:00 and 9:30 - note 9:30, not 9:00: at 9:30 a 30-minute break still
# leaves exactly nine hours, and nine hours is not "more than nine".
BREAK_THRESHOLDS = ((6 * 60, 0), (9 * 60 + 30, 30))
LONG_SHIFT_BREAK_MINUTES = 45


def legal_break_minutes(duration_minutes):
    """The shortest break § 4 ArbZG allows for a block of this span."""
    if duration_minutes is None:
        return 0
    for limit, minutes in BREAK_THRESHOLDS:
        if duration_minutes <= limit:
            return minutes
    return LONG_SHIFT_BREAK_MINUTES


def net_working_minutes(duration_minutes, break_minutes):
    """Working time in the sense of § 2 Abs. 1 ArbZG: the span without the break.

    `break_minutes` None means "not separately agreed", which is read as the
    legal minimum for this span - the law requires it, so a plan that did not
    subtract it would be claiming someone works eight hours straight through.
    A stored value wins, including a zero: that is HR saying something, and
    constraint_warnings() is where it gets questioned, not here.
    """
    if duration_minutes is None:
        return None
    taken = legal_break_minutes(duration_minutes) if break_minutes is None else break_minutes
    return max(0, duration_minutes - taken)
```

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_working_time.py -q`
Erwartet: PASS.

- [ ] **Schritt 5: Commit**

```bash
git add backend/scheduler.py backend/test_working_time.py
git commit -m "feat: gesetzliche Mindestpause und Netto-Arbeitszeit berechnen"
```

---

## Aufgabe 2: Die Spalte und der Weg durch die API

**Files:**
- Create: `backend/migrations/0009_break_minutes.py`
- Modify: `backend/app.py` — `fetch_schedule()` (~1405), `update_assignment()` (~1930), der INSERT in `generate_schedule_route()`
- Test: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`, `backend/test_api_assignment_times.py`

**Interfaces:**
- Produces: `shift_assignments.break_minutes INTEGER NULL`; je Zuweisung im JSON `break_minutes` (gesetzt oder `null`) und `effective_break_minutes` (wirksam).

- [ ] **Schritt 1: Rundlauftest schreiben, Fehlschlag prüfen**

Nach dem Muster von `test_0008_laeuft_nach_der_eigenen_ruecknahme_wieder_vorwaerts` in `test_migrations.py`. Zusätzlich ein Test, dass Bestandszeilen `NULL` behalten — **nicht** 0, das ist der ganze Punkt der Nullbarkeit.

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_migrations.py -k 0009 -q`

- [ ] **Schritt 2: Migration schreiben**

Nach dem Muster von `0008_max_daily_hours.py`: `.py`, `table_columns()`-Wächter, `down()` lässt die Spalte stehen mit derselben Begründung. Der Modulkommentar hält fest, warum nullbar und nicht `NOT NULL DEFAULT 0` — siehe Spec §5.

- [ ] **Schritt 3: Lesen — `fetch_schedule()`**

`a = dict(row)` bringt `break_minutes` von selbst mit, sobald die Spalte existiert. Zu ergänzen ist nur die aufgelöste Größe, **nachdem** die Zeiten aufgelöst sind (die Pause hängt an der endgültigen Spanne):

```python
        # The break the block actually runs on: what someone entered, or the
        # legal minimum for the hours this assignment ended up with. Resolved
        # after the three time layers above, because the minimum depends on the
        # span they produce - the same shape as assignment_time_set/
        # time_overridden, so the browser never re-derives a rule.
        a['effective_break_minutes'] = (
            a['break_minutes'] if a['break_minutes'] is not None
            else legal_break_minutes(shift_duration_minutes(a['start_time'], a['end_time']))
            if a['start_time'] and a['end_time'] else None
        )
```

- [ ] **Schritt 4: Schreiben — `update_assignment()`**

`break_minutes` aus dem Rumpf, validiert als nicht-negative ganze Zahl oder `None`. **Auf jedem PUT geschrieben**, dieselbe „fehlt heißt leer"-Semantik wie `start_time`/`end_time` daneben — Fallstrick 14. Der Kommentar dort nennt die Zeiten; er wird um die Pause erweitert, nicht danebengeschrieben.

Der Generator schreibt `break_minutes` **nicht**: seine Blöcke bekommen die Mindestpause über den `NULL`-Standard, und genau das ist die richtige Annahme.

- [ ] **Schritt 5: API-Tests**

```python
def test_pause_ohne_angabe_ist_die_gesetzliche(hr_client):
    """Ein Achtstundenblock laeuft auf 30 Minuten, ohne dass jemand etwas eintraegt."""
    ...
    assert zuweisung['break_minutes'] is None
    assert zuweisung['effective_break_minutes'] == 30


def test_gesetzte_pause_schlaegt_die_gesetzliche(hr_client):
    ...
    assert zuweisung['break_minutes'] == 60
    assert zuweisung['effective_break_minutes'] == 60


def test_pause_faellt_weg_wenn_der_put_sie_nicht_mitschickt(hr_client):
    """Fallstrick 14: PUT /assignments/<id> schreibt vollstaendig.

    Kein Schoenheitsfehler, sondern die dokumentierte Semantik - der Test
    haelt sie fest, damit sie nicht versehentlich kippt.
    """
    ...
```

- [ ] **Schritt 6: Volle Suite und Commit**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
git add backend/migrations/0009_break_minutes.py backend/app.py backend/test_migrations.py backend/test_migrations_postgres.py backend/test_api_assignment_times.py
git commit -m "feat: Ruhepause je Zuweisung, nullbar mit gesetzlichem Standard"
```

---

## Aufgabe 3: Netto-Arbeitszeit im Suchkern

**Files:**
- Modify: `backend/scheduler.py` — `build_slots()` (~155), `eligible_candidates()` (~446, ~454), `backtrack()` (~512, ~531)
- Modify: `backend/block_planner.py` — `build_month_blocks()` (~493)
- Test: `backend/test_scheduler_split_shifts.py` (erweitert), `backend/test_api_coverage.py` (erweitert)

**Interfaces:**
- Consumes: `net_working_minutes()` aus Aufgabe 1.
- Produces: Slots tragen zusätzlich `working_minutes`. `duration_minutes` **behält seine Bedeutung** — die Spanne. Kein Umdeuten.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `test_scheduler_split_shifts.py`, weil dort die Tagesgrenze schon zu Hause ist:

```python
def test_die_tagesgrenze_rechnet_netto():
    """Zwei Bloecke von je sieben Stunden sind 14 Stunden Anwesenheit, aber nur
    13 Stunden Arbeitszeit - je 30 Minuten gesetzliche Pause gehen ab.

    Bei einer Grenze von 13 Stunden entscheidet genau das: brutto gerechnet
    bliebe ein Block offen, netto gehen beide.
    """
    ergebnis = plan(
        [block('2026-09-01', '06:00', '13:00', 0),
         block('2026-09-01', '14:00', '21:00', 1)],
        [person(1, max_daily_hours=13)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_die_tagesgrenze_bindet_trotzdem():
    """Gegenprobe: dieselben Bloecke, Grenze zwoelf Stunden. Auch netto sind es
    dreizehn - einer bleibt offen. Ohne diesen Test waere eine Umsetzung gruen,
    die die Grenze gar nicht mehr prueft."""
    ergebnis = plan(
        [block('2026-09-01', '06:00', '13:00', 0),
         block('2026-09-01', '14:00', '21:00', 1)],
        [person(1, max_daily_hours=12)],
    )

    assert ergebnis['unfilled_count'] == 1
```

Und in `test_api_coverage.py` die wichtigste Gegenprobe der ganzen Etappe:

```python
def test_die_pause_erzeugt_keine_deckungsluecke(hr_client):
    """Anwesenheit und Arbeitszeit sind zwei verschiedene Groessen.

    Wer 08:00-16:00 im Plan steht, deckt diese acht Stunden ab - auch wenn
    darin eine halbe Stunde Pause steckt. Wuerde die Deckungsrechnung auf
    netto umgestellt, entstuende hier eine Luecke von 30 Minuten irgendwo im
    Band, und niemand koennte sie je schliessen.
    """
    ...
    assert antwort.json['coverage_gaps'] == []
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest test_scheduler_split_shifts.py -k netto -q`
Erwartet: FAIL bei `test_die_tagesgrenze_rechnet_netto` (ein Block bleibt offen). Der Deckungstest muss von Anfang an **grün** sein — er sichert ab, dass Aufgabe 3 ihn nicht kaputtmacht.

- [ ] **Schritt 3: `working_minutes` in die Slots**

In `build_slots()` neben `duration_minutes`:

```python
                    'working_minutes': net_working_minutes(duration_minutes, None),
```

Ebenso in `block_planner.build_month_blocks()`. Beide setzen `None` als Pause: die Blöcke des Generators tragen keine, und `NULL` heißt die gesetzliche.

- [ ] **Schritt 4: Die drei Stellen im Suchkern**

`eligible_candidates()` und `backtrack()` lesen `slot['working_minutes']` statt `slot['duration_minutes']` — je zweimal in `eligible_candidates()` (Tages- und Wochengrenze) und zweimal in `backtrack()` (Aufbau und Rücknahme). **Fünf Vorkommen von `slot['duration_minutes']` insgesamt**; `grep -n "duration_minutes" backend/scheduler.py` zeigt sie, und danach darf keines mehr in einer Grenzenrechnung stehen.

- [ ] **Schritt 5: Tests laufen lassen**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning`
Erwartet: PASS, die 23 Bestandstests unverändert (sie liefern keine Zeiten, also `working_minutes = None`, also keine Prüfung).

- [ ] **Schritt 6: Commit**

```bash
git add backend/scheduler.py backend/block_planner.py backend/test_scheduler_split_shifts.py backend/test_api_coverage.py
git commit -m "feat: Tages- und Wochengrenze rechnen mit Netto-Arbeitszeit"
```

---

## Aufgabe 4: Netto und Warnung auf dem Handkorrektur-Pfad

**Files:**
- Modify: `backend/app.py` — `constraint_warnings()`, Tagesgrenze (~1981) und Wochenstunden (~2010)
- Modify: `backend/i18n.py`
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Produces: i18n-Schlüssel `warn_break_below_minimum`.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_pause_unter_der_gesetzlichen_dauer_warnt(hr_client):
    """Der einzige Ort, an dem Paragraph 4 ueberhaupt verletzt werden kann.

    Solange break_minutes NULL bleibt, ist jeder Plan per Konstruktion konform.
    Erst wer ausdruecklich weniger eintraegt, bekommt eine Warnung - und ein
    Verbot ist es nicht, HR bleibt der Chef.
    """
    ...
    assert any('Pause' in w for w in warnungen)


def test_ausreichende_pause_warnt_nicht(hr_client):
    """Gegenprobe: 30 Minuten bei acht Stunden sind genau die gesetzliche
    Dauer und duerfen nicht melden."""
    ...
    assert not any('Pause' in w for w in warnungen)


def test_die_wochenstunden_rechnen_netto(hr_client):
    """Fuenf Achtstundentage sind 40 Stunden Anwesenheit, aber 37,5 Stunden
    Arbeitszeit. Bei einem Wochenziel von 38 Stunden entscheidet genau das."""
    ...
```

- [ ] **Schritt 2: Fehlschlag prüfen, umsetzen**

Beide Summen in `constraint_warnings()` laufen über `net_working_minutes(shift_duration_minutes(start, end), break_minutes)` statt über `shift_duration_minutes()` allein. Die Zeilen, die dort gelesen werden, bringen `break_minutes` bereits mit (`SELECT` erweitern, wo nötig).

Die neue Warnung:

- DE: „{name} hätte bei {hours:.1f} Std. nur {minutes} Min. Pause; nach § 4 ArbZG sind mindestens {required} Min. vorgeschrieben."
- EN: „{name} would get only {minutes} min of break for {hours:.1f}h; § 4 ArbZG requires at least {required} min."

- [ ] **Schritt 3: Volle Suite und Commit**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -q -W error::DeprecationWarning
git add backend/app.py backend/i18n.py backend/test_api_assignment_times.py
git commit -m "feat: Handkorrektur rechnet netto und warnt vor zu kurzer Pause"
```

---

## Aufgabe 5: Frontend

**Files:**
- Modify: `frontend/src/components/ShiftCell.jsx`, `frontend/src/pages/SchedulePage.jsx` (der `reassign`-Aufruf muss die Pause mitschicken — Fallstrick 14)
- Modify: `frontend/src/i18n/translations.js`
- Test: `frontend/src/components/ShiftCell.test.jsx` (erweitert)

- [ ] **Schritt 1: Test schreiben**

```jsx
it('zeigt eine abweichende Pause an', () => { ... })

it('zeigt eine Pause, die der gesetzlichen entspricht, nicht an', () => {
  // Dieselbe Zurueckhaltung wie bei den Zeiten: sonst steht auf jeder Zeile
  // dieselbe Zahl.
})
```

- [ ] **Schritt 2: Umsetzen**

Die Pause dort, wo schon die individuelle Zeit bearbeitet wird (`AssignmentSlot`). Angezeigt nur, wenn `break_minutes !== null`. Die Zeitangabe nennt bei einer wirksamen Pause über 0 zusätzlich die Nettozeit, damit „08:00–16:00" nicht wie acht Stunden Arbeit aussieht.

**`SchedulePage.reassign()` muss `break_minutes` mitschicken**, sonst löscht jeder Mitarbeitertausch die Pause — dieselbe Falle, die dort schon für die Zeiten gelöst ist.

- [ ] **Schritt 3: Tests, Lint, Build, Commit**

```bash
cd frontend && npm test -- --run && npx eslint src && npm run build
git add frontend/src
git commit -m "refactor: Ruhepause je Person sichtbar und bearbeitbar"
```

---

## Aufgabe 6: Dokumentation

**Files:**
- Modify: `README.md` — den Abschnitt „Split shifts and working-time law" um die Pausen ergänzen und § 4 aus der Liste des Nichtgeprüften herausnehmen (bis auf Satz 3); die Netto-Umstellung bei „Part-time / weekly hours" und bei der Tagesgrenze nennen; `Project Structure` um `test_working_time.py`; Migrationsliste um `0009`
- Modify: `docs/HANDOFF.md` — Etappe 5a eintragen, die Dreiteilung von Etappe 5 festhalten, neue zurückgestellte Befunde

**Die Netto-Umstellung gehört ausdrücklich hervorgehoben**: sie lockert bestehende Grenzen, ohne dass jemand etwas angefasst hat.

- [ ] **Schritt 1: README**
- [ ] **Schritt 2: HANDOFF**
- [ ] **Schritt 3: Commit**

---

## Selbstdurchsicht

**Spec-Abdeckung:**

| Spec-Abschnitt | Aufgabe |
|---|---|
| §5 Migration `0009` | Aufgabe 2 |
| §6 Netto/brutto, fünf Stellen | Aufgabe 3 (drei), Aufgabe 4 (zwei) |
| §6.1 `working_minutes` neben `duration_minutes` | Aufgabe 3 |
| §6.2 die zwei Funktionen und die 9:30-Kante | Aufgabe 1 |
| §7 Generator setzt nichts, Handkorrektur warnt | Aufgabe 2 Schritt 4, Aufgabe 4 |
| §8 API | Aufgabe 2 |
| §9 Frontend | Aufgabe 5 |
| §10 Tests | in jeder Aufgabe; die Deckungs-Gegenprobe in Aufgabe 3 |
| §13 Risiko „Anwesenheit und Arbeitszeit verwechselt" | Aufgabe 3 Schritt 1, zweiter Test |

**Reihenfolge:** Aufgabe 1 muss zuerst, alles andere baut auf den zwei Funktionen. Aufgabe 3 und 4 sind unabhängig voneinander. Aufgabe 5 braucht Aufgabe 2.

**Bewusst offen gelassen:** Aufgabe 4 Schritt 2 sagt „`SELECT` erweitern, wo nötig" statt die Abfragen auszuschreiben — welche der drei Abfragen in `constraint_warnings()` `break_minutes` schon mitbringt, entscheidet sich am Code, und alle drei aufzuzählen hieße den Bestand abzuschreiben.
