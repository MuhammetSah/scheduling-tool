"""Ruhepause je Zuweisung.

Paragraph 4 ArbZG verlangt Ruhepausen von mindestens 30 Minuten bei mehr als
sechs bis zu neun Stunden und 45 Minuten daruueber, und Paragraph 2 Abs. 1
rechnet sie ausdruecklich nicht zur Arbeitszeit. Bis hierher kannte das Tool
keine Pausen: es hat Arbeitszeit brutto gerechnet und damit Plaene erzeugt, die
so nicht zulaessig waren.

NULL heisst "nicht abweichend geregelt" und wird als die gesetzliche
Mindestpause fuer die Laenge dieses Blocks gelesen (siehe
scheduler.legal_break_minutes). Ein gesetzter Wert ist die tatsaechliche Pause
- auch eine 0, wenn HR das ausdruecklich so eintraegt; gewarnt wird darueber in
constraint_warnings(), gespeichert wird, was dasteht.

Damit folgt das Feld dem dreistufigen Muster, das das Projekt fuer Zeiten schon
zweimal benutzt (eigene Zeit, Datums-Override, Schichtart): der Regelfall steht
nirgends geschrieben und ergibt sich, gespeichert wird nur die Abweichung. Alle
Bestandszeilen bleiben unveraendert gueltig und bekommen rueckwirkend die
richtige Pause.

Warum nullbar und nicht NOT NULL DEFAULT 0 - anders als max_daily_hours in
0008: dort ist der Standard eine Sicherheitsgrenze, die nie unbesetzt sein
soll. Hier waere eine 0 eine Aussage ("keine Pause"), und die muss von "nicht
abweichend geregelt" unterscheidbar bleiben. Ein DEFAULT 0 legte jede
Bestandszeile ruecckwirkend auf einen Plan fest, den Paragraph 4 nicht zulaesst.

Warum .py und nicht .sql: das ALTER unten muss bedingt sein, damit die
Migration nach ihrer eigenen Ruecknahme wieder vorwaerts laeuft - siehe down()
und die ausfuehrliche Begruendung in 0004_employee_availability.py.
"""

from db import table_columns


def up(cursor):
    if 'break_minutes' not in table_columns(cursor, 'shift_assignments'):
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN break_minutes INTEGER')


def down(cursor):
    """Laesst die Spalte stehen - dieselbe Begruendung wie in 0004 und 0008.

    SQLite kann DROP COLUMN erst ab 3.35 und selbst dann nicht in jeder Lage.
    Eine zurueckgebliebene nullbare Spalte ist hier besonders harmlos: NULL ist
    ohnehin der Regelfall, und jeder Leser kommt ohne die Spalte genauso weit
    wie mit ihr. Ein Rollback, der an einem fehlenden DROP COLUMN scheitert,
    waere dagegen ein Rollback, der nicht funktioniert.

    Genau deshalb ist das ALTER in up() bedingt: die Spalte ueberlebt die
    Ruecknahme, der naechste Vorwaertslauf muss sie also vorfinden duerfen.
    """
