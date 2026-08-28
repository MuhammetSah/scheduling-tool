"""Ein Zaehler je Konto, mit dem sich ausgegebene Anmeldetoken entwerten lassen.

Das Bearer-Token aus app.py ist signiert und zustandslos: es traegt die
Benutzer-ID, laeuft nach dreissig Tagen ab und wird bis dahin von jeder
Anfrage akzeptiert. Zustandslos heisst aber auch: es gab nichts, was es
vorzeitig ungueltig machen konnte.

Der Fall, in dem das zaehlt, ist genau der, fuer den es die Schaltflaeche
"Passwort zuruecksetzen" gibt. Sie setzt users.hash auf den leeren String, das
alte Passwort ist damit wertlos - und das Token, das mit ihm erzeugt wurde,
blieb trotzdem noch bis zu dreissig Tage lang gueltig. Wer ein Konto
zuruecksetzt, weil ein Geraet abhanden gekommen ist oder jemand das Haus
verlassen hat, tat damit nachweislich nichts: die alte Sitzung las weiter den
Dienstplan.

Der Zaehler schliesst das ohne Sitzungstabelle. Er wandert in das signierte
Token hinein und wird bei jeder Anfrage gegen die Spalte hier verglichen;
stimmen sie nicht ueberein, ist das Token ungueltig. Ein Zuruecksetzen erhoeht
ihn, und damit fallen alle Token dieses Kontos in einem Schritt.

Vorgabe 0, und ein Token ohne die Angabe zaehlt ebenfalls als 0: die
Umstellung meldet niemanden ab, der gerade angemeldet ist. Erst das naechste
Zuruecksetzen wirkt - was genau die Absicht ist.

INTEGER und nicht TIMESTAMP: verglichen wird auf Gleichheit, nicht auf
"aelter als". Ein Zeitstempel brauchte eine Aufloesung feiner als die Sekunde,
sonst faellt ein Token, das in derselben Sekunde ausgestellt wird wie das
Zuruecksetzen, durch das Raster.
"""

from db import table_columns


def up(cursor):
    if 'token_epoch' not in table_columns(cursor, 'users'):
        cursor.execute('ALTER TABLE users ADD COLUMN token_epoch INTEGER NOT NULL DEFAULT 0')


def down(cursor):
    """Die Spalte bleibt stehen.

    Dieselbe Entscheidung wie in 0008, 0014 und 0016: SQLite kann eine Spalte
    nur ueber einen Tabellenneubau entfernen, und den fuer eine Zahlspalte mit
    Vorgabe zu fahren ist mehr Risiko als Nutzen. up() ist ueber
    table_columns() ohnehin wiederholbar.
    """
