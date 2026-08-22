"""Taegliche Hoechstarbeitszeit je Mitarbeiter.

Gebraucht wird sie, seit eine Person mehrere Bloecke am selben Tag arbeiten
darf (geteilter Dienst, Etappe 4). Solange jeder hoechstens einen Block pro
Tag bekam, war die Schichtlaenge selbst die Grenze.

Paragraph 3 ArbZG: die werktaegliche Arbeitszeit darf acht Stunden nicht
ueberschreiten und nur dann bis auf zehn verlaengert werden, wenn innerhalb
von sechs Kalendermonaten oder 24 Wochen im Durchschnitt acht Stunden
eingehalten werden. Der Standard 10 ist also die Obergrenze des ueberhaupt
Zulaessigen, nicht die Normalvorgabe - und den Ausgleich prueft dieses Tool
nicht. Es kann ihn auch nicht pruefen: der Planer arbeitet monatsweise,
dieselbe Grenze, an der schon max_shifts_per_month und die Ruhezeitpruefung am
Monatsrand enden. Der Hinweis darauf steht in der Oberflaeche am Feld.

Gezaehlt wird die Summe der Blockdauern, nicht die Spanne vom ersten Beginn
bis zum letzten Ende - Paragraph 2 Abs. 1 ArbZG rechnet die Unterbrechung
eines geteilten Dienstes nicht zur Arbeitszeit.

NOT NULL mit Standard, nicht nullbar wie weekly_hours: 0001_baseline.py
begruendet dieselbe Entscheidung fuer min_rest_hours damit, dass eine
sicherheitsrelevante Einstellung nie unbesetzt sein soll. Fuer eine Grenze aus
dem Arbeitszeitgesetz gilt das erst recht - "keine Tagesgrenze" darf nicht die
stille Voreinstellung eines vergessenen Feldes sein.

Warum .py und nicht .sql: das ALTER unten muss bedingt sein, damit die
Migration nach ihrer eigenen Ruecknahme wieder vorwaerts laeuft - siehe down()
und die ausfuehrliche Begruendung in 0004_employee_availability.py.
"""

from db import table_columns


def up(cursor):
    if 'max_daily_hours' not in table_columns(cursor, 'employees'):
        cursor.execute(
            'ALTER TABLE employees ADD COLUMN max_daily_hours REAL NOT NULL DEFAULT 10')


def down(cursor):
    """Laesst die Spalte stehen - dieselbe Begruendung wie in 0004.

    SQLite kann DROP COLUMN erst ab 3.35 und selbst dann nicht in jeder Lage.
    Eine zurueckgebliebene Spalte mit sinnvollem Standard ist harmlos: jeder
    Bestandsdatensatz bleibt so gueltig wie vor der Migration, und der Planer
    liest den Wert ueber .get(), findet also auch ohne ihn seinen Weg. Ein
    Rollback, der an einem fehlenden DROP COLUMN scheitert, waere dagegen ein
    Rollback, der nicht funktioniert - schlimmer als eine harmlose Spalte.

    Genau deshalb ist das ALTER in up() bedingt: die Spalte ueberlebt die
    Ruecknahme, der naechste Vorwaertslauf muss sie also vorfinden duerfen.
    """
