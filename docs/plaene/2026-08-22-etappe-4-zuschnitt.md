# Etappe 4 — Zuschnitt im Planer: Umsetzungsplan

**Ziel:** Der Planer baut seine Blöcke aus `coverage_requirements` statt aus `shift_requirements`, schneidet sie bei Bedarf auf die Arbeitszeitfenster der Mitarbeiter zu, und erlaubt den geteilten Dienst innerhalb der Grenzen des Arbeitszeitgesetzes.

**Architektur:** Zweistufig. Stufe 1 (neu, `backend/block_planner.py`) ist deterministische Rechenlogik ohne Datenbank: aus Bedarfsbändern, Vorlagen und Fenstern wird eine Blockliste, strukturgleich zu dem, was `build_slots()` heute liefert. Stufe 2 ist der bestehende Backtracking-Suchkern, an drei eng umrissenen Stellen erweitert (Überschneidung statt Tagesbelegung, Ruhezeit zwischen Arbeitstagen, tägliche Höchstarbeitszeit).

**Tech Stack:** Python 3.13/3.14, Flask, SQLite lokal / Postgres in Produktion über die handgeschriebene Dialektschicht in `backend/db.py` (kein ORM). Frontend React 19 + Vite, Tests pytest und Vitest.

**Spec:** [`docs/entwuerfe/2026-08-22-etappe-4-zuschnitt-design.md`](../specs/2026-08-22-etappe-4-zuschnitt-design.md)

## Globale Randbedingungen

- **Kein literales `?` in SQL, auch nicht in Kommentaren.** `_PostgresCursor` ersetzt es bedingungslos durch `%s`.
- **Keine Semikolons in SQL-Kommentaren** — sie zerteilen die Datei am naiven Splitter.
- **`ADD COLUMN` gehört in eine `.py`-Migration mit `table_columns()`-Wächter**, Muster aus `0001_baseline.py`. Rundlauftest up → down → up ist Pflicht.
- **Die 23 Tests in `backend/test_scheduler.py` bleiben unverändert.** Werden sie rot, ist die Änderung falsch, nicht der Test.
- **Die Tabellenliste in `test_migrations.py` ist absichtlich fest verdrahtet.** Nicht in eine Ableitung zurückverwandeln.
- **Kommentarsprache folgt der Datei.** `app.py`, `db.py`, `scheduler.py`, `test_scheduler.py` englisch; `coverage_model.py`, `security.py`, `timeutil.py`, `migrations.py` und die neueren Testdateien deutsch. `block_planner.py` ist deutsch (Nachbar von `coverage_model.py`). Zwei Sprachen in *einer* Datei sind der Fehler.
- **Commit-Nachrichten deutsch, ohne Umlaute** (Projektkonvention: „Uebergabe", „Oeffnungszeiten"). README englisch.
- **Vor jedem Commit die Frage:** *Würde dieser Test fehlschlagen, wenn ich das Feature lösche?* Vier wertlose Tests gab es im Projekt schon.
- **Zwei gleichnamige Testfunktionen im selben Modul überschreiben sich in Python still.** `pytest --collect-only` zeigt es.
- **Alle neuen Texte in beiden Sprachen**, `backend/i18n.py` und `frontend/src/i18n/translations.js`.
- **Testlauf lokal:** `cd backend && python -m pytest -q -W error::DeprecationWarning`. Frontend: `cd frontend && npm test -- --run`.

---

## Dateistruktur

| Datei | Verantwortung | Status |
|---|---|---|
| `backend/block_planner.py` | Stufe 1: Bedarfsbänder + Vorlagen + Fenster → Blockliste. Reine Rechenlogik, kein DB-Zugriff | **neu** |
| `backend/test_block_planner.py` | Tests dazu | **neu** |
| `backend/test_scheduler_split_shifts.py` | Geteilter Dienst, Tagesgrenze, Ruhezeit über Tagesgrenzen | **neu** |
| `backend/migrations/0008_max_daily_hours.py` | Spalte `employees.max_daily_hours` | **neu** |
| `backend/scheduler.py` | Stufe 2: die drei Eingriffe, Ergebnisaufbau | geändert |
| `backend/app.py` | Datenladen für Stufe 1, Generator-Persistenz, `max_daily_hours`, neue Route, neue Warnungen | geändert |
| `backend/coverage_model.py` | unverändert — wird nur importiert | — |
| `frontend/src/components/ShiftCell.jsx` | Zeitgruppen innerhalb einer Zelle | geändert |
| `frontend/src/components/CalendarView.jsx` | Gruppierung nach (Vorlage, Start, Ende) | geändert |
| `frontend/src/pages/ShiftTypes.jsx` | Bedarfszahlen entfernen | geändert |
| `frontend/src/pages/Employees.jsx` | Feld `max_daily_hours` | geändert |

Die Reihenfolge der Aufgaben ist so gewählt, dass jede für sich lauffähig und grün ist: erst die beiden Vorarbeiten (unabhängig vom Rest), dann das Schema, dann Stufe 1 (ohne Anschluss, rein testbar), dann der Anschluss, dann Stufe 2, dann Handkorrektur und Frontend.

---

## Aufgabe 1: Route für eigene Arbeitszeitfenster

Vorarbeit 1 aus Spec §10. Heute hängen die Fenster ausschließlich an `PUT /employees/<id>` mit `@hr_required` — ein Mitarbeiter kann seine eigenen Arbeitszeiten nicht einsehen. Etappe 4 macht die Fenster zur zentralen Steuergröße der Planung; das wird damit unhaltbar.

**Files:**
- Modify: `backend/app.py` — neue Route hinter `serialize_employee()` (Zeile 586–627)
- Test: `backend/test_api_availability.py`

**Interfaces:**
- Consumes: `require_self_or_hr(employee_id)` (`app.py:217`), `replace_employee_constraints(connection, employee_id, data)` (`app.py:673`) — dessen Fenster-Zweig (Zeilen 696–742) ist die einzige Schreiblogik und wird **nicht** dupliziert.
- Produces: `GET /employees/<id>/availability` → `{availability_mode, availability: [...]}`; `PUT` mit demselben Rumpf.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_employee_reads_own_availability(client, hr_headers):
    employee_id = _create_employee_with_window(client, hr_headers)
    headers = _login_as_employee(client, employee_id)

    response = client.get(f'/employees/{employee_id}/availability', headers=headers)

    assert response.status_code == 200
    assert response.get_json()['availability_mode'] == 'windows'
    assert response.get_json()['availability'][0]['start_time'] == '08:00'


def test_employee_cannot_read_someone_elses_availability(client, hr_headers):
    other_id = _create_employee_with_window(client, hr_headers)
    mine_id = _create_employee_with_window(client, hr_headers, name='Zweiter')
    headers = _login_as_employee(client, mine_id)

    response = client.get(f'/employees/{other_id}/availability', headers=headers)

    assert response.status_code == 403


def test_employee_cannot_write_own_availability(client, hr_headers):
    employee_id = _create_employee_with_window(client, hr_headers)
    headers = _login_as_employee(client, employee_id)

    response = client.put(
        f'/employees/{employee_id}/availability',
        json={'availability_mode': 'anytime', 'availability': []},
        headers=headers,
    )

    assert response.status_code == 403
```

Der dritte Test ist die eigentliche Sicherheitsaussage: **lesen** darf man sich selbst, **schreiben** bleibt HR. `require_self_or_hr` deckt nur das Lesen ab.

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_api_availability.py -k availability_ -v`
Erwartet: FAIL mit 404 (Route existiert nicht).

- [ ] **Schritt 3: Route umsetzen**

```python
@app.route('/employees/<int:employee_id>/availability', methods=['GET'])
@login_required
def get_employee_availability(employee_id):
    """An employee's own working-time windows, readable by them and by HR.

    Spec §6 asked for this route from the start; the windows ended up hanging
    off PUT /employees/<id> (@hr_required) instead, which meant the one person
    the windows are about could not see them. Etappe 4 turns the windows into
    what the planner cuts blocks against, so that gap stops being cosmetic.

    Writing stays HR-only: an employee announcing their own availability is a
    different feature (a request that someone approves), not this one.
    """
    denied = require_self_or_hr(employee_id)
    if denied:
        return denied

    cursor = get_db().cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    payload = serialize_employee(cursor, row)
    return jsonify({
        'availability_mode': payload['availability_mode'],
        'availability': payload['availability'],
    })


@app.route('/employees/<int:employee_id>/availability', methods=['PUT'])
@hr_required
def put_employee_availability(employee_id):
    """Replace one employee's windows without touching the rest of their record.

    Same replace-completely semantics as the constraint lists on
    PUT /employees/<id>, and the same writer: replace_employee_constraints()
    is the only place that validates and stores windows, so this route hands
    the payload straight to it rather than growing a second copy of that
    validation.
    """
    connection = get_db()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM employees WHERE id = ?', (employee_id,))
    if not cursor.fetchone():
        return jsonify({'message': t(g.lang, 'employee_not_found')}), 404

    data = request.get_json(silent=True) or {}
    mode = data.get('availability_mode') or 'anytime'
    if mode not in ('anytime', 'windows'):
        return jsonify({'message': t(g.lang, 'availability_mode_invalid')}), 400

    try:
        replace_employee_constraints(connection, employee_id, {
            'availability': data.get('availability') or [],
        })
    except ValueError as error:
        return jsonify({'message': str(error)}), 400

    cursor.execute('UPDATE employees SET availability_mode = ? WHERE id = ?', (mode, employee_id))
    connection.commit()

    cursor.execute('SELECT * FROM employees WHERE id = ?', (employee_id,))
    payload = serialize_employee(cursor, cursor.fetchone())
    return jsonify({
        'availability_mode': payload['availability_mode'],
        'availability': payload['availability'],
    })
```

**Achtung:** `replace_employee_constraints()` löscht *alle* Constraint-Listen des Mitarbeiters, bevor es neu schreibt. Vor dem Umsetzen prüfen, ob es sich auf den `availability`-Zweig beschränken lässt, ohne `unavailable_weekdays` und `allowed_shift_types` mitzulöschen. Wenn nicht: den Fenster-Zweig (Zeilen 696–742) in eine eigene Funktion `replace_employee_availability(connection, employee_id, entries)` herausziehen und von beiden Aufrufern nutzen. Das ist der DRY-korrekte Weg und vermutlich ohnehin nötig.

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && python -m pytest test_api_availability.py -v`
Erwartet: PASS, und die bestehenden Tests der Datei bleiben grün.

- [ ] **Schritt 5: Commit**

```bash
git add backend/app.py backend/test_api_availability.py
git commit -m "feat: eigene Arbeitszeitfenster ueber eine eigene Route lesbar"
```

---

## Aufgabe 2: Zellenkollision bei gleichzeitigen Blöcken

Vorarbeit 2 aus Spec §10. `CalendarView.jsx` gruppiert die Zuweisungen eines Tages nach `shift_type_id` und zeigt als Zeitangabe der Gruppe `slots[0].start_time`–`slots[0].end_time`. `ShiftCell.jsx` tut dasselbe mit `sample = sorted[0]`.

**Der Befund ist breiter als im Handoff notiert.** Nicht nur mehrere vorlagenlose Blöcke kollidieren (alle unter dem Schlüssel `null`), sondern ab Etappe 4 auch **zugeschnittene Blöcke derselben Vorlage**: eine Frühschicht 06:00–14:00 und ihr auf 08:00–14:00 gekürztes Geschwister tragen dieselbe `shift_type_id` und würden unter einer einzigen Überschrift mit den Zeiten des ersten erscheinen. Der Fix muss deshalb allgemein sein und nach **(Vorlage, Startzeit, Endzeit)** gruppieren, nicht nach Vorlage allein.

**Files:**
- Modify: `frontend/src/components/CalendarView.jsx:76-84` (Gruppierung), `:97` (Schlüssel)
- Modify: `frontend/src/components/ShiftCell.jsx:59-60` (`sorted`/`sample`) und der Rumpf darunter
- Test: `frontend/src/components/ShiftCell.test.jsx` (neu), `frontend/src/components/CalendarView.test.jsx` (neu)

**Interfaces:**
- Produces: keine neue API. Beide Komponenten behalten ihre Props unverändert; nur die interne Gruppierung ändert sich.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```jsx
// frontend/src/components/ShiftCell.test.jsx
import { render, screen } from '@testing-library/react'
import ShiftCell from './ShiftCell'
import { TranslationProvider } from '../i18n/context'

const slots = [
  { id: 1, slot_index: 0, employee_id: 3, employee_name: 'Anna',
    start_time: '08:00', end_time: '12:00', assignment_time_set: true },
  { id: 2, slot_index: 1, employee_id: 4, employee_name: 'Ben',
    start_time: '16:00', end_time: '20:00', assignment_time_set: true },
]

function renderCell(props) {
  return render(
    <TranslationProvider>
      <ShiftCell date="2026-09-01" shiftType={{ id: null, name: 'Dienst' }}
        slots={slots} employees={[]} readOnly {...props} />
    </TranslationProvider>
  )
}

test('zwei Bloecke mit verschiedenen Zeiten zeigen beide Zeitpaare', () => {
  renderCell()

  expect(screen.getByText(/08:00.*12:00/)).toBeInTheDocument()
  expect(screen.getByText(/16:00.*20:00/)).toBeInTheDocument()
})

test('jede Person steht unter ihrem eigenen Zeitpaar', () => {
  const { container } = renderCell()

  const groups = container.querySelectorAll('.cell-time-group')
  expect(groups).toHaveLength(2)
  expect(groups[0].textContent).toContain('Anna')
  expect(groups[0].textContent).not.toContain('Ben')
})
```

Der zweite Test ist der, der wirklich etwas prüft: dass die Personen den richtigen Zeitpaaren zugeordnet sind, nicht nur dass beide Zeiten irgendwo auftauchen.

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Run: `cd frontend && npm test -- --run ShiftCell`
Erwartet: FAIL — nur ein Zeitpaar im Dokument, `.cell-time-group` existiert nicht.

- [ ] **Schritt 3: `ShiftCell.jsx` auf Zeitgruppen umstellen**

Die Slots innerhalb der Zelle nach ihrem aufgelösten Zeitpaar gruppieren und je Gruppe rendern, was die Zelle heute einmal rendert:

```jsx
  // Slots sharing one cell no longer share one time pair. A trimmed block
  // keeps its template's shift_type_id but runs different hours, and the
  // free-block column collects every template-less block of the date at once,
  // so both land here side by side. Grouping by the pair keeps each group's
  // header true for the people underneath it - showing sorted[0]'s hours for
  // all of them silently mislabels everyone else.
  const timeGroups = []
  for (const slot of slots.slice().sort((a, b) => a.slot_index - b.slot_index)) {
    const key = `${slot.start_time}-${slot.end_time}`
    const existing = timeGroups.find(group => group.key === key)
    if (existing) existing.slots.push(slot)
    else timeGroups.push({ key, slots: [slot] })
  }
```

Der bisherige Rumpf ab `const sample = sorted[0]` wandert in eine innere Komponente oder eine `map` über `timeGroups`, jeweils mit `sample = group.slots[0]` und einem umschließenden `<div className="cell-time-group">`. Die Steuerelemente auf Zellenebene (Zeit für das Datum überschreiben, Platz hinzufügen) bleiben **einmal** pro Zelle, nicht pro Gruppe — sie beziehen sich auf die Schichtart des Datums, nicht auf einen einzelnen Block.

- [ ] **Schritt 4: `CalendarView.jsx` gleichziehen**

```jsx
            const groups = new Map()
            for (const a of dayAssignments) {
              // Key on the hours too, not just the template: a trimmed block
              // shares its template's id but not its times, and every
              // template-less block of the day shares the id null. Either way
              // one header per distinct pair is the only honest rendering.
              const key = `${a.shift_type_id ?? 'free'}|${a.start_time}|${a.end_time}`
              if (!groups.has(key)) groups.set(key, [])
              groups.get(key).push(a)
            }
```

Die Sortierung `orderedGroups` darunter nutzt bisher `shiftOrder.get(a[0])` mit der Vorlagen-ID als Schlüssel. Sie muss auf `group[1][0].shift_type_id` umgestellt werden und bei Gleichstand nach `start_time` sortieren, damit die Reihenfolge deterministisch bleibt. Der `key`-Prop der Gruppe wird der neue zusammengesetzte Schlüssel.

- [ ] **Schritt 5: Tests laufen lassen**

Run: `cd frontend && npm test -- --run`
Erwartet: PASS, die 5 Bestandstests bleiben grün.

- [ ] **Schritt 6: Commit**

```bash
git add frontend/src/components/ShiftCell.jsx frontend/src/components/CalendarView.jsx frontend/src/components/ShiftCell.test.jsx frontend/src/components/CalendarView.test.jsx
git commit -m "fix: gleichzeitige Bloecke bekommen jeder ihr eigenes Zeitpaar"
```

---

## Aufgabe 3: Tägliche Höchstarbeitszeit im Datenmodell

**Files:**
- Create: `backend/migrations/0008_max_daily_hours.py`
- Modify: `backend/app.py` — `serialize_employee()` (586), `create_employee` (~806), `update_employee` (~855), `load_employees_for_scheduling()` (1228)
- Modify: `frontend/src/pages/Employees.jsx`, `frontend/src/i18n/translations.js`
- Test: `backend/test_migrations.py`, `backend/test_migrations_postgres.py`, `backend/test_api_availability.py`

**Interfaces:**
- Produces: `employees.max_daily_hours` (REAL NOT NULL DEFAULT 10); im Scheduler-Dict als `max_daily_hours`.

- [ ] **Schritt 1: Den fehlschlagenden Rundlauftest schreiben**

```python
def test_0008_roundtrip_up_down_up(migrated_connection):
    """Eine Migration muss nach ihrer eigenen Ruecknahme wieder vorwaerts laufen."""
    cursor = migrated_connection.cursor()
    assert 'max_daily_hours' in table_columns(cursor, 'employees')

    run_down(migrated_connection, '0008_max_daily_hours')
    run_up(migrated_connection, '0008_max_daily_hours')

    assert 'max_daily_hours' in table_columns(cursor, 'employees')


def test_0008_defaults_existing_rows_to_ten(migrated_connection):
    cursor = migrated_connection.cursor()
    cursor.execute("INSERT INTO employees (name, active) VALUES ('Anna', 1)")
    cursor.execute("SELECT max_daily_hours FROM employees WHERE name = 'Anna'")

    assert cursor.fetchone()['max_daily_hours'] == 10
```

Die genauen Hilfsnamen (`migrated_connection`, `run_down`, `run_up`) aus `test_migrations.py` übernehmen — dort steht das etablierte Muster von `0004` bis `0007`.

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_migrations.py -k 0008 -v`
Erwartet: FAIL — Migration existiert nicht.

- [ ] **Schritt 3: Migration schreiben**

```python
"""Taegliche Hoechstarbeitszeit je Mitarbeiter.

Paragraph 3 ArbZG: die werktaegliche Arbeitszeit darf acht Stunden nicht
ueberschreiten und nur dann bis auf zehn verlaengert werden, wenn im Schnitt
ueber sechs Kalendermonate oder 24 Wochen acht Stunden eingehalten werden.
Der Standard 10 ist deshalb die Obergrenze des Zulaessigen, nicht die
Normalvorgabe - den Ausgleich prueft das Tool nicht und kann er auch nicht
pruefen, weil der Planer monatsweise arbeitet. Der Hinweis dazu steht in der
Oberflaeche am Feld.

NOT NULL mit Standard, nicht nullbar wie weekly_hours: 0001_baseline.py
begruendet dieselbe Entscheidung fuer min_rest_hours damit, dass eine
sicherheitsrelevante Einstellung nie unbesetzt sein soll. Fuer eine Grenze aus
dem Arbeitszeitgesetz gilt das erst recht - "keine Tagesgrenze" darf nicht die
stille Voreinstellung eines vergessenen Feldes sein.

Warum .py und nicht .sql: das ALTER unten muss bedingt sein, damit die
Migration nach ihrer eigenen Ruecknahme wieder vorwaerts laeuft. down()
entfernt die Spalte nicht (SQLite kann DROP COLUMN nicht verlaesslich),
dieselbe Begruendung wie in 0004_employee_availability.py.
"""

from db import table_columns


def up(cursor):
    if 'max_daily_hours' not in table_columns(cursor, 'employees'):
        cursor.execute(
            'ALTER TABLE employees ADD COLUMN max_daily_hours REAL NOT NULL DEFAULT 10')


def down(cursor):
    """Laesst die Spalte stehen - siehe Modulkommentar und 0004.

    Eine zurueckgebliebene Spalte mit sinnvollem Standard ist harmlos: jeder
    Bestandsdatensatz bleibt genauso gueltig wie vor der Migration. Ein
    Rollback, der an einem fehlenden DROP COLUMN scheitert, waere dagegen ein
    Rollback, der nicht funktioniert.
    """
```

Ein leeres `down()` ist zulässig, aber der Runner muss es finden — prüfen, wie `migrations.py` mit einer Migration ohne Rücknahmeschritt umgeht, und notfalls ein `pass` mit Kommentar setzen.

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && python -m pytest test_migrations.py -v`
Erwartet: PASS. **Die fest verdrahtete Tabellenliste in `test_migrations.py` braucht keinen Eintrag** — es kommt keine Tabelle hinzu, nur eine Spalte.

- [ ] **Schritt 5: Durch die API reichen**

In `serialize_employee()` und `load_employees_for_scheduling()` je eine Zeile `'max_daily_hours': row['max_daily_hours'],`. In `create_employee` und `update_employee` über das bestehende `parse_optional_hours(data.get('max_daily_hours'), 'max_daily_hours_label')`, mit `if ... is not None else 10` — genau das Muster, das `min_rest_hours` daneben schon nutzt.

- [ ] **Schritt 6: API-Test schreiben und laufen lassen**

```python
def test_max_daily_hours_defaults_to_ten(client, hr_headers):
    response = client.post('/employees', json={'name': 'Anna'}, headers=hr_headers)

    assert response.get_json()['max_daily_hours'] == 10


def test_max_daily_hours_is_stored_and_returned(client, hr_headers):
    created = client.post('/employees', json={'name': 'Anna', 'max_daily_hours': 8},
                          headers=hr_headers).get_json()

    fetched = client.get(f"/employees/{created['id']}", headers=hr_headers).get_json()

    assert fetched['max_daily_hours'] == 8
```

Run: `cd backend && python -m pytest -q -W error::DeprecationWarning`

- [ ] **Schritt 7: Frontend-Feld und Übersetzungen**

In `Employees.jsx` neben `min_rest_hours` ein Zahlenfeld. Übersetzungsschlüssel `employees.maxDailyHours` und `employees.maxDailyHoursHint`:

- DE: „Tägliche Höchstarbeitszeit (Stunden)" / „Mehr als 8 Stunden setzen nach § 3 ArbZG einen Ausgleich über sechs Monate voraus, den dieses Tool nicht prüft."
- EN: „Maximum daily working hours" / „Over 8 hours, § 3 ArbZG requires a six-month average this tool does not check."

- [ ] **Schritt 8: Commit**

```bash
git add backend/migrations/0008_max_daily_hours.py backend/app.py backend/test_migrations.py backend/test_migrations_postgres.py backend/test_api_availability.py backend/i18n.py frontend/src/pages/Employees.jsx frontend/src/i18n/translations.js
git commit -m "feat: taegliche Hoechstarbeitszeit je Mitarbeiter"
```

---

## Aufgabe 4: Stufe 1 — Bedarf mit Vorlagen decken (Phasen A und B)

**Files:**
- Create: `backend/block_planner.py`
- Test: `backend/test_block_planner.py`

**Interfaces:**
- Consumes: `scheduler._time_range_minutes()`, `scheduler._ranges_overlap()`, `coverage_model._minutes_to_time()` — die Minutenachse und die Mitternachtsregel werden importiert, nicht zweitgefasst.
- Produces:
  ```python
  cover_demand(bands, templates, min_block_minutes=MIN_BLOCK_MINUTES) -> list[dict]
  # bands:     [{'start_time': 'HH:MM', 'end_time': 'HH:MM', 'required_count': int}]
  # templates: [{'id': int, 'start_time': 'HH:MM', 'end_time': 'HH:MM'}]
  # Rueckgabe: [{'shift_type_id': int|None, 'start_time': str, 'end_time': str}]
  MIN_BLOCK_MINUTES = 180
  ```

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_vorlage_deckt_ihr_eigenes_band_genau():
    """Der Normalfall: eine Vorlage, ein daraus abgeleitetes Band."""
    bands = [{'start_time': '06:00', 'end_time': '14:00', 'required_count': 3}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]

    blocks = cover_demand(bands, templates)

    assert len(blocks) == 3
    assert all(b['shift_type_id'] == 1 for b in blocks)
    assert all((b['start_time'], b['end_time']) == ('06:00', '14:00') for b in blocks)


def test_gestaffelter_bedarf_wird_von_einer_vorlage_und_einem_rest_gedeckt():
    """Zwei Baender, eine Vorlage: die Vorlage traegt die Ueberdeckung,
    der Mehrbedarf des zweiten Bandes wird ein eigener Block."""
    bands = [
        {'start_time': '06:00', 'end_time': '08:00', 'required_count': 2},
        {'start_time': '08:00', 'end_time': '14:00', 'required_count': 3},
    ]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]

    blocks = cover_demand(bands, templates)

    volle = [b for b in blocks if (b['start_time'], b['end_time']) == ('06:00', '14:00')]
    rest = [b for b in blocks if (b['start_time'], b['end_time']) == ('08:00', '14:00')]
    assert len(volle) == 2
    assert len(rest) == 1
    assert rest[0]['shift_type_id'] is None


def test_bedarf_ohne_passende_vorlage_wird_vorlagenloser_block():
    bands = [{'start_time': '10:00', 'end_time': '16:00', 'required_count': 1}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]

    blocks = cover_demand(bands, templates)

    assert blocks == [{'shift_type_id': None, 'start_time': '10:00', 'end_time': '16:00'}]


def test_nachtband_ueber_mitternacht():
    bands = [{'start_time': '22:00', 'end_time': '06:00', 'required_count': 1}]
    templates = [{'id': 1, 'start_time': '22:00', 'end_time': '06:00'}]

    blocks = cover_demand(bands, templates)

    assert blocks == [{'shift_type_id': 1, 'start_time': '22:00', 'end_time': '06:00'}]


def test_ohne_baender_keine_bloecke():
    assert cover_demand([], [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]) == []
```

`test_gestaffelter_bedarf_...` ist der wichtigste: er prüft, dass die Bänder als **absolute Besetzungsstärke** gelesen werden (bei 06–08 zwei Leute, bei 08–14 drei *insgesamt*, nicht 2+3) und dass die Vorlage die Überdeckung trägt, statt für jedes Band eigene Blöcke zu erzeugen.

Ein weiterer Test gehört dazu, weil er die Rückwärtskompatibilität festnagelt:

```python
def test_aus_vorlagen_abgeleitete_baender_ergeben_wieder_die_vorlagenbloecke():
    """Migration 0007 leitet Baender aus genau diesen Vorlagen ab. Auf
    unveraendertem Bestand muss cover_demand() daraus wieder exakt die
    Bloecke bauen, die build_slots() bisher gebaut hat - sonst aendert die
    Umstellung stillschweigend die Plaene."""
    templates = [
        {'id': 1, 'start_time': '06:00', 'end_time': '14:00'},
        {'id': 2, 'start_time': '14:00', 'end_time': '22:00'},
    ]
    bands = coverage_curve([
        {'start_time': '06:00', 'end_time': '14:00', 'required_count': 3},
        {'start_time': '14:00', 'end_time': '22:00', 'required_count': 2},
    ])

    blocks = cover_demand(bands, templates)

    by_template = Counter(b['shift_type_id'] for b in blocks)
    assert by_template == {1: 3, 2: 2}
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_block_planner.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'block_planner'`.

- [ ] **Schritt 3: Phasen A und B umsetzen**

```python
"""Stufe 1 der Planung: aus Bedarf und Vorlagen werden Bloecke.

Reine Rechenlogik ohne Datenbank und ohne Flask, wie coverage_model.py
nebenan. Diese Datei beantwortet genau eine Frage: welche Bloecke muss ein
Tag haben? Wer sie arbeitet, entscheidet der Suchkern in scheduler.py.

Die Minutenachse und ihre Mitternachtsregel kommen aus scheduler.py und
werden hier nur wiederverwendet - dieselbe Linie wie in coverage_model.py,
genau eine Fassung, nicht drei.

Der Dateiname folgt der Lehre aus Etappe 3: block_planner statt planner,
damit kein installiertes Paket verdeckt werden kann.
"""

from collections import Counter

from coverage_model import _minutes_to_time
from scheduler import _time_range_minutes

MIN_BLOCK_MINUTES = 180


def _demand_profile(bands):
    """Restbedarf je Minutenintervall, als Liste (start, ende, anzahl).

    Die Baender eines Wochentags ueberlappen sich nicht - das garantiert
    replace_coverage_requirements() - und tragen absolute Besetzungsstaerke.
    Sie koennen deshalb unveraendert als Profil dienen.
    """
    return [
        [*_time_range_minutes(band['start_time'], band['end_time']), band['required_count']]
        for band in bands
    ]


def _covered_everywhere(profile, start, end):
    """Kleinster Restbedarf ueber [start, end) - 0, wenn irgendwo nichts offen ist."""
    overlapping = [count for lo, hi, count in profile if lo < end and start < hi]
    if not overlapping:
        return 0
    # Ein Loch im Profil (Bereich ohne Band) zaehlt als Bedarf 0 und macht die
    # Vorlage dort wertlos - deshalb erst pruefen, ob das Intervall luecken-
    # los belegt ist.
    covered = sorted((lo, hi) for lo, hi, _ in profile if lo < end and start < hi)
    cursor = start
    for lo, hi in covered:
        if lo > cursor:
            return 0
        cursor = max(cursor, hi)
    if cursor < end:
        return 0
    return min(overlapping)


def _subtract(profile, start, end, count):
    """count Personen ueber [start, end) vom Restbedarf abziehen."""
    for entry in profile:
        lo, hi, remaining = entry
        if lo < end and start < hi:
            entry[2] = max(0, remaining - count)


def cover_demand(bands, templates, min_block_minutes=MIN_BLOCK_MINUTES):
    """Bedarfsbaender eines Tages zu Bloecken machen.

    Phase A deckt mit Vorlagen: fuer jede Vorlage ist n der kleinste
    Restbedarf ueber ihre gesamte Laufzeit, also wie oft sie vollstaendig
    gebraucht wird. Die Vorlage mit dem groessten n mal Dauer kommt zuerst -
    lange, oft gebrauchte Vorlagen tragen am meisten Bedarf ab. Bei
    Gleichstand entscheidet die Vorlagen-ID, damit das Ergebnis
    deterministisch ist.

    Phase B macht aus dem Rest eigene Bloecke: der frueheste Punkt mit
    Restbedarf, von dort der maximale zusammenhaengende Bereich mit
    demselben Restbedarf.

    Warum das die Umstellung rueckwaertskompatibel macht: Migration 0007 hat
    die Baender aus genau diesen Vorlagen abgeleitet. Auf unveraendertem
    Bestand ist n deshalb identisch mit dem alten required_count, Phase A
    deckt alles ab und Phase B hat nichts zu tun.
    """
    profile = _demand_profile(bands)
    blocks = []

    # Phase A
    while True:
        best = None
        for template in sorted(templates, key=lambda tpl: tpl['id']):
            start, end = _time_range_minutes(template['start_time'], template['end_time'])
            n = _covered_everywhere(profile, start, end)
            if n == 0:
                continue
            weight = n * (end - start)
            if best is None or weight > best[0]:
                best = (weight, n, template, start, end)
        if best is None:
            break
        _, n, template, start, end = best
        for _ in range(n):
            blocks.append({
                'shift_type_id': template['id'],
                'start_time': template['start_time'],
                'end_time': template['end_time'],
            })
        _subtract(profile, start, end, n)

    # Phase B
    blocks.extend(_remaining_blocks(profile, templates, min_block_minutes))
    return blocks
```

`_remaining_blocks()` läuft über die Ereignispunkte des Restprofils, bildet je zusammenhängendem Bereich mit Restbedarf > 0 so viele Blöcke wie der Restbedarf hoch ist, verwirft Bereiche unter `min_block_minutes` und setzt `shift_type_id` auf die ID einer Vorlage, deren Zeiten exakt getroffen werden, sonst `None`.

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && python -m pytest test_block_planner.py -v`
Erwartet: PASS.

- [ ] **Schritt 5: Commit**

```bash
git add backend/block_planner.py backend/test_block_planner.py
git commit -m "feat: Stufe 1 deckt Bedarfsbaender mit Vorlagen"
```

---

## Aufgabe 5: Stufe 1 — Zuschnitt auf Arbeitszeitfenster (Phasen C und D)

**Files:**
- Modify: `backend/block_planner.py`
- Test: `backend/test_block_planner.py`

**Interfaces:**
- Consumes: `scheduler.window_contains_shift()`, `scheduler.window_is_valid_on()` — **nicht duplizieren**, `constraint_warnings()` hängt an derselben Implementierung.
- Produces:
  ```python
  plan_day(bands, templates, candidates, iso_date, weekday,
           min_block_minutes=MIN_BLOCK_MINUTES) -> list[dict]
  # candidates: [{'id': int, 'availability_mode': 'anytime'|'windows',
  #               'availability': [{'weekday', 'start_time', 'end_time',
  #                                 'valid_from', 'valid_until'}],
  #               'max_daily_hours': float|None}]
  ```

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_block_wird_auf_das_einzige_passende_fenster_gekuerzt():
    """Drei Plaetze, zwei uneingeschraenkte Leute, eine mit Fenster 08:00-14:00.
    Der dritte Block muss gekuerzt werden, sonst bleibt er unbesetzt."""
    bands = [{'start_time': '06:00', 'end_time': '14:00', 'required_count': 3}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]
    candidates = [
        {'id': 1, 'availability_mode': 'anytime', 'availability': []},
        {'id': 2, 'availability_mode': 'anytime', 'availability': []},
        {'id': 3, 'availability_mode': 'windows', 'availability': [
            {'weekday': 1, 'start_time': '08:00', 'end_time': '14:00',
             'valid_from': None, 'valid_until': None}]},
    ]

    blocks = plan_day(bands, templates, candidates, '2026-09-01', 1)

    zeiten = sorted((b['start_time'], b['end_time']) for b in blocks)
    assert zeiten == [('06:00', '14:00'), ('06:00', '14:00'), ('08:00', '14:00')]


def test_ohne_fenster_wird_nichts_gekuerzt():
    """Gegenprobe zum vorigen Test: dieselben Baender, aber drei
    uneingeschraenkte Leute - es darf kein Zuschnitt entstehen."""
    bands = [{'start_time': '06:00', 'end_time': '14:00', 'required_count': 3}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]
    candidates = [{'id': i, 'availability_mode': 'anytime', 'availability': []}
                  for i in (1, 2, 3)]

    blocks = plan_day(bands, templates, candidates, '2026-09-01', 1)

    assert all((b['start_time'], b['end_time']) == ('06:00', '14:00') for b in blocks)


def test_zuschnitt_unter_mindestlaenge_entsteht_nicht():
    """Fenster 13:00-14:00 wuerde einen Einstundenblock ergeben - der bleibt aus,
    der Bedarf wird stattdessen als Luecke gemeldet."""
    bands = [{'start_time': '06:00', 'end_time': '14:00', 'required_count': 2}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]
    candidates = [
        {'id': 1, 'availability_mode': 'anytime', 'availability': []},
        {'id': 2, 'availability_mode': 'windows', 'availability': [
            {'weekday': 1, 'start_time': '13:00', 'end_time': '14:00',
             'valid_from': None, 'valid_until': None}]},
    ]

    blocks = plan_day(bands, templates, candidates, '2026-09-01', 1)

    assert len(blocks) == 2
    assert all(b['start_time'] == '06:00' for b in blocks)


def test_abgelaufenes_fenster_zaehlt_nicht():
    """valid_until in der Vergangenheit: das Fenster darf keinen Zuschnitt ausloesen."""
    bands = [{'start_time': '06:00', 'end_time': '14:00', 'required_count': 1}]
    templates = [{'id': 1, 'start_time': '06:00', 'end_time': '14:00'}]
    candidates = [{'id': 1, 'availability_mode': 'windows', 'availability': [
        {'weekday': 1, 'start_time': '08:00', 'end_time': '14:00',
         'valid_from': None, 'valid_until': '2026-08-01'}]}]

    blocks = plan_day(bands, templates, candidates, '2026-09-01', 1)

    assert [(b['start_time'], b['end_time']) for b in blocks] == [('06:00', '14:00')]
```

Der zweite Test ist die Gegenprobe, die den ersten überhaupt aussagekräftig macht — ohne ihn könnte die Umsetzung *immer* kürzen und trotzdem grün sein.

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_block_planner.py -k plan_day -v`
Erwartet: FAIL — `plan_day` existiert nicht.

- [ ] **Schritt 3: Phase C und D umsetzen**

`plan_day()` ruft zuerst `cover_demand()`, dann:

1. **Deckungsmenge je Block bestimmen.** Ein Kandidat deckt einen Block, wenn `availability_mode == 'anytime'`, oder wenn eines seiner für `iso_date` gültigen Fenster des Wochentags den Block über `window_contains_shift()` vollständig enthält.
2. **Probeweise besetzen nach Knappheit.** Blöcke aufsteigend nach der Größe ihrer Deckungsmenge sortieren (Minimum-Remaining-Values, dieselbe Heuristik wie `order_slots()`), bei Gleichstand nach Startzeit und Vorlagen-ID für Determinismus. Jeweils den Kandidaten mit den wenigsten verbleibenden Alternativen zuweisen, sofern die Zuweisung überschneidungsfrei ist und `max_daily_hours` einhält.
3. **Unbesetzte Blöcke zuschneiden.** Über alle an diesem Tag noch nicht ausgelasteten Kandidaten den größten Schnitt aus Block und Fenster bilden. Größter Schnitt gewinnt, bei Gleichstand die kleinere Kandidaten-ID. Der Schnitt muss mindestens `min_block_minutes` lang sein.
4. **Rest zurück in die Warteschlange.** Der ungedeckte Teil des Blocks wird ein neuer Block und durchläuft Schritt 1 bis 3 erneut.
5. **Zuordnung verwerfen.** Zurückgegeben wird nur die Blockliste.

Die Schleife über Schritt 1–4 braucht eine Iterationsschranke:

```python
    # Phase C erzeugt beim Zuschneiden neue Bloecke und laeuft dann erneut.
    # Ohne Schranke koennte ein Rest, der sich immer wieder nur um Minuten
    # verkuerzt, beliebig lange kreisen. Bei Erreichen der Schranke kommt
    # zurueck, was bis dahin gebaut wurde - der ungedeckte Rest erscheint als
    # Deckungsluecke. Meldet Luecken, statt zu scheitern: dieselbe Haltung wie
    # die Notbremse des Suchkerns und wie max_shifts_per_month.
    max_iterations = 4 * len(blocks) + 8
```

- [ ] **Schritt 4: Tests laufen lassen**

Run: `cd backend && python -m pytest test_block_planner.py -v`
Erwartet: PASS.

- [ ] **Schritt 5: Commit**

```bash
git add backend/block_planner.py backend/test_block_planner.py
git commit -m "feat: Stufe 1 schneidet Bloecke auf Arbeitszeitfenster zu"
```

---

## Aufgabe 6: Stufe 1 an den Generator anschließen

**Files:**
- Modify: `backend/scheduler.py` — `build_slots()` (155–188), `_search()` (Aufruf 305), `generate_schedule()` (508)
- Modify: `backend/app.py` — `generate_schedule_route()` (1404), Datenladen
- Test: `backend/test_api_coverage.py`

**Interfaces:**
- Consumes: `block_planner.plan_day()`; `coverage_requirements_by_weekday()`, `load_business_hours_by_weekday()`, `business_hours_exceptions_by_date()`, `_closed_on()`, `business_hours_for()`, `trim_band_to_hours()` — alle aus `coverage_gaps_for_month()` (app.py:2565) bereits vorhanden.
- Produces: `build_slots(year, month, templates, bands_by_weekday, employees, hours_context)` liefert Blöcke mit echten Zeiten und optional `shift_type_id = None`.

- [ ] **Schritt 1: Das Datenladen aus `coverage_gaps_for_month()` herausziehen**

Der Prolog von `coverage_gaps_for_month()` (Bänder, Öffnungszeiten, Ausnahmen laden; je Datum schließen-prüfen und Bänder zuschneiden) ist genau das, was Stufe 1 auch braucht. Ihn in eine Funktion `effective_bands_by_date(cursor, year, month)` herausziehen und von **beiden** Aufrufern nutzen. Sonst steht die Zuschnittlogik zweimal da und driftet auseinander — genau der Befund, den Etappe 3 bei `business_hours_for()` schon einmal hatte.

- [ ] **Schritt 2: Den fehlschlagenden Test schreiben**

```python
def test_generator_plant_aus_bedarfsbaendern_statt_aus_schichtbedarf(client, hr_headers):
    """shift_requirements steht auf 0, coverage_requirements verlangt 2 -
    der Generator muss den Baendern folgen."""
    shift_type = _create_shift_type(client, hr_headers, start='08:00', end='16:00',
                                    requirements={0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0})
    _create_employees(client, hr_headers, count=2)
    _set_coverage(client, hr_headers, weekday=0,
                  bands=[{'start_time': '08:00', 'end_time': '16:00', 'required_count': 2}])

    response = client.post('/schedules/generate', json={'year': 2026, 'month': 9},
                           headers=hr_headers)

    montage = [a for a in response.get_json()['assignments']
               if date.fromisoformat(a['date']).weekday() == 0]
    assert len(montage) == 2 * _mondays_in(2026, 9)


def test_generator_schreibt_die_tatsaechlichen_zeiten(client, hr_headers):
    """Bisher blieben start_time/end_time auf dem Erzeugen-Pfad leer."""
    ...
    assignment = response.get_json()['assignments'][0]
    assert assignment['start_time'] == '08:00'
    assert assignment['end_time'] == '16:00'
```

Der erste Test ist der Beweis der Umstellung: er setzt `shift_requirements` bewusst auf 0, sodass der alte Pfad **nichts** erzeugen würde.

- [ ] **Schritt 3: Test laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_api_coverage.py -k generator -v`
Erwartet: FAIL — keine Zuweisungen, weil `shift_requirements` auf 0 steht.

- [ ] **Schritt 4: `build_slots()` umstellen**

`build_slots()` bekommt die Bänder je Datum und die Kandidaten und ruft je Tag `plan_day()`. Die Rückgabe wird um `date`, `weekday`, `week_start`, `slot_index`, `is_weekend` und `duration_minutes` ergänzt — die Felder, die der Suchkern erwartet. `slot_index` zählt innerhalb eines Datums über alle Blöcke durch, damit der UNIQUE-Index `(schedule_id, date, COALESCE(shift_type_id, 0), slot_index)` trägt.

**Die alte Signatur bleibt als Pfad für die 23 Bestandstests erhalten:** werden keine Bänder übergeben, baut `build_slots()` wie bisher aus `shift_type['requirements']`. Das ist die Vergleichsbasis für den Benchmark und der Grund, warum `test_scheduler.py` unverändert grün bleibt.

- [ ] **Schritt 5: Die Sortier-Landmine entschärfen**

`backend/scheduler.py`, Ergebnisaufbau in `_search()`:

```python
    # shift_type_id is None for a block with no template, and None does not
    # compare against int - sorting the raw value raises TypeError the moment
    # stage 1 emits its first template-less block. Sort those last, then by
    # the hours, so a date's blocks come out in a stable, readable order.
    assignments.sort(key=lambda a: (
        a['date'], a['shift_type_id'] is None, a['shift_type_id'] or 0,
        a['start_time'] or '', a['slot_index'],
    ))
```

- [ ] **Schritt 6: Zeiten persistieren**

`generate_schedule_route()`, INSERT erweitern:

```python
        cursor.execute(
            'INSERT INTO shift_assignments '
            '(schedule_id, date, shift_type_id, slot_index, employee_id, start_time, end_time) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (schedule_id, a['date'], a['shift_type_id'], a['slot_index'], a['employee_id'],
             a['start_time'], a['end_time']),
        )
```

Dazu müssen `start_time`/`end_time` im Ergebnis-Dict von `_search()` stehen — der Aufbau listet sie heute nicht.

- [ ] **Schritt 7: Tests laufen lassen**

Run: `cd backend && python -m pytest -q -W error::DeprecationWarning`
Erwartet: PASS, insbesondere die 23 Tests in `test_scheduler.py` unverändert.

- [ ] **Schritt 8: Commit**

```bash
git add backend/scheduler.py backend/app.py backend/test_api_coverage.py
git commit -m "feat: der Planer baut seine Bloecke aus den Bedarfsbaendern"
```

---

## Aufgabe 7: Geteilter Dienst im Suchkern

**Files:**
- Modify: `backend/scheduler.py` — `_search()`: `day_usage` (317), `day_shift` (325), `rest_period_ok()` (338–364), `eligible_candidates()` (366–392), der Zuweisungs- und Rücknahmepfad in `backtrack()`
- Test: `backend/test_scheduler_split_shifts.py` (neu)

**Interfaces:**
- Consumes: `_ranges_overlap()`, `_time_range_minutes()` aus derselben Datei.
- Produces: keine neue öffentliche Signatur. `generate_schedule()` liest zusätzlich `emp.get('max_daily_hours')`.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

```python
def test_split_shift_is_assigned_to_one_person():
    """Two non-overlapping blocks on one date, one person: both go to them."""
    employees = [{'id': 1, 'max_shifts_per_month': None, 'unavailable_weekdays': set(),
                  'unavailable_dates': set(), 'allowed_shift_types': None,
                  'weekly_hours': None, 'min_rest_hours': 11, 'max_daily_hours': 10}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),
        _slot('2026-09-01', '16:00', '20:00', slot_index=1),
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 0
    assert {a['employee_id'] for a in result['assignments']} == {1}


def test_overlapping_blocks_do_not_go_to_the_same_person():
    employees = [{'id': 1, ...}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),
        _slot('2026-09-01', '11:00', '15:00', slot_index=1),
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 1


def test_daily_hours_cap_binds_across_blocks():
    """Sum of block durations, not the span from first start to last end -
    § 2 Abs. 1 ArbZG: the interruption is not working time."""
    employees = [{'id': 1, ..., 'max_daily_hours': 7}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),   # 4 h
        _slot('2026-09-01', '16:00', '20:00', slot_index=1),   # 4 h -> 8 h > 7
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 1


def test_span_alone_does_not_exceed_the_cap():
    """Gegenprobe: dieselben zwei Bloecke, Grenze 8 - die Spanne von 08:00 bis
    20:00 sind 12 Stunden, die Arbeitszeit aber nur 8. Beide muessen gehen."""
    employees = [{'id': 1, ..., 'max_daily_hours': 8}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),
        _slot('2026-09-01', '16:00', '20:00', slot_index=1),
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 0


def test_rest_period_measures_from_the_last_block_of_the_day():
    """§ 5 Abs. 1: eleven hours after the end of the daily working time.
    A split shift ending 20:00 blocks a 06:00 start the next morning."""
    employees = [{'id': 1, ..., 'min_rest_hours': 11}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),
        _slot('2026-09-01', '16:00', '20:00', slot_index=1),
        _slot('2026-09-02', '06:00', '10:00', slot_index=0),
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 1


def test_the_midday_interruption_is_not_rest():
    """Gegenprobe: die Luecke zwischen 12:00 und 16:00 sind vier Stunden und
    damit weniger als min_rest_hours - sie darf trotzdem nichts blockieren,
    weil die taegliche Arbeitszeit erst um 20:00 endet."""
    employees = [{'id': 1, ..., 'min_rest_hours': 11}]
    slots = [
        _slot('2026-09-01', '08:00', '12:00', slot_index=0),
        _slot('2026-09-01', '16:00', '20:00', slot_index=1),
    ]

    result = _run(slots, employees)

    assert result['unfilled_count'] == 0
```

Die beiden Gegenproben (`test_span_alone_...`, `test_the_midday_interruption_...`) sind unverzichtbar: ohne sie wäre eine Umsetzung grün, die die Spanne statt der Summe rechnet oder die Ruhezeit zwischen den Blöcken eines Tages prüft — beides genau die falschen Lesarten des Gesetzes.

Kommentarsprache: `test_scheduler.py` ist englisch, `test_scheduler_windows.py` deutsch. Die neue Datei ist ein Nachbar von `test_scheduler_windows.py` → **deutsch**, mit englischen Docstrings nur dort, wo sie aus `scheduler.py` zitieren. Innerhalb der Datei einheitlich bleiben.

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_scheduler_split_shifts.py -v`
Erwartet: FAIL — `test_split_shift_is_assigned_to_one_person` schlägt fehl (ein Block bleibt unbesetzt, weil `day_usage` die Person sperrt).

- [ ] **Schritt 3: `day_usage` auf Intervalle umstellen**

```python
    # (employee_id, date) -> list of (start, end) minute ranges already
    # assigned there. Was a plain set of employee ids per date until Etappe 4:
    # "works today" was enough while nobody could work twice a day. A split
    # shift makes the question "does this block overlap one they already have"
    # instead - § 2 Abs. 1 ArbZG counts both blocks, and only an overlap is
    # actually impossible.
    day_blocks = {}
```

`eligible_candidates()` prüft dann Überschneidung über `_ranges_overlap()` statt Mitgliedschaft. **Wichtig:** ein Block ohne bekannte Zeiten (die 23 Bestandstests) hat keine Minutenachse — dort bleibt es bei „einmal pro Tag", sonst würde ein Test, der nur mit Schichtzahlen arbeitet, plötzlich dieselbe Person mehrfach am Tag sehen. Das ist der Zweig, der `test_scheduler.py` unverändert grün hält.

- [ ] **Schritt 4: Ruhezeit über die Tagesgrenze**

`day_shift` wird zu einer Liste je `(employee_id, date)`. `rest_period_ok()` vergleicht das **späteste Ende** des Vortags gegen den **frühesten Beginn** des aktuellen Tages und das späteste Ende des aktuellen Tages gegen den frühesten Beginn des Folgetags. Innerhalb eines Tages wird **nicht** geprüft — die Ruhezeit misst zwischen Arbeitstagen.

- [ ] **Schritt 5: Tagesarbeitszeit**

```python
    # (employee_id, date) -> minutes assigned there, mirroring week_minutes.
    day_minutes = {}
```

In `eligible_candidates()`:

```python
            daily_cap = emp.get('max_daily_hours')
            if daily_cap is not None and slot['duration_minutes'] is not None:
                current = day_minutes.get((eid, slot['date']), 0)
                if current + slot['duration_minutes'] > daily_cap * 60:
                    continue
```

`.get()` statt `[...]`: Aufrufer ohne den Schlüssel — alle Bestandstests — bekommen wie bei `weekly_hours` keine Prüfung statt eines `KeyError`.

Alle drei Strukturen müssen im Rücknahmepfad von `backtrack()` sauber zurückgesetzt werden, nach dem Muster, das `week_minutes` dort schon hat.

- [ ] **Schritt 6: Tests laufen lassen**

Run: `cd backend && python -m pytest test_scheduler.py test_scheduler_windows.py test_scheduler_split_shifts.py -v`
Erwartet: PASS. Die 23 Bestandstests unverändert.

- [ ] **Schritt 7: Commit**

```bash
git add backend/scheduler.py backend/test_scheduler_split_shifts.py
git commit -m "feat: geteilter Dienst mit Tagesgrenze und Ruhezeit nach ArbZG"
```

---

## Aufgabe 8: Warnungen auf dem Handkorrektur-Pfad

**Files:**
- Modify: `backend/app.py` — `constraint_warnings()` (1763)
- Modify: `backend/i18n.py`, `frontend/src/i18n/translations.js`
- Test: `backend/test_api_assignment_times.py`

**Interfaces:**
- Consumes: die in Aufgabe 7 erweiterten Prüfungen aus `scheduler.py`. **Nicht duplizieren** — `swap_assignments()` und `replacement_suggestions()` bauen auf `constraint_warnings()` auf, alle Pfade hängen an einer Implementierung.
- Produces: drei neue i18n-Schlüssel: `warn_overlapping_blocks`, `warn_daily_hours_exceeded`, `warn_rest_period_split`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_overlapping_manual_assignment_warns(client, hr_headers):
    """Warnung, kein Verbot - HR bleibt der Chef."""
    ...
    assert response.status_code == 200
    assert any('überschneid' in w.lower() for w in response.get_json()['warnings'])


def test_daily_hours_exceeded_warns(client, hr_headers):
    ...
    assert any('8' in w for w in response.get_json()['warnings'])
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag prüfen**

Run: `cd backend && python -m pytest test_api_assignment_times.py -k warn -v`
Erwartet: FAIL — keine Warnung in der Antwort.

- [ ] **Schritt 3: Die drei Prüfungen ergänzen**

`constraint_warnings()` lädt bereits die Nachbarschichten für die Ruhezeitprüfung. Erweitert wird um: alle Zuweisungen derselben Person am selben Datum (Überschneidung, Summe der Minuten) und die Umstellung der Ruhezeitprüfung auf letztes Ende / ersten Beginn. Die Abfrage bleibt bewusst ohne `schedule_id`-Filter — die Nachbarschicht kann zu einem anderen Monat gehören.

- [ ] **Schritt 4: Übersetzungen ergänzen**

- `warn_overlapping_blocks` — DE: „{name} hat am {date} bereits einen Block von {start} bis {end}, der sich damit überschneidet." / EN: „{name} already has a block from {start} to {end} on {date} that overlaps this one."
- `warn_daily_hours_exceeded` — DE: „{name} käme am {date} auf {hours} Stunden, die Tagesgrenze liegt bei {cap}." / EN: „{name} would work {hours} hours on {date}; the daily cap is {cap}."
- `warn_rest_period_split` — nutzt die bestehende Ruhezeit-Warnung, nur mit den korrigierten Zeiten; **kein neuer Schlüssel**, wenn der bestehende passt. Vor dem Anlegen prüfen.

- [ ] **Schritt 5: Tests laufen lassen und committen**

```bash
cd backend && python -m pytest -q -W error::DeprecationWarning
git add backend/app.py backend/i18n.py backend/test_api_assignment_times.py frontend/src/i18n/translations.js
git commit -m "feat: Handkorrektur warnt vor Ueberschneidung und Tagesgrenze"
```

---

## Aufgabe 9: Bedarfszahlen aus dem Schichtart-Editor nehmen

**Files:**
- Modify: `frontend/src/pages/ShiftTypes.jsx`
- Modify: `frontend/src/i18n/translations.js`
- Test: `frontend/src/pages/ShiftTypes.test.jsx` (neu)

Die Schichtart bleibt Vorlage: Name, Zeiten, Farbe. Nur das Wochentagsraster mit den Bedarfszahlen verschwindet. **Backend und Tabelle bleiben unangetastet** — `replace_shift_requirements()` (app.py:760) und die Route bleiben stehen, damit `build_slots()` seinen Vergleichspfad behält und Etappe 5 die Tabelle geordnet entfernen kann.

- [ ] **Schritt 1: Test schreiben**

```jsx
test('der Schichtart-Editor zeigt keine Bedarfszahlen mehr', () => {
  render(<ShiftTypes />)

  expect(screen.queryByLabelText(/bedarf/i)).not.toBeInTheDocument()
})

test('Name und Zeiten bleiben bedienbar', () => {
  render(<ShiftTypes />)

  expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
  expect(screen.getByLabelText(/beginn/i)).toBeInTheDocument()
})
```

- [ ] **Schritt 2: Fehlschlag prüfen, Raster entfernen, Tests laufen lassen**

Run: `cd frontend && npm test -- --run`

- [ ] **Schritt 3: Ein Hinweis, wo der Bedarf jetzt lebt**

Ein Satz im Editor mit Verweis auf den Bedarfseditor, damit niemand das Feld sucht. Schlüssel `shiftTypes.demandMovedHint` — DE: „Der Personalbedarf wird jetzt unter *Bedarf* über den Tagesverlauf gepflegt." / EN: „Staffing demand now lives under *Coverage*, across the day."

- [ ] **Schritt 4: Commit**

```bash
git add frontend/src/pages/ShiftTypes.jsx frontend/src/pages/ShiftTypes.test.jsx frontend/src/i18n/translations.js
git commit -m "refactor: Bedarf wird nur noch im Bedarfseditor gepflegt"
```

---

## Aufgabe 10: Benchmark-Gegenprobe

**Files:**
- Modify: `backend/benchmark.py`

**Interfaces:**
- Consumes: `build_slots()` in beiden Formen (mit und ohne Bänder), `plan_day()`.

- [ ] **Schritt 1: Szenario „unveränderter Bestand" ergänzen**

Bänder über `coverage_curve()` aus den Schichtarten ableiten — genau das, was Migration `0007` tut —, beide Pfade laufen lassen und vergleichen: gleiche Blockanzahl, gleiche Zeiten, gleiche `unfilled_count`. Das ist die Messlatte aus Spec §5.2.

- [ ] **Schritt 2: Szenario „Zuschnitt schließt Lücken" ergänzen**

Ein Monat, in dem ein Teil der Belegschaft Fenster hat, die die Vorlagen nicht ganz abdecken. Belegen, dass der neue Pfad weniger unbesetzte Blöcke liefert als der alte — das ist der Nutzen der ganzen Etappe in einer Zahl.

- [ ] **Schritt 3: Laufen lassen und Ergebnis festhalten**

Run: `cd backend && python benchmark.py`
Die Zahlen kommen in den Commit und später ins Handoff.

- [ ] **Schritt 4: Commit**

```bash
git add backend/benchmark.py
git commit -m "test: Benchmark vergleicht alten und neuen Bedarfspfad"
```

---

## Aufgabe 11: Dokumentation

**Files:**
- Modify: `README.md` — `Project Structure` um `block_planner.py` ergänzen; die Beschreibung des Planers auf die zwei Stufen umstellen; einen Abschnitt zum Arbeitszeitrecht mit der ausdrücklichen Abgrenzung aus Spec §3
- Modify: `docs/HANDOFF.md` — Etappe 4 als abgeschlossen eintragen, Stand, offene Befunde, die beiden erledigten Vorarbeiten aus der Liste streichen

Der `Project Structure`-Block listet seit Etappe 3 weiterhin nicht `security.py` und `timeutil.py` — bei der Gelegenheit mit erledigen, der Befund steht seit Etappe 1 offen.

- [ ] **Schritt 1: README**
- [ ] **Schritt 2: HANDOFF**
- [ ] **Schritt 3: Commit**

```bash
git add README.md docs/HANDOFF.md
git commit -m "docs: Etappe 4 beschreiben und das Handoff nachziehen"
```

---

## Selbstdurchsicht

**Spec-Abdeckung:**

| Spec-Abschnitt | Aufgabe |
|---|---|
| §3 ArbZG umgesetzt (geteilter Dienst, Tagesgrenze, Ruhezeit) | Aufgabe 3, 7 |
| §3 ArbZG abgegrenzt (Hinweis in der Oberfläche) | Aufgabe 3 Schritt 7, Aufgabe 11 |
| §5.2 Phase A/B | Aufgabe 4 |
| §5.2 Phase C/D | Aufgabe 5 |
| §5.4 Schranken | Aufgabe 5 Schritt 3 |
| §5.5 `MIN_BLOCK_MINUTES` | Aufgabe 4 (Konstante), Aufgabe 6 (Parameter) |
| §6 Suchkern, drei Eingriffe | Aufgabe 7 |
| §7 Migration `0008` | Aufgabe 3 |
| §8 API | Aufgabe 1, 3, 6, 8 |
| §9 Frontend | Aufgabe 2, 3, 9 |
| §10 Vorarbeiten | Aufgabe 1, 2 |
| §11 Deckungslücken fallen ab | kein Task — bewusst, `coverage_gaps_for_month()` bleibt unverändert |
| §12 Tests | in jeder Aufgabe |
| §2 Landminen | Aufgabe 6 Schritt 5 und 6 |

**Offener Punkt für den Bearbeiter:** Aufgabe 1 Schritt 3 enthält eine Verzweigung („prüfen, ob `replace_employee_constraints()` sich auf den Fenster-Zweig beschränken lässt"). Das ist kein Platzhalter, sondern eine bewusst offengelassene Refaktorierungsentscheidung, die erst am Code entschieden werden kann — beide Wege sind beschrieben.
