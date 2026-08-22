"""Die alte Bedarfsquelle entfernen.

shift_requirements hat bis Etappe 3 gesagt, wie viele Leute eine Schichtart an
einem Wochentag braucht - "montags braucht die Fruehschicht 3 Leute". Seit
Etappe 4 baut der Planer seine Bloecke aus coverage_requirements, dem feineren
Modell ueber den Tagesverlauf; die alte Tabelle wurde seither noch geschrieben,
aber von nichts mehr gelesen, was den Plan beeinflusst.

Die uebergeordnete Spec sieht die Entfernung ausdruecklich "erst nach Etappe 4"
vor - bis dahin war sie die Rueckfallebene, falls der neue Pfad Probleme macht.
Er hat keine gemacht.

Die Daten gehen nicht verloren: Migration 0007 hat sie einmalig in
coverage_requirements ueberfuehrt, und genau das war ihr Zweck.

Reihenfolge auf einer frischen Datenbank: 0001 legt die Tabelle an, 0007 findet
sie (leer, leitet also nichts ab), 0010 entfernt sie. Das laeuft durch, und
0007 bleibt deshalb unangetastet - sie ist Geschichte.

Warum .py und nicht .sql: der Waechter unten. Ein blankes DROP TABLE scheiterte
beim zweiten Vorwaertslauf nach einer Ruecknahme nicht, wohl aber das CREATE in
down() nach einem zweiten Rueckwaertslauf - und der Runner soll sich in beide
Richtungen wiederholen lassen.
"""

from db import table_columns, use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    cursor.execute('DROP TABLE IF EXISTS shift_requirements')


def down(cursor):
    """Legt die Tabelle wieder an - LEER.

    Die Zeilen sind fort. Bei einem DROP ist das nicht anders zu haben, und es
    steht hier, damit niemand die zurueckgerollte Tabelle fuer vollstaendig
    haelt. Wer den Altbestand wirklich braucht, holt ihn aus einem Backup;
    inhaltlich lebt er ohnehin in coverage_requirements weiter.

    Die Definition ist aus 0001_baseline.py uebernommen statt von dort
    importiert. Eine zweite Fassung ist unschoen, aber zwei Migrationen
    aneinanderzukoppeln waere schlimmer: eine Migration muss lesbar bleiben,
    ohne dass man ihre Vorgaenger daneben legt.
    """
    # table_columns() statt eines eigenen table_exists(): fuer eine fehlende
    # Tabelle liefert es eine leere Menge, und eine Tabelle ohne Spalten gibt
    # es nicht. Ein zweiter Helfer daneben waere dieselbe Frage in einer
    # zweiten Fassung - inklusive der Postgres-Eigenheit mit current_schema(),
    # die dort schon geloest ist.
    if table_columns(cursor, 'shift_requirements'):
        return

    cursor.execute(f'''
        CREATE TABLE shift_requirements(
            id {_auto_id()},
            shift_type_id INTEGER NOT NULL REFERENCES shift_types(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL,
            required_count INTEGER NOT NULL DEFAULT 0
        )
    ''')
