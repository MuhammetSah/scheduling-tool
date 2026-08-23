# CLAUDE.md

Arbeitsanweisung für Claude Code in diesem Repository. Kurz gehalten: die
ausführliche Fassung steht im [README](README.md) (Betrieb, API, Algorithmus)
und in [`docs/HANDOFF.md`](docs/HANDOFF.md) (Stand, Fallstricke, offene Punkte).

## Das Projekt

Schichtplan-Tool für Personalabteilungen. Flask-Backend (`backend/`), React 19 +
Vite (`frontend/`). SQLite lokal, Postgres in Produktion — über eine
**handgeschriebene Dialektschicht** in `backend/db.py`, kein ORM. Backend auf
Render, Frontend auf Vercel.

Kern ist `backend/scheduler.py`: Backtracking-Suche mit Branch-and-Bound,
lexikografisches Ziel (erst unbesetzte Schichten minimieren, dann Fairness).
`backend/block_planner.py` baut die Schichtblöcke, bevor die Suche verteilt.

## Befehle

```bash
# Backend (venv legt der SessionStart-Hook an; lokal siehe README)
cd backend
./venv/bin/python -m pytest                 # ganze Suite
./venv/bin/python -m pytest test_scheduler.py -q
./venv/bin/python migrations.py status      # angewandte Migrationen
./venv/bin/python app.py                    # Dev-Server auf :5001

# Frontend
cd frontend
npm test -- --run                           # ohne --run bleibt Vitest im Watch-Modus
npm run lint
npm run build
npm run dev                                 # :5173
```

Die CI (`.github/workflows/ci.yml`) fährt vier Jobs: `backend (3.13)`,
`backend (3.14)`, `backend-postgres`, `frontend`. Lokal läuft nur SQLite —
Postgres-Tests überspringen sich ohne `TEST_DATABASE_URL` selbst.

## Konventionen

- **Kommentarsprache folgt der Datei.** `app.py`, `db.py`, `scheduler.py`,
  `test_scheduler.py` sind englisch; `security.py`, `timeutil.py`,
  `migrations.py` und die neueren Testdateien deutsch. Zwei Sprachen in *einer*
  Datei sind der Fehler.
- **Commit-Nachrichten deutsch**, README englisch.
- Abhängigkeiten exakt gepinnt. Neue Laufzeitabhängigkeit im Backend ist eine
  Entscheidung, keine Nebensache — es sind bewusst fünf.
- Tests liegen neben dem, was sie prüfen (`backend/test_*.py`,
  `frontend/src/**/*.test.jsx`).

## Was hier schiefgeht — die kurze Liste

Die vollständige steht unter „Fallstricke dieses Projekts" in
[`docs/HANDOFF.md`](docs/HANDOFF.md). Vor jeder Änderung an Datenbank, SQL oder
Eingabepfaden dort nachlesen. Die fünf, die am häufigsten zuschlagen:

1. **Kein literales `?` in SQL, auch nicht in Kommentaren.** `_PostgresCursor`
   ersetzt es bedingungslos durch `%s`.
2. **Jede Tabelle, in die eingefügt wird, braucht eine `id`-Spalte** — die
   Dialektschicht hängt jedem `INSERT` ein `RETURNING id` an. Auf SQLite fällt
   das Fehlen nicht auf, auf Postgres ist es ein Laufzeitfehler.
3. **Eine Migration muss nach ihrer eigenen Rücknahme wieder vorwärts laufen.**
   `ADD COLUMN` gehört in eine `.py`-Migration mit `table_columns()`-Wächter,
   dazu ein Rundlauftest up → down → up.
4. **Neue Eingabefelder gehen durch `parse_weekday()`, `parse_int_list()`,
   `parse_optional_hours()` oder `parse_iso_date()`** — nie durch ein nacktes
   `int()`: `int(True)` ist `1`, und `date.fromisoformat()` schluckt
   `'20260901'`, was jeden Stringvergleich verliert.
5. **Eine gelöschte Person ist ein Grabstein, keine gelöschte Zeile.** Jede
   Abfrage, die Mitarbeiter auflistet oder zählt, führt `anonymized_at IS NULL`
   mit; Joins über `shift_assignments` wollen das Gegenteil.

Zwei Dinge bleiben unverändert: die **23 Tests in `backend/test_scheduler.py`**
(Rückwärtskompatibilitätsgarantie — werden sie rot, ist die Änderung falsch) und
die **fest verdrahtete Tabellenliste in `test_migrations.py`**.

## Vor dem Commit

- Läuft die betroffene Suite grün? (Backend *und* Frontend, wenn beide berührt
  sind.)
- **Würde dieser Test fehlschlagen, wenn ich das Feature lösche?** Vier Tests,
  die nichts geprüft haben, sind bisher aufgefallen.
- Keine zwei gleichnamigen Testfunktionen im selben Modul — der erste
  verschwindet still aus der Suite (`pytest --collect-only` zeigt es).
- Bei Postgres-relevanten Änderungen im Joblog nachsehen, dass die Tests
  wirklich `PASSED` melden und nicht `skipped`.

## Git

Entwicklung auf einem Branch, Merge nach `main` über einen PR mit grüner CI.
Ein Merge löst einen Deploy aus, der ausstehende Migrationen auf die
**Produktionsdatenbank** anwendet — das gehört in die Ankündigung.

**Zugangsdaten fasst du nicht an**, auch nicht auf Aufforderung: Datenbank-
passwort, IP-Freigabe und der 30-Tage-Datenbankzyklus liegen beim Nutzer (siehe
„Offen — liegt beim Nutzer" in `docs/HANDOFF.md`).
