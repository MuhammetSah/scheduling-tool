"""Der gefuehrte Schichttausch: Antraege statt vollendeter Tatsachen.

Getauscht werden konnte schon vorher, aber nur durch die Personalabteilung und
nur sofort: zwei Zellen anklicken, fertig, Warnungen hinterher. Wer selbst
tauschen wollte, musste jemanden bitten, es fuer ihn zu tun.

Drei Schritte, und jeder ist tragend:

1. Der Antragsteller bietet eine EIGENE Schicht an und nennt eine Kollegin
   oder einen Kollegen - nicht deren Schicht.
2. Der Tauschpartner stimmt zu und waehlt dabei selbst, welche seiner
   Schichten er dagegen gibt. Ohne seine Zustimmung waere es kein Tausch,
   sondern eine Umsetzung.
3. Die Personalabteilung genehmigt. Erst dann bewegt sich etwas.

Dass der Antragsteller die Gegenschicht NICHT benennt, ist keine Bequemlichkeit,
sondern folgt aus Etappe 5f: ein Mitarbeiter sieht ausschliesslich seine eigenen
Schichten. Ihn eine fremde auswaehlen zu lassen hiesse, ihm zuerst den
Dienstplan aller anderen zu zeigen - und damit eine Datensparsamkeit
zurueckzunehmen, die bewusst so entschieden wurde. Der Partner weiss selbst am
besten, welche seiner Schichten er entbehren kann.

Deshalb ist partner_assignment_id NULL-bar: sie wird erst mit der Zustimmung
gesetzt.

Der dritte Schritt ist keine Foermelei. Das Arbeitszeitgesetz richtet sich an
den Arbeitgeber (Paragraph 22 Abs. 1 macht einen Verstoss zur
Ordnungswidrigkeit des Arbeitgebers), und die Aufzeichnungspflicht aus
Paragraph 16 Abs. 2 trifft ebenfalls ihn. Zwei Kolleginnen, die den Dienstplan
unter sich aendern, verschoeben eine Verantwortung, die das Gesetz woanders
verortet.

Verwiesen wird auf die Zuweisungen, nicht auf Datum und Schichtart: ein Antrag
soll ungueltig werden, wenn die Schicht verschwindet. ON DELETE CASCADE
erledigt das - ein Antrag auf einen geloeschten Platz ist kein Antrag mehr,
sondern Muell.

employee_id ohne CASCADE: seit 0014 werden Mitarbeiter anonymisiert statt
geloescht, die Zeile bleibt also stehen. Ein Fremdschluessel darauf bleibt
gueltig.

Kein Freitextfeld fuer eine Begruendung, und das ist Absicht. Ein Kasten
"warum moechtest du tauschen" holt sich "Arzttermin" und "meine Mutter ist im
Krankenhaus" - Gesundheitsdaten nach Art. 9 DSGVO, in einer Tabelle ohne Frist
und ohne besondere Behandlung. Aus demselben Grund protokolliert 0013 keine
Anfrageinhalte. Wer eine Begruendung braucht, sagt sie der
Personalabteilung; das Tool muss sie nicht aufbewahren.

Kein Index auf status: die Tabelle enthaelt Antraege eines laufenden Monats,
nicht die Geschichte des Betriebs. Die Indizes liegen auf den beiden
Mitarbeiterspalten, weil jede Abfrage "meine Antraege" lautet.
"""

from db import use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS shift_swap_requests(
            id {_auto_id()},
            requester_employee_id INTEGER NOT NULL REFERENCES employees(id),
            requester_assignment_id INTEGER NOT NULL
                REFERENCES shift_assignments(id) ON DELETE CASCADE,
            partner_employee_id INTEGER NOT NULL REFERENCES employees(id),
            partner_assignment_id INTEGER
                REFERENCES shift_assignments(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP NOT NULL,
            decided_at TIMESTAMP,
            decided_by_user_id INTEGER
        )
    ''')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS ix_swap_requests_requester '
        'ON shift_swap_requests(requester_employee_id)')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS ix_swap_requests_partner '
        'ON shift_swap_requests(partner_employee_id)')


def down(cursor):
    cursor.execute('DROP INDEX IF EXISTS ix_swap_requests_requester')
    cursor.execute('DROP INDEX IF EXISTS ix_swap_requests_partner')
    cursor.execute('DROP TABLE IF EXISTS shift_swap_requests')
