"""Anonymisierung: eine geloeschte Person wird zum Grabstein.

Bis hierher setzte ON DELETE SET NULL die Zuweisungen einer geloeschten Person
auf "unbesetzt". Das ist schlechter, als es klingt: die Vergangenheit sieht
danach unterbesetzt aus, Deckungsluecken erscheinen rueckwirkend, und die
Arbeitszeitaufzeichnung nach Paragraph 16 Abs. 2 ArbZG verliert genau die
Zuordnung, die sie ausmacht.

Stattdessen bleibt die Mitarbeiterzeile stehen, ohne Person: Name ersetzt,
E-Mail entfernt, inaktiv, und alles Persoenliche daneben geloescht. Die
Zuweisungen zeigen weiter darauf.

Art. 17 Abs. 3 lit. b DSGVO nimmt Verarbeitung aus, die zur Erfuellung einer
rechtlichen Verpflichtung erforderlich ist - Paragraph 16 Abs. 2 ArbZG ist
eine. Was bleibt, ist die Arbeitszeitaufzeichnung ohne Person; was geht, ist
die Person.

Diese Spalte unterscheidet den Grabstein vom lebenden Datensatz, damit die
Oberflaeche ihn nicht zum Bearbeiten anbietet und die Mitarbeiterliste ihn
nicht mitzaehlt.
"""

from db import table_columns


def up(cursor):
    if 'anonymized_at' not in table_columns(cursor, 'employees'):
        cursor.execute('ALTER TABLE employees ADD COLUMN anonymized_at TIMESTAMP')


def down(cursor):
    """Laesst die Spalte stehen - dieselbe Begruendung wie in 0004, 0008 und 0009.

    SQLite kann DROP COLUMN nicht verlaesslich, und eine zurueckgebliebene
    nullbare Spalte ist harmlos.
    """
