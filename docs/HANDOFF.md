# Handoff — Stand und offene Punkte

Kompakte Übergabe, damit eine neue Sitzung ohne Vorwissen weiterarbeiten kann.
Stand: 16.08.2026.

## Das Projekt

Schichtplan-Tool für Personalabteilungen. Flask-Backend (`backend/`), React 19 + Vite
(`frontend/`). SQLite lokal, Postgres in Produktion — über eine **handgeschriebene
Dialektschicht** in `backend/db.py`, kein ORM. Backend auf Render, Frontend auf Vercel.

- Repo: https://github.com/MuhammetSah/scheduling-tool (öffentlich)
- Lokal: `C:\Users\muham\source\repos\scheduling-tool-main`
- API: https://schichtplan-api.onrender.com
- Render-Service `srv-d9r7b4ajobas73cplm1g`, Postgres `dpg-d9r7a7740ujc73arnp6g-a`

Kern ist `backend/scheduler.py`: Backtracking-Suche mit Branch-and-Bound, lexikografisches
Ziel (erst unbesetzte Schichten minimieren, dann Fairness über die Summe quadrierter
Schichtzahlen). Diese Suche wurde in beiden Etappen **nicht** angefasst.

## Aktueller Stand

| | |
|---|---|
| `main` | `4c2be23` — Etappe 0 gemergt (PR #9) + Blueprint-Anpassung (PR #10) |
| Arbeitsbranch | `etappe-1-arbeitszeitfenster`, PR #11 offen |
| Testsuite | 110 passed / 16 skipped (Postgres-only, lokal übersprungen), warnungsfrei unter `-W error::DeprecationWarning` |
| CI | 4 Jobs: `backend (3.13)`, `backend (3.14)`, `backend-postgres`, `frontend` |
| Migrationen | `0001`–`0003` in Produktion angewandt, `0004` auf dem Branch |
| Laufzeitabhängigkeiten | fünf: flask, flask-cors, gunicorn, psycopg2-binary, tzdata |

## Etappe 0 — abgeschlossen, gemergt, deployt

Produktionsreife-Fundament. 17 Commits, Suite von 23 auf 66 Tests.

- CI-Pipeline (vorher liefen die Tests nie automatisch)
- Versionierte Migrationen mit Rücknahme und Transaktion pro Migration; `init_db()`-Flickwerk abgelöst
- Abhängigkeiten exakt gepinnt
- `SECRET_KEY` in Produktion erzwungen (fiel vorher still auf einen im Quelltext veröffentlichten Wert zurück)
- Login-Drosselung, überlebt Neustart und mehrere Worker
- Fehlerantworten immer JSON, mit nachverfolgbarer `request_id`
- „Aktueller Monat" in der Betriebszeitzone statt UTC; `datetime.utcnow()` entfernt
- Rückfrage vor dem Überschreiben von Handkorrekturen
- Indizes und Eindeutigkeit auf `shift_assignments`
- Postgres in der CI; Advisory Lock gegen das Migrations-Rennen
- Betriebsrunbook im README

## Etappe 1 — in Arbeit: Arbeitszeitfenster

Plan: [`docs/superpowers/plans/2026-08-16-etappe-1-arbeitszeitfenster.md`](superpowers/plans/2026-08-16-etappe-1-arbeitszeitfenster.md)
Ledger: `.superpowers/sdd/2026-08-16-etappe-1-arbeitszeitfenster/progress.md` (gitignoriert)

Ziel: „Anna arbeitet Mo–Fr 08:00–14:00" wird ausdrückbar und vom Planer respektiert.

| Task | Stand | Commit |
|---|---|---|
| 1 Migration und Schema | ✅ Review sauber | `415caca` |
| 2 Fensterprüfung im Planer | ✅ Review sauber | `4c857d3` |
| 3 API — lesen und schreiben | ✅ Review sauber | `d5e1d14` |
| 4 Warnung bei Handkorrektur | ⚠️ implementiert, **Review steht aus** | `1f3e161` |
| 5 Frontend-Editor | ⬜ offen | — |
| 6 Dokumentation | ⬜ offen | — |

**Serverseitig funktioniert das Feature vollständig** — nachgewiesen durch einen Durchstichtest
mit echtem Gegenbeispiel. Es fehlt die Eingabemaske.

**Erster Schritt einer neuen Sitzung:** Task 4 reviewen lassen. Er ist implementiert und die CI
ist grün, aber er hat als einziger der vier fertigen Aufgaben noch kein unabhängiges Review
durchlaufen. Diff `d5e1d14..1f3e161`. Der Implementer meldet zwei bewusst nicht
diskriminierende „keine Warnung"-Tests — genau das ist der Punkt, den ein Review prüfen muss,
denn ein Test, der eine Abwesenheit behauptet, ohne dass derselbe Aufbau im anderen Modus
warnen würde, beweist nichts über den Schalter.

### Die Semantik, einmal präzise

`employees.availability_mode` ist `'anytime'` (Standard, wie bisher) oder `'windows'`.
Im Fenster-Modus gilt: nur innerhalb der eingetragenen Fenster; ein Wochentag ohne Fenster
heißt „an dem Tag gar nicht". `unavailable_dates` und Abwesenheiten gelten zusätzlich.

Eine Schicht ist erlaubt, wenn sie **vollständig in ein einzelnes** Fenster passt — nicht in
die Vereinigung mehrerer. Gerechnet in Minuten ab Mitternacht des Starttags; ein Ende ≤ Start
bekommt 1440 aufgeschlagen, für Fenster **und** Schicht. Der Wochentag ist der des
Schichtbeginns, auch bei Nachtschichten. Gültigkeitsgrenzen sind einschließlich.

Funktionen in `backend/scheduler.py`: `time_to_minutes()`, `window_contains_shift()`,
`window_is_valid_on()`. **Nicht duplizieren** — Task 4 und alles Spätere müssen sie
wiederverwenden, sonst driften Planer und Warnung auseinander.

## Arbeitsweise

Subagent-driven development (`superpowers:subagent-driven-development`): pro Aufgabe ein
frischer Implementer, danach ein unabhängiger Reviewer, der dem Bericht des Implementers
ausdrücklich **nicht** glauben darf. Bei Befunden Fix-Runden mit eng gefasstem Re-Review.
Fortschritt im Ledger, nicht nur im Kopf — er überlebt eine Kontextverdichtung.

Skripte: `scripts/sdd-workspace`, `scripts/task-brief`, `scripts/review-package` unter
`C:\Users\muham\.claude\plugins\cache\claude-plugins-official\superpowers\6.2.0\skills\subagent-driven-development\`

Modellwahl: Sonnet für Implementierung und Review, Opus für besonders riskante Reviews
(Migrations-Runner, Auth-Pfad, Gesamt-Review).

## Fallstricke dieses Projekts — das Wichtigste für eine neue Sitzung

1. **Kein literales `?` in SQL, auch nicht in Kommentaren.** `_PostgresCursor` ersetzt es
   bedingungslos durch `%s`. Ein `?` in einem Migrations-Kommentar hätte beinahe die
   Produktion lahmgelegt; gefunden nur, weil die Postgres-CI existierte.
2. **Semikolons in SQL-Kommentaren** zerteilen die Datei am naiven Splitter.
3. **Tests, die nichts prüfen — vier Fälle bisher.** Vor jedem Commit fragen: *Würde dieser
   Test fehlschlagen, wenn ich das Feature lösche?* Typische Muster: Operationen in falscher
   Reihenfolge gestaffelt; zwei Eingaben gleichzeitig variiert, sodass ein Filter vorher
   kurzschließt; eine Soll-Liste aus derselben Datei abgeleitet, die sie absichern soll.
4. **Die Tabellenliste in `test_migrations.py` ist absichtlich fest verdrahtet.** Nicht wieder
   in eine Ableitung zurückverwandeln.
5. **Die 23 Tests in `backend/test_scheduler.py` bleiben unverändert.** Sie sind die
   Rückwärtskompatibilitätsgarantie. Werden sie rot, ist die Änderung falsch, nicht der Test.
6. **Kommentarsprache folgt der Datei.** `app.py`, `db.py`, `scheduler.py`,
   `test_scheduler.py` sind englisch; `security.py`, `timeutil.py`, `migrations.py` und die
   neueren Testdateien deutsch. Zwei Sprachen in *einer* Datei sind der eigentliche Fehler.
   Commit-Nachrichten durchgehend deutsch, README englisch.
7. **`render.yaml` ist nicht, was läuft.** Der Render-Dashboard-Startbefehl überschreibt die
   Datei vollständig. Vor jeder Änderung dort prüfen, ob der Dienst der Datei überhaupt folgt.
8. **`--preload` nicht als Ballast entfernen.** Ohne es führt jeder Worker beim Start die
   Migrationen aus; stirbt einer beim Booten, fährt Gunicorn den *gesamten* Dienst herunter.
9. **Postgres-Verhalten nie aus SQLite schließen.** Lokal läuft nur SQLite. Der
   `backend-postgres`-Job ist die einzige echte Probe.
10. **Die Render-MCP-Abfrage funktioniert nicht** (kein SSL). Für Datenbankabfragen ein
    Python-Skript mit `psycopg2` und `sslmode='require'` nutzen.

## Offen — liegt beim Nutzer

- **Postgres läuft am 07.09.2026 ab.** Kostenloser Plan. Entscheidung nötig: bezahlter Plan,
  Umzug, oder bewusster Datenverlust. Datenbestand ist klein (3 Mitarbeiter, 62 Zuweisungen),
  also kein Notfall, aber ein Termin.
- **IP-Freigabe an der Datenbank entfernen.** Wurde für eine einmalige Prüfung gesetzt.
- **Datenbankpasswort wurde in einem Chatverlauf offengelegt** und sollte getauscht werden.
  Entschärft dadurch, dass externer Zugriff nur von einer IP erlaubt ist und die Instanz
  ohnehin am 07.09. verschwindet.
- **Render-Startbefehl angleichen** (optional): Dashboard → Settings → Start Command auf
  `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --threads 4 --timeout 60`
- **`pg_dump` fehlt**: `winget install --id PostgreSQL.PostgreSQL.18` (Version 18, passend zum Server)

## Zurückgestellte Befunde

Aus den Reviews, bewusst nicht behoben, für ein späteres Aufräumen:

- `ci.yml` Cache-Schlüssel deckt nur `requirements-dev.txt` ab
- `ortools` in `requirements-dev.txt` ungepinnt
- `password_not_set_yet`-Zweig in `login()` zählt keine Versuche
- Drosselungstests verdrahten `10/9/11` fest statt `security.MAX_FAILED_ATTEMPTS`
- `is_locked_out`/`record_attempt` sind check-then-act ohne Zeilensperre
- `HTTPException`-Fallback liefert für andere Codes als 404/405 einen unübersetzten Literal (aktuell unerreichbar)
- `handleMonthChange` setzt den geladenen Plan nicht zurück; Erzeugen-Knopf nicht gesperrt während des Ladens
- `fetchSchedule()` schluckt jeden GET-Fehler zu `null`
- `MIGRATIONS_DIR.iterdir()` wirft, wenn das Verzeichnis fehlt
- Zwei Validierungstests in `test_api_availability.py` prüfen nur den Status, nicht die Meldung
- **Frontend hat keinerlei Testinfrastruktur.** Bewusste Entscheidung; sollte spätestens mit
  dem Zeitachsen-Editor aus Etappe 3 nachgerüstet werden (Vitest + Testing Library)

## Roadmap

Design: [`docs/superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md`](superpowers/specs/2026-08-16-zeitachsen-dienstplan-design.md)

- **Etappe 2** — individuelle Zeiten pro Zuweisung: `shift_assignments.start_time/end_time`,
  `shift_type_id` nullable, damit ein freier Block „10:00–16:00" ohne passende Vorlage möglich wird
- **Etappe 3** — Öffnungszeiten und Bedarf auf der Zeitachse: `business_hours`,
  `business_hours_exceptions`, `coverage_requirements` (nicht überlappend, absolute
  Besetzungsstärke), Migration aus `shift_requirements`, Deckungslücken-Anzeige
- **Etappe 4** — Zuschnitt im Planer: Blockplanung aus Bedarf und Fenstern, automatisches
  Kürzen auf das Mitarbeiterfenster, benannte Restlücken. Das ist der Punkt, an dem das Tool
  über Papershift und Deputy hinausgeht — dort wird nicht automatisch zugeschnitten.
- **Etappe 5** — restliche Produktionsreife: Veröffentlichen-Workflow (`schedules.status` wird
  bis heute nicht genutzt), Audit-Log, Exporte, DSGVO (Krankmeldungen sind Art.-9-Daten),
  ArbZG-Prüfungen (max. 8/10 h, Pausen, max. 6 Tage in Folge)
