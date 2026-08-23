"""Die Lage der Pause, nicht nur ihre Dauer.

Paragraph 4 Satz 3 ArbZG: "Laenger als sechs Stunden hintereinander duerfen
Arbeitnehmer nicht ohne Ruhepause beschaeftigt werden." Bis hierhin kannte das
Tool nur break_minutes - eine Dauer ohne Uhrzeit -, und konnte den Satz
deshalb gar nicht pruefen. Eine halbe Stunde Pause ab Schichtbeginn erfuellt
Satz 1 und verstoesst gegen Satz 3, und beide Faelle sahen in der Datenbank
gleich aus.

Paragraph 4 Satz 1 verlangt ohnehin "im voraus feststehende Ruhepausen". Eine
Dauer ohne Lage steht nicht fest; die Spalte schliesst also nicht nur eine
Pruefluecke, sondern auch eine Modelluecke.

NULL-bar und ohne Vorgabe. Fuer jeden Block, den dieses Tool bauen kann -
hoechstens zehn Stunden Spanne, mindestens dreissig Minuten Pause - gibt es
immer eine zulaessige Lage; eine fehlende Angabe ist deshalb nie ein bekannter
Verstoss. Sie zu erzwingen hiesse, jeden Bestandsplan fuer ungueltig zu
erklaeren, und eine erfundene Vorgabe waere eine Behauptung ueber einen
Betriebsablauf, den das Tool nicht kennt.

Eine Lage je Block. Paragraph 4 Satz 2 erlaubt, die Pause in Abschnitte von je
mindestens fuenfzehn Minuten zu teilen - das waere eine eigene Tabelle. Nicht
abzubilden macht das Tool an dieser Stelle strenger, nicht laxer: wer teilt,
traegt die Lage des laengsten Abschnitts ein und bekommt eher eine Meldung als
zu wenige. Das gehoert gesagt, nicht verschwiegen.

Text und nicht TIME, wie alle Uhrzeiten in diesem Schema (siehe start_time in
0005_assignment_times): das ganze Werkzeug vergleicht "HH:MM" als
Zeichenkette, und eine einzelne abweichende Spalte waere die Ausnahme, die
jede Abfrage kennen muesste.
"""

from db import table_columns


def up(cursor):
    if 'break_start' not in table_columns(cursor, 'shift_assignments'):
        cursor.execute('ALTER TABLE shift_assignments ADD COLUMN break_start TEXT')


def down(cursor):
    """Die Spalte bleibt stehen.

    Dieselbe Entscheidung wie in 0008 und 0014: SQLite kann eine Spalte nur
    ueber einen Tabellenneubau entfernen, und den fuer eine NULL-bare
    Zusatzspalte zu fahren ist mehr Risiko als Nutzen. up() ist ueber
    table_columns() ohnehin wiederholbar.
    """
