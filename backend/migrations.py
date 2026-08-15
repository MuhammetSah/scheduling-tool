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


def _ensure_version_table(cursor):
    auto_id = _placeholders()['auto_id']
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS schema_migrations(
            id {auto_id},
            version TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _statements(path):
    """SQL-Anweisungen einer Datei.

    Bewusst simpel: Aufteilung am Semikolon. Migrationen dieses Projekts
    enthalten keine Semikolons in Zeichenketten oder Prozedurkoerpern. Falls
    das je noetig wird, gehoert die Migration in eine .py-Datei.
    """
    text = path.read_text(encoding='utf-8').format(**_placeholders())
    return [statement.strip() for statement in text.split(';') if statement.strip()]


def _python_module(path):
    spec = importlib.util.spec_from_file_location(f'migration_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def available_versions():
    """Alle Migrationen in Anwendungsreihenfolge."""
    versions = set()
    for path in MIGRATIONS_DIR.iterdir():
        if path.suffix not in ('.sql', '.py') or path.name.startswith('__'):
            continue
        stem = path.stem.removesuffix('.down')
        if _VERSION_PATTERN.match(stem):
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

    Jede Migration bekommt ihre eigene Transaktion: schlaegt die dritte fehl,
    bleiben die ersten beiden angewandt und protokolliert, statt dass alles
    in einem unklaren Zwischenzustand endet.
    """
    connection = get_db_connection()
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
            try:
                _run(cursor, version, 'up')
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
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        _ensure_version_table(cursor)
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version DESC')
        rows = cursor.fetchall()
        if not rows:
            return None

        version = rows[0]['version']
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
