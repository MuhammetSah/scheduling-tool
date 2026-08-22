"""Aenderungsprotokoll: wer hat wann was angefasst.

published_at beantwortet seit 0012 das Seit-wann eines Plans, aber nicht das
Wer. Bei einem Streit ueber den Dienstplan ist das die zweite Frage.

Protokolliert wird auf Anfrageebene - Methode, Pfad, Status, Benutzer - und
ausdruecklich OHNE Anfrageinhalte. Ein fachliches Protokoll ("Anna auf
Fruehschicht gesetzt") laese sich besser, wuerde aber Krankmeldungen ein
zweites Mal wegschreiben, und die sind Gesundheitsdaten nach Art. 9 DSGVO. Das
ist eine Entscheidung des Betreibers, keine des Schemas.

Kein Fremdschluessel auf users, und der Benutzername steht als Kopie daneben:
Konten werden geloescht (DELETE /accounts/<id>), und mit ON DELETE CASCADE
verschwaende das Protokoll mit ihnen. Ein Protokoll, dessen Eintraege sich
loeschen lassen, indem man das Konto loescht, ist keines. user_id bleibt als
blosse Zahl stehen, damit zusammenhaengende Eintraege auffindbar sind.

Das Protokoll ist selbst personenbezogen und braucht eine Aufbewahrungsfrist.
Die festzulegen ist Sache des Betreibers und gehoert zum DSGVO-Teil - hier
steht sie bewusst nicht.

Der Index liegt auf at, weil jede Abfrage "die letzten N" lautet.
"""

from db import use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS audit_log(
            id {_auto_id()},
            at TIMESTAMP NOT NULL,
            user_id INTEGER,
            username TEXT,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            status INTEGER NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS ix_audit_log_at ON audit_log(at)')


def down(cursor):
    cursor.execute('DROP INDEX IF EXISTS ix_audit_log_at')
    cursor.execute('DROP TABLE IF EXISTS audit_log')
