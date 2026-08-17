"""Arbeitszeitfenster: "Anna kann montags 08:00-14:00".

Mehrere Zeilen pro (employee_id, weekday) sind erlaubt und beschreiben einen
geteilten Dienst. Eine Schicht muss vollstaendig in EIN Fenster passen, nicht
in die Vereinigung mehrerer.

end_time <= start_time bedeutet Ueberschreitung nach Mitternacht, wie ueberall
sonst im Projekt (siehe scheduler.shift_duration_minutes).

valid_from/valid_until sind ISO-Daten oder NULL fuer unbegrenzt, beide Grenzen
einschliesslich. Damit laesst sich "ab September gilt etwas anderes" abbilden,
ohne die alte Zeile zu verlieren.

Warum .py und nicht .sql: das ALTER TABLE unten muss bedingt sein (siehe
up()), und der SQL-Pfad des Runners kennt keine Bedingungen. Damit muss auch
{auto_id} hier selbst aufgeloest werden - dieselbe Stelle wie in
0001_baseline.py, siehe _auto_id().
"""

from db import table_columns, use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    auto_id = _auto_id()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_availability(
            id {auto_id},
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            valid_from TEXT,
            valid_until TEXT
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS ix_availability_employee
            ON employee_availability(employee_id, weekday)
    ''')

    # 'anytime' = wie bisher, keine Uhrzeit-Einschraenkung. 'windows' = nur
    # innerhalb der Fenster oben. Der Schalter ist absichtlich explizit: ohne
    # ihn waere "hat keine Fenster" mehrdeutig, und jeder Bestandsdatensatz
    # muesste geraten werden. Der Standard haelt alle vorhandenen Mitarbeiter
    # unveraendert gueltig.
    #
    # Bedingt, nicht blank: down() entfernt die Spalte bewusst nicht (siehe
    # dort). Ein blankes ALTER TABLE ADD COLUMN wuerde diese Migration dadurch
    # unwiederholbar machen - nach einem einzigen "python migrations.py down"
    # scheitert der naechste Vorwaertslauf an der schon vorhandenen Spalte
    # (SQLite: duplicate column name, Postgres: DuplicateColumn; ADD COLUMN IF
    # NOT EXISTS gibt es auf SQLite nicht). Und da app.py init_db() beim
    # Modulimport aufruft und jeder Gunicorn-Worker die App nach dem Forken
    # selbst importiert, waere das keine Randnotiz, sondern eine Anwendung,
    # die ueberhaupt nicht mehr startet, bis jemand die Spalte von Hand
    # entfernt. Dieselbe bedingte Form wie bei den Spaltenergaenzungen in
    # 0001_baseline.py.
    if 'availability_mode' not in table_columns(cursor, 'employees'):
        cursor.execute(
            "ALTER TABLE employees ADD COLUMN availability_mode TEXT NOT NULL DEFAULT 'anytime'")


def down(cursor):
    """Nimmt nur die Tabelle zurueck, nicht die Spalte employees.availability_mode.

    SQLite kann DROP COLUMN erst ab Version 3.35 und selbst dann nicht in jeder
    Situation (z.B. auf Spalten mit CHECK-Constraint oder als Teil eines
    Fremdschluessels). Eine zurueckgebliebene Spalte mit sinnvollem Standard
    ('anytime', siehe up()) ist harmlos - jeder Bestandsdatensatz bleibt genauso
    gueltig wie vor der Migration. Ein Rollback, der an einem fehlenden
    DROP COLUMN scheitert, waere dagegen ein Rollback, der nicht funktioniert -
    schlimmer als eine harmlose Spalte, die liegen bleibt.

    Genau deshalb ist das ALTER in up() bedingt: die Spalte ueberlebt die
    Ruecknahme, der naechste Vorwaertslauf muss sie also vorfinden duerfen.
    """
    cursor.execute('DROP INDEX IF EXISTS ix_availability_employee')
    cursor.execute('DROP TABLE IF EXISTS employee_availability')
