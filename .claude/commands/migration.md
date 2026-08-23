---
description: Legt eine neue Schemamigration nach den Regeln dieses Projekts an
argument-hint: [kurzer Name, z. B. urlaubskontingente]
---

Lege eine neue Migration für: $ARGUMENTS

Vorgehen:

1. `ls backend/migrations/` — die nächste freie vierstellige Nummer nehmen, den
   Namen in `snake_case` anhängen (`0018_urlaubskontingente.py`).
2. Eine bestehende `.py`-Migration als Muster lesen, nicht aus dem Kopf
   schreiben. `.sql` nur für reine Indizes ohne Spaltenänderung.
3. Die Regeln, an denen dieses Projekt schon geblutet hat:
   - **Kein literales `?` im SQL, auch nicht im Kommentar** — die
     Postgres-Dialektschicht ersetzt es bedingungslos durch `%s`.
   - **Keine Semikolons in SQL-Kommentaren** — der Splitter zerteilt daran.
   - **Jede Tabelle, in die eingefügt wird, braucht eine eigene `id`-Spalte**;
     Eindeutigkeit sagt man mit `UNIQUE`, nicht mit zusammengesetztem
     Primärschlüssel.
   - **`ADD COLUMN` gehört hinter einen `table_columns()`-Wächter**, damit die
     Migration nach ihrer eigenen Rücknahme wieder vorwärts läuft.
4. Rücknahme (`down`) mitschreiben.
5. Rundlauftest **up → down → up** in `backend/test_migrations.py` ergänzen; die
   fest verdrahtete Tabellenliste dort mitpflegen, nicht durch eine Ableitung
   ersetzen.
6. Wenn Personendaten betroffen sind: die neue Tabelle in die Löschliste in
   `delete_employee()` eintragen — sonst überlebt die Angabe die Anonymisierung.
7. `cd backend && ./venv/bin/python -m pytest test_migrations.py -q` laufen
   lassen und melden, dass die Postgres-Probe erst in der CI stattfindet
   (`backend-postgres`), weil lokal nur SQLite läuft.
