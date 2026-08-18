"""Individuelle Zeiten pro Zuweisung, und Bloecke ohne Vorlage.

Zwei Aenderungen an shift_assignments:

1. start_time/end_time. NULL heisst "erbt wie bisher" - erst ein Eintrag in
   shift_time_overrides fuer dieses Datum, sonst die Zeit der Schichtart.
   Gefuellt heisst "genau diese Person arbeitet auf diesem Platz genau diese
   Zeit". Alle Bestandszeilen haben NULL und bleiben damit unveraendert gueltig.

2. shift_type_id wird nullable. Ein Block ohne Vorlage traegt seine Zeiten
   selbst; er ist die Voraussetzung fuer den Zuschnitt in Etappe 4, wo der
   Planer Restbedarf erzeugt, fuer den es keine passende Schichtart gibt.

Warum .py und nicht .sql: Postgres lockert NOT NULL mit ALTER COLUMN, SQLite
kann das nicht und braucht einen Tabellenneubau. Ausserdem ist der ALTER fuer
die beiden neuen Spalten bedingt, damit die Migration nach ihrer eigenen
Ruecknahme wieder vorwaerts laeuft - die Lehre aus dem Abschluss-Review von
Etappe 1.

Der UNIQUE-Index wird ersetzt statt geaendert: Postgres behandelt NULLs in
einem UNIQUE-Index als voneinander verschieden, ux_assignment_slot wuerde fuer
Bloecke ohne Vorlage also gar nichts mehr garantieren. COALESCE(shift_type_id, 0)
faengt das ab; 0 ist sicher, weil shift_types.id bei beiden Dialekten bei 1
beginnt.
"""

from db import table_columns, use_postgres


def _add_time_columns(cursor):
    spalten = table_columns(cursor, 'shift_assignments')
    if 'start_time' not in spalten:
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN start_time TEXT')
    if 'end_time' not in spalten:
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN end_time TEXT')


def _rebuild_indexes(cursor):
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_assignments_date_employee '
                   'ON shift_assignments(date, employee_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_assignments_schedule '
                   'ON shift_assignments(schedule_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot_v2 '
                   'ON shift_assignments(schedule_id, date, COALESCE(shift_type_id, 0), slot_index)')


def up(cursor):
    _add_time_columns(cursor)

    # Der alte Index kennt COALESCE nicht und wuerde fuer NULL-Schichtarten
    # nichts mehr garantieren. Zuerst weg, damit der Neubau unten ihn nicht
    # versehentlich wieder mitbringt.
    cursor.execute('DROP INDEX IF EXISTS ux_assignment_slot')

    if use_postgres():
        cursor.execute('ALTER TABLE shift_assignments ALTER COLUMN shift_type_id DROP NOT NULL')
    else:
        # SQLite kennt kein ALTER COLUMN. Neubau nach dem offiziell empfohlenen
        # Ablauf: neue Tabelle, kopieren, tauschen. Die Spaltenliste ist
        # absichtlich ausgeschrieben und nicht aus PRAGMA abgeleitet - eine
        # abgeleitete Liste wuerde jede kuenftige Spalte stillschweigend
        # mitnehmen und diesen Neubau von einer weiteren Migration abhaengig
        # machen.
        cursor.execute('''
            CREATE TABLE shift_assignments_neu(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                shift_type_id INTEGER REFERENCES shift_types(id),
                slot_index INTEGER NOT NULL,
                employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                manually_edited INTEGER NOT NULL DEFAULT 0,
                absence_type TEXT,
                absent_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
                start_time TEXT,
                end_time TEXT
            )
        ''')
        cursor.execute('''
            INSERT INTO shift_assignments_neu
                (id, schedule_id, date, shift_type_id, slot_index, employee_id,
                 manually_edited, absence_type, absent_employee_id, start_time, end_time)
            SELECT id, schedule_id, date, shift_type_id, slot_index, employee_id,
                   manually_edited, absence_type, absent_employee_id, start_time, end_time
            FROM shift_assignments
        ''')
        cursor.execute('DROP TABLE shift_assignments')
        cursor.execute('ALTER TABLE shift_assignments_neu RENAME TO shift_assignments')

    _rebuild_indexes(cursor)


def down(cursor):
    """Nimmt den Index zurueck und stellt den alten wieder her.

    Die beiden Zeitspalten bleiben stehen, und shift_type_id bleibt nullable -
    aus demselben Grund wie bei 0004: eine zurueckgebliebene Spalte mit NULL
    ist harmlos, und ein Rollback, der an einem nicht rueckbaubaren Schema
    scheitert, waere schlimmer als eine Lockerung, die bestehen bleibt. Der
    Vorwaertslauf ist dank der Waechter oben trotzdem wiederholbar.

    Achtung: existieren bereits Zeilen mit shift_type_id IS NULL, koennte der
    alte Index sie nicht mehr eindeutig halten. Da down() die Spalte nicht
    wieder auf NOT NULL zieht, ist das kein Fehlerfall, sondern nur der Grund,
    warum diese Ruecknahme bewusst unvollstaendig ist.
    """
    cursor.execute('DROP INDEX IF EXISTS ux_assignment_slot_v2')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot '
                   'ON shift_assignments(schedule_id, date, shift_type_id, slot_index)')
