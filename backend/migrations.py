"""Versionierte Schemaaenderungen.

Warum kein Alembic: dieses Projekt spricht die Datenbank direkt ueber sqlite3
bzw. psycopg2 an und uebersetzt den Dialekt selbst (db.py). Alembic erwartet
eine SQLAlchemy-Engine und wuerde gegen diese Schicht arbeiten; ohne
ORM-Modelle bliebe von Alembic ohnehin kaum mehr als eine Versionstabelle
plus op.execute. Der Runner hier nutzt die vorhandene Schicht und kommt ohne
neue Abhaengigkeit aus - dieselbe Ueberlegung wie bei i18n.py gegenueber
Flask-Babel.

Eine Migration ist entweder
  NNNN_name.sql       - Anweisungen, durch Semikolon getrennt
  NNNN_name.down.sql  - optionale Ruecknahme dazu
oder
  NNNN_name.py        - mit up(cursor) und down(cursor)

SQL-Dateien duerfen den Platzhalter {auto_id} verwenden; er wird je nach
Datenbank durch SERIAL PRIMARY KEY oder INTEGER PRIMARY KEY AUTOINCREMENT
ersetzt.

Zwei Faellen der Dialektschicht in db.py, die beim Schreiben einer
.sql-Migration leicht uebersehen werden:
  - _PostgresCursor.execute() interpoliert mit %, auch ohne uebergebene
    Parameter - ein woertliches % in einer .sql-Migration (z.B. in einem
    LIKE-Muster) schlaegt auf Postgres fehl.
  - Jedes blanke INSERT ohne eigenes RETURNING bekommt automatisch
    RETURNING id angehaengt; das schlaegt fehl, wenn die Zieltabelle keine
    Spalte id hat.

Das Aufteilen in _statements() kennt keine Kommentare oder Zeichenketten: ein
woertliches ; in einem -- Kommentar trennt die Datei genauso wie jedes andere.
Fragmente, die nach Entfernen der -- Kommentare nur noch aus Leerraum
bestehen, werden stillschweigend uebersprungen statt an cursor.execute()
uebergeben - alles andere (Bloeckkommentare /* */, ; in Zeichenketten) bleibt
unabsichtlich falsch aufgeteilt; siehe _statements().
"""

import importlib.util
import re
from pathlib import Path

from db import get_db_connection, use_postgres

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'

_VERSION_PATTERN = re.compile(r'^(\d{4}_[a-z0-9_]+)$')


def _placeholders():
    return {
        'auto_id': 'SERIAL PRIMARY KEY' if use_postgres() else 'INTEGER PRIMARY KEY AUTOINCREMENT',
    }


def _connection():
    """Oeffnet eine Verbindung mit echter Transaktionskontrolle je Migration.

    db.get_db_connection() liefert unter SQLite eine Verbindung mit
    isolation_level='' (SQLite-Default): Python haengt ein implizites BEGIN
    nur vor DML an (INSERT/UPDATE/DELETE), nicht vor DDL - CREATE TABLE und
    ALTER TABLE committen dort sofort fuer sich allein. Ein
    connection.rollback() nach einer fehlgeschlagenen Migration haette dann
    nichts mehr zum Zuruecknehmen. isolation_level=None schaltet auf
    Autocommit pro Anweisung um; zusammen mit einem expliziten BEGIN vor
    jeder Migration (siehe _begin()) stehen DDL und DML dann unter derselben
    Transaktion. Auf Postgres ist DDL ueber psycopg2 bereits transaktional -
    dort bleibt die Verbindung unveraendert.
    """
    connection = get_db_connection()
    if not use_postgres():
        connection.isolation_level = None
    return connection


def _begin(cursor):
    """Startet die Transaktion einer einzelnen Migration (siehe _connection())."""
    if not use_postgres():
        cursor.execute('BEGIN')


def _ensure_version_table(cursor):
    auto_id = _placeholders()['auto_id']
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schema_migrations(
            id {auto_id},
            version TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _has_sql(fragment):
    """True, wenn nach Entfernen der -- Kommentare noch Code uebrig bleibt.

    Nur zur Erkennung leerer Fragmente gedacht (siehe _statements()) - kein
    SQL-Parser: Bloeckkommentare (/* */) und ; in Zeichenketten bleiben
    absichtlich unbehandelt, siehe Modul-Docstring.
    """
    ohne_kommentare = re.sub(r'--[^\n]*', '', fragment)
    return bool(ohne_kommentare.strip())


def _statements(path):
    """SQL-Anweisungen einer Datei.

    Bewusst simpel: Aufteilung am Semikolon. Migrationen dieses Projekts
    enthalten keine Semikolons in Zeichenketten oder Prozedurkoerpern. Falls
    das je noetig wird, gehoert die Migration in eine .py-Datei. Ein
    woertliches ; innerhalb eines -- Kommentars trennt die Datei genauso wie
    jedes andere - das dabei entstehende Fragment enthaelt dann nur noch
    Kommentartext und wird uebersprungen statt an cursor.execute() zu gehen
    (siehe _has_sql()): ein leeres Fragment an die Datenbank zu schicken waere
    schlicht sinnlos, unabhaengig vom Dialekt.

    {auto_id} wird gezielt ersetzt statt ueber str.format() auf die ganze
    Datei - ein Migrationstext mit einer woertlichen { oder } (Postgres-Array-
    Default, JSON-Literal, CHECK mit Wiederholungsquantor) wuerde format()
    sonst mit KeyError/ValueError zum Absturz bringen.
    """
    text = path.read_text(encoding='utf-8').replace('{auto_id}', _placeholders()['auto_id'])
    return [statement.strip() for statement in text.split(';')
            if statement.strip() and _has_sql(statement)]


def _python_module(path):
    spec = importlib.util.spec_from_file_location(f'migration_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def available_versions():
    """Alle Migrationen in Anwendungsreihenfolge.

    Eine Datei mit .sql/.py-Endung, die nicht dem Namensschema entspricht,
    wird nicht stillschweigend uebersprungen: eine so benannte Migration
    (Tippfehler in der Nummer, falscher Trenner) wuerde sonst committet,
    reviewt, deployt und nie ausgefuehrt - genau die stille Schemadrift,
    die dieser Runner verhindern soll.
    """
    versions = set()
    for path in MIGRATIONS_DIR.iterdir():
        if path.suffix not in ('.sql', '.py') or path.name.startswith('__'):
            continue
        stem = path.stem.removesuffix('.down')
        if not _VERSION_PATTERN.match(stem):
            raise ValueError(f'Migrationsdatei entspricht nicht dem Namensschema NNNN_name: {path.name}')
        versions.add(stem)
    return sorted(versions)


def _run(cursor, version, direction):
    """Wendet eine Migration in eine Richtung an. direction: 'up' oder 'down'."""
    python_path = MIGRATIONS_DIR / f'{version}.py'
    if python_path.exists():
        getattr(_python_module(python_path), direction)(cursor)
        return True

    suffix = '.sql' if direction == 'up' else '.down.sql'
    sql_path = MIGRATIONS_DIR / f'{version}{suffix}'
    if not sql_path.exists():
        return False
    for statement in _statements(sql_path):
        cursor.execute(statement)
    return True


def applied_versions():
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        connection.commit()
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version')
        return [row['version'] for row in cursor.fetchall()]
    finally:
        connection.close()


def apply_pending():
    """Wendet alle noch nicht angewandten Migrationen an, aelteste zuerst.

    Jede Migration bekommt ihre eigene Transaktion (siehe _connection() und
    _begin()): schlaegt die dritte fehl, bleiben die ersten beiden angewandt
    und protokolliert, und von der dritten selbst bleibt nichts zurueck -
    statt dass alles in einem unklaren Zwischenzustand endet.
    """
    connection = _connection()
    newly_applied = []
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        connection.commit()

        cursor.execute('SELECT version FROM schema_migrations')
        already = {row['version'] for row in cursor.fetchall()}

        for version in available_versions():
            if version in already:
                continue
            _begin(cursor)
            try:
                if not _run(cursor, version, 'up'):
                    # available_versions() findet eine Version auch anhand
                    # einer .down.sql ohne zugehoeriges Up-Skript. Ohne diese
                    # Pruefung wuerde eine solche Datei unten als
                    # "angewandt" protokolliert, obwohl nie etwas lief - und
                    # jeder spaetere Lauf wuerde sie fuer immer ueberspringen.
                    raise RuntimeError(f'Migration {version} hat kein Up-Skript')
                cursor.execute('INSERT INTO schema_migrations (version) VALUES (?)', (version,))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            newly_applied.append(version)
        return newly_applied
    finally:
        connection.close()


def rollback_last():
    """Nimmt die zuletzt angewandte Migration zurueck. Gibt deren Namen zurueck."""
    connection = _connection()
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version DESC')
        rows = cursor.fetchall()
        if not rows:
            return None

        version = rows[0]['version']
        _begin(cursor)
        try:
            if not _run(cursor, version, 'down'):
                raise RuntimeError(f'Migration {version} hat keine Ruecknahme')
            cursor.execute('DELETE FROM schema_migrations WHERE version = ?', (version,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return version
    finally:
        connection.close()


if __name__ == '__main__':
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else 'up'
    if command == 'up':
        applied = apply_pending()
        print('Angewandt:', ', '.join(applied) if applied else 'nichts offen')
    elif command == 'down':
        print('Zurueckgerollt:', rollback_last() or 'nichts angewandt')
    elif command == 'status':
        applied = set(applied_versions())
        for version in available_versions():
            print(('[x] ' if version in applied else '[ ] ') + version)
    else:
        print('Verwendung: python migrations.py [up|down|status]')
        sys.exit(1)
