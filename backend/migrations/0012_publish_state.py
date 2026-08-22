"""Veroeffentlichen-Workflow: aus schedules.status wird ein Zustand mit Bedeutung.

Die Spalte gibt es seit 0001. Sie wurde beim Erzeugen auf 'generated' gesetzt,
in die Antwort geschrieben - und von nichts gelesen. Jeder Plan war sichtbar,
sobald er erzeugt war, auch der halbfertige.

Ab hier sind es zwei Werte: 'draft' und 'published'. Erst der veroeffentlichte
ist fuer Mitarbeiter da.

**Bestandsplaene werden veroeffentlicht, nicht Entwurf.** Das ist die
entscheidende Richtung: eine Migration darf nicht aendern, was Leute gestern
sehen konnten. Auf 'draft' zu setzen liesse alle laufenden Plaene verschwinden,
bis jemand sie einzeln freigibt - und niemand wuesste warum.

published_at beantwortet "seit wann sehen die Leute das?", die Frage, die bei
einem Streit ueber den Dienstplan zuerst kommt. NULL bei einem Entwurf.

Kein CHECK auf status: das Projekt hat auf keiner Tabelle welche, die API ist
der einzige Schreiber, und ein CHECK auf SQLite spaeter zu aendern verlangt den
Tabellenneubau, den 0005_assignment_times schon einmal gekostet hat. Die
erlaubten Werte stehen an einer Stelle im Code.
"""

from db import table_columns


def up(cursor):
    if 'published_at' not in table_columns(cursor, 'schedules'):
        cursor.execute('ALTER TABLE schedules ADD COLUMN published_at TIMESTAMP')

    cursor.execute(
        "UPDATE schedules SET status = 'published', published_at = CURRENT_TIMESTAMP "
        "WHERE status = 'generated'")


def down(cursor):
    """Setzt die Zustaende zurueck auf 'generated' und laesst die Spalte stehen.

    Die Spalte zu behalten ist dieselbe Entscheidung wie in 0004 und 0008:
    SQLite kann DROP COLUMN nicht verlaesslich, und eine zurueckgebliebene
    nullbare Spalte ist harmlos. Der Zustand dagegen gehoert zurueckgedreht -
    sonst faende der Bestand nach einem Rollback Werte vor, die die alte
    Fassung nicht kennt.

    'draft' wird dabei ebenfalls zu 'generated': vor dieser Migration gab es
    nur den einen Wert, und ein Entwurf war schlicht ein erzeugter Plan.
    """
    cursor.execute(
        "UPDATE schedules SET status = 'generated' WHERE status IN ('draft', 'published')")
