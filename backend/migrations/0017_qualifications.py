"""Nachweise: was eine Schicht verlangt, und wer ihn hat.

Drei Tabellen, und die interessante Spalte ist valid_until.

qualifications: der Katalog des Betriebs. Ein Name je Zeile, UNIQUE darauf -
"Ersthelfer" zweimal anzulegen erzeugt zwei Nachweise, die dasselbe meinen,
und danach traegt die eine Haelfte der Belegschaft den einen und die andere
den anderen.

employee_qualifications: wer welchen Nachweis hat, und BIS WANN. Das ist der
Punkt dieser Etappe. Ein Ersthelferschein laeuft nach zwei Jahren ab (DGUV
Vorschrift 1 Paragraph 26 verlangt die Auffrischung), ein Staplerschein
ebenso. Ein Nachweis ohne Ablaufdatum ist einer, den der Dienstplan noch
Jahre nach seinem Ende weiter beachtet - genau der Fehler, den die
Arbeitszeitfenster mit valid_from/valid_until schon vermeiden. NULL heisst
"laeuft nicht ab", nicht "abgelaufen".

shift_type_qualifications: was eine Schichtart verlangt. Sie gilt fuer JEDEN
auf dieser Schicht, nicht fuer einen davon - "mindestens ein Ersthelfer je
Schicht" waere eine Anzahl innerhalb einer Anzahl und damit ein eigenes
Modell. Was hier steht, ist die einfachere und haeufigere Aussage: diese
Arbeit darf nur machen, wer das kann.

Alle Verknuepfungstabellen mit ON DELETE CASCADE: ein Nachweis, den es nicht
mehr gibt, kann von niemandem gehalten und von keiner Schicht verlangt werden.
Bei employees ist es nicht noetig - seit 0014 werden Mitarbeiter anonymisiert,
nicht geloescht -, aber delete_employee() raeumt die persoenlichen Nebendaten
ausdruecklich weg, und dazu gehoert auch das hier.

TEXT fuer valid_until, wie jedes Datum in diesem Schema: das ganze Werkzeug
vergleicht ISO-Daten als Zeichenkette.

Beide Verknuepfungstabellen tragen eine eigene id-Spalte, obwohl das Paar
schon eindeutig ist - Fallstrick 16: die Dialektschicht haengt jedem INSERT
ohne RETURNING ein RETURNING id an, und eine Tabelle ohne id-Spalte scheitert
auf Postgres mit UndefinedColumn. Der erste Entwurf hatte hier einen
zusammengesetzten Primaerschluessel und lief auf SQLite einwandfrei; der
Schreibtest in test_migrations_postgres.py hat es gefangen. Die Eindeutigkeit
sagt jetzt UNIQUE, genau wie bei employee_allowed_shift_types in
0001_baseline.py.
"""

from db import use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS qualifications(
            id {_auto_id()},
            name TEXT NOT NULL UNIQUE
        )
    ''')
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS employee_qualifications(
            id {_auto_id()},
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            qualification_id INTEGER NOT NULL
                REFERENCES qualifications(id) ON DELETE CASCADE,
            valid_until TEXT,
            UNIQUE(employee_id, qualification_id)
        )
    ''')
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_type_qualifications(
            id {_auto_id()},
            shift_type_id INTEGER NOT NULL
                REFERENCES shift_types(id) ON DELETE CASCADE,
            qualification_id INTEGER NOT NULL
                REFERENCES qualifications(id) ON DELETE CASCADE,
            UNIQUE(shift_type_id, qualification_id)
        )
    ''')


def down(cursor):
    cursor.execute('DROP TABLE IF EXISTS shift_type_qualifications')
    cursor.execute('DROP TABLE IF EXISTS employee_qualifications')
    cursor.execute('DROP TABLE IF EXISTS qualifications')
