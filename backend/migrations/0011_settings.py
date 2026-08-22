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
"""

def up(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings(
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')


def down(cursor):
    cursor.execute('DROP TABLE IF EXISTS settings')
