"""Oeffnungszeiten, Ausnahmen davon und Bedarfsbaender ueber den Tagesverlauf.

Drei neue Tabellen, keine Ableitung von Bedarf - das ist eine spaetere Etappe,
nachdem die Rechenlogik dafuer bewiesen ist.

business_hours: eine Zeile je Wochentag (0=Montag..6=Sonntag, siehe
db.WEEKDAYS), UNIQUE(weekday) erzwingt genau eine. end_time <= start_time
bedeutet Ueberschreitung nach Mitternacht, wie ueberall sonst im Projekt
(siehe scheduler.shift_duration_minutes und 0004_employee_availability.py).

business_hours_exceptions: punktuelle Abweichungen fuer ein einzelnes Datum
(Feiertag, Sonderoeffnung), UNIQUE(date) haelt das eindeutig. open_time/
close_time sind hier nullbar - ein geschlossener Feiertag braucht keine
Uhrzeiten, closed traegt dann die eigentliche Aussage.

coverage_requirements: wie viele Personen zwischen start_time und end_time an
einem Wochentag gebraucht werden. Kein UNIQUE ueber (weekday, start_time,
end_time): mehrere, sich ueberschneidende Baender pro Tag sind ausdruecklich
erlaubt (z.B. ein durchgehendes Band plus ein zusaetzliches ueber die
Mittagsspitze). Der Index auf weekday ist eine reine Lesebeschleunigung fuer
"alle Baender eines Wochentags", ohne eine Eindeutigkeitsaussage zu machen.

Warum .py und nicht .sql: die sieben Standardzeilen fuer business_hours
muessen bedingt eingefuegt werden (siehe unten), und der SQL-Pfad des Runners
kennt keine Bedingungen. Damit muss auch {auto_id} hier selbst aufgeloest
werden - dieselbe Stelle wie in 0001_baseline.py, siehe _auto_id().
"""

from db import use_postgres


def _auto_id():
    return 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT'


def up(cursor):
    auto_id = _auto_id()

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS business_hours(
            id {auto_id},
            weekday INTEGER NOT NULL UNIQUE,
            open_time TEXT NOT NULL,
            close_time TEXT NOT NULL,
            closed INTEGER NOT NULL DEFAULT 0
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS business_hours_exceptions(
            id {auto_id},
            date TEXT NOT NULL UNIQUE,
            open_time TEXT,
            close_time TEXT,
            closed INTEGER NOT NULL DEFAULT 0,
            label TEXT
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS coverage_requirements(
            id {auto_id},
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            required_count INTEGER NOT NULL DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS ix_coverage_requirements_weekday
            ON coverage_requirements(weekday)
    ''')

    # Sieben Standardzeilen, eine je Wochentag: 00:00-00:00 mit closed=0 ist
    # nach der Mitternachtskonvention oben "der ganze Tag" - der einzige
    # Standard, der kein bestehendes Verhalten aendert, weil es vor dieser
    # Migration ueberhaupt keine Oeffnungszeiten gab und ihre Einfuehrung
    # deshalb nichts verbieten darf, was vorher erlaubt war.
    #
    # Das INSERT unten ist absichtlich bedingt und nicht blank: INSERT ist
    # nicht idempotent. Ohne diese Pruefung stuenden nach einer Ruecknahme
    # und einem erneuten Vorwaertslauf entweder vierzehn Zeilen da, oder der
    # UNIQUE(weekday)-Index oben wuerde beim zweiten Satz werfen und die
    # Migration mitten im Lauf abbrechen. Genau dieses Muster war der
    # Critical aus dem Abschluss-Review von Etappe 1 - und weil app.py
    # init_db() beim Modulimport aufruft, waere ein solcher Abbruch nicht nur
    # ein fehlgeschlagener Test, sondern ein Boot, der jeden Gunicorn-Worker
    # toetet. Deshalb erst nachschauen, welche Wochentage schon eine Zeile
    # haben, und nur die fehlenden ergaenzen.
    cursor.execute('SELECT weekday FROM business_hours')
    vorhandene_wochentage = {row['weekday'] for row in cursor.fetchall()}
    for wochentag in range(7):
        if wochentag not in vorhandene_wochentage:
            cursor.execute(
                'INSERT INTO business_hours (weekday, open_time, close_time, closed) '
                'VALUES (?, ?, ?, ?)',
                (wochentag, '00:00', '00:00', 0))


def down(cursor):
    """Nimmt alle drei Tabellen vollstaendig zurueck.

    Anders als bei 0004 und 0005, wo Spalten bewusst stehen blieben, weil sie
    auf dem jeweiligen Dialekt nicht (oder nicht sicher) entfernbar waren:
    hier entstehen alle drei Tabellen in dieser Migration neu, es gibt also
    keinen Bestandszustand, den eine vollstaendige Ruecknahme gefaehrden
    koennte. DROP TABLE IF EXISTS ist deshalb nicht nur moeglich, sondern die
    richtige, vollstaendige Ruecknahme - keine bewusste Lockerung wie dort,
    sondern der Normalfall fuer eine Migration ohne Bestandsschema.
    """
    cursor.execute('DROP INDEX IF EXISTS ix_coverage_requirements_weekday')
    cursor.execute('DROP TABLE IF EXISTS coverage_requirements')
    cursor.execute('DROP TABLE IF EXISTS business_hours_exceptions')
    cursor.execute('DROP TABLE IF EXISTS business_hours')
