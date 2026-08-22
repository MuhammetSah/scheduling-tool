"""Eine Tabelle fuer betriebsweite Einstellungen.

Bis hierher hatte das Projekt keinen Ort dafuer. Der erste Schluessel ist
holiday_region, der zweistellige Ländercode fuer den Feiertagskalender -
Paragraph 9 ArbZG verbietet Feiertagsarbeit, nennt aber keine Feiertage und
ueberlaesst die Fuellung dem Landesrecht.

Ohne Eintrag kennt das Tool keine Feiertage und verhaelt sich wie zuvor. Es
gibt bewusst kein Standard-Bundesland: eines zu raten waere schlechter als
keines zu haben.

Eine Schluessel-Wert-Tabelle fuer eine einzige Einstellung ist grenzwertig
YAGNI. Sie gewinnt trotzdem, weil es keinen anderen Ort gibt, an den die
Einstellung gehoert, und weil aus Etappe 5 absehbar weitere kommen
(Veroeffentlichen-Workflow, Aufbewahrungsfristen). Eine Spalte an einer
fachfremden Tabelle waere der schlechtere Kompromiss.

Die Spalte heisst name und nicht key: key ist in manchen SQL-Dialekten heikel,
und die Dialektschicht dieses Projekts soll sich damit nicht befassen muessen.

Warum eine id-Spalte, obwohl name der natuerliche Schluessel waere: die
Dialektschicht in db.py haengt an jedes INSERT ohne eigenes RETURNING ein
RETURNING id an, damit lastrowid auch auf Postgres funktioniert. Eine Tabelle
ohne id ist damit auf Postgres nicht beschreibbar - auf SQLite dagegen schon,
weshalb es lokal nicht auffaellt. Gekostet hat das einen roten
backend-postgres-Job.
"""

from db import use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS settings(
            id {_auto_id()},
            name TEXT NOT NULL UNIQUE,
            value TEXT NOT NULL
        )
    ''')


def down(cursor):
    cursor.execute('DROP TABLE IF EXISTS settings')
