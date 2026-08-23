"""Absicherung der HTTP-Schicht.

Zwei Dinge, die nichts mit Fachlogik zu tun haben und deshalb nicht in app.py
gehoeren: die Pflicht zu einem echten Signierschluessel und die Header, die
jede Antwort tragen soll.
"""

import contextlib
import os
import zlib
from datetime import datetime, timedelta, timezone

from db import use_postgres

# Nur fuer lokale Entwicklung. Der Wert steht im oeffentlichen Quelltext und
# ist damit kein Geheimnis - in Produktion wird er deshalb verweigert.
DEV_SECRET_KEY = 'schichtplan-local-dev'

SECURITY_HEADERS = {
    # Verhindert, dass ein Browser den Inhaltstyp einer Antwort errät.
    'X-Content-Type-Options': 'nosniff',
    # Diese API gehoert in keinen fremden Rahmen.
    'X-Frame-Options': 'DENY',
    # Keine Pfade oder Query-Parameter an fremde Seiten weitergeben.
    'Referrer-Policy': 'no-referrer',
    'Cross-Origin-Opener-Policy': 'same-origin',
}


def is_production():
    return os.environ.get('FLASK_ENV') == 'production'


def resolve_secret_key():
    """Der Schluessel fuer Sitzungscookie und Bearer-Token.

    Faellt lokal auf einen festen Entwicklungswert zurueck, verweigert in
    Produktion aber den Start: mit einem bekannten Schluessel kann jeder
    gueltige Anmeldetoken erzeugen, und ein stiller Fallback ist genau die
    Art Fehler, die niemandem auffaellt.
    """
    secret = os.environ.get('SECRET_KEY')
    if secret:
        return secret
    if is_production():
        raise RuntimeError(
            'SECRET_KEY muss in der Produktionsumgebung gesetzt sein. Er signiert '
            'Sitzungscookie und Bearer-Token; der Entwicklungswert steht im Quelltext.'
        )
    return DEV_SECRET_KEY


def register_security_headers(app):
    """Haengt die Header an jede Antwort.

    Keine Content-Security-Policy: diese Anwendung liefert ausschliesslich
    JSON aus. Die CSP gehoert vor das Frontend (Vercel), nicht hierher.
    """
    @app.after_request
    def _add_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if is_production():
            response.headers.setdefault(
                'Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response


# Zehn Versuche in einer Viertelstunde: hoch genug, dass ein vertippter Mensch
# nie dagegen laeuft, niedrig genug, dass Raten unbrauchbar langsam wird.
MAX_FAILED_ATTEMPTS = 10
ATTEMPT_WINDOW_MINUTES = 15


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _window_start_iso():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=ATTEMPT_WINDOW_MINUTES)
    return cutoff.isoformat(timespec='seconds')


# Zwei Zahlen statt einer: Postgres verwaltet Advisory-Locks mit einem
# bigint ODER mit zwei int-Werten in getrennten Raeumen. Der Migrations-Runner
# benutzt die Einzahl-Form (siehe _migration_lock() in migrations.py); die
# Zweizahl-Form hier kann mit ihm deshalb gar nicht kollidieren, statt sich nur
# darauf zu verlassen, dass zwei crc32-Werte verschieden ausfallen.
_ATTEMPT_LOCK_CLASS = zlib.crc32(b'scheduling-tool-main:login-attempts') % (2 ** 31)


def _attempt_lock_key(identifier):
    """Ein stabiler int32 je Benutzername.

    crc32 und nicht ein kryptografischer Hash: der Wert schuetzt nichts, er
    sortiert nur Wartende in dieselbe Schlange. Zwei Benutzernamen mit
    demselben Wert warten gelegentlich unnoetig aufeinander - ein paar
    Millisekunden auf einem Pfad, der ohnehin ein Passwort prueft.
    """
    return zlib.crc32(identifier.encode('utf-8')) % (2 ** 31)


@contextlib.contextmanager
def attempt_guard(cursor, identifier):
    """Serialisiert Pruefen und Zaehlen eines Anmeldeversuchs je Benutzername.

    is_locked_out() liest einen Zaehler, den record_attempt() gleich darauf
    erhoeht - klassisches check-then-act. Ohne Serialisierung lesen N
    gleichzeitige Anfragen alle denselben Stand unterhalb der Grenze und
    kommen alle durch: aus zehn erlaubten Versuchen je Viertelstunde werden
    zehn mal so viele, wie der Angreifer Verbindungen aufmacht. Die Drosselung
    ist dann keine Grenze mehr, sondern eine Empfehlung.

    Nur auf Postgres aktiv, und zwar bewusst asymmetrisch - dieselbe
    Abwaegung wie bei _migration_lock() in migrations.py: SQLite kommt in
    diesem Projekt nur lokal und nur als einzelner Prozess vor (siehe der
    Kommentar bei DB_PATH in db.py). Ein Lock ohne erreichbare Race waere dort
    zusaetzlicher, ungetesteter Code auf dem Pfad, den jeder Entwickler
    taeglich benutzt.

    Sitzungsgebunden (pg_advisory_lock) statt transaktionsgebunden
    (pg_advisory_xact_lock): der Sperrpfad in login() antwortet mit 429, ohne
    zu committen, und ein xact-Lock haenge dann bis zum teardown der
    Anfrage. Die Freigabe steht hier im finally und ist damit unabhaengig
    davon, ob und wann der Aufrufer committet.
    """
    if not (use_postgres() and identifier):
        yield
        return
    schluessel = (_ATTEMPT_LOCK_CLASS, _attempt_lock_key(identifier))
    cursor.execute('SELECT pg_advisory_lock(?, ?)', schluessel)
    try:
        yield
    finally:
        cursor.execute('SELECT pg_advisory_unlock(?, ?)', schluessel)


def is_locked_out(cursor, identifier):
    """Sind fuer diesen Benutzernamen zu viele Fehlversuche im Zeitfenster?

    Die Sperre gilt pro Benutzername, nicht pro IP: eine IP-Sperre trifft bei
    einem Buero hinter einem gemeinsamen Anschluss alle Kolleginnen und
    Kollegen mit, und ein Angreifer mit wechselnden Adressen umgeht sie
    ohnehin. Sie blockiert waehrend der Sperre auch das richtige Passwort -
    sonst waere sie als Bremse wirkungslos.
    """
    cursor.execute(
        'SELECT COUNT(*) AS n FROM login_attempts '
        'WHERE identifier = ? AND succeeded = 0 AND attempted_at >= ?',
        (identifier, _window_start_iso()),
    )
    return cursor.fetchone()['n'] >= MAX_FAILED_ATTEMPTS


def record_attempt(cursor, identifier, ip, succeeded):
    """Protokolliert einen Versuch. Ein Erfolg loescht die Fehlversuche davor."""
    if succeeded:
        cursor.execute('DELETE FROM login_attempts WHERE identifier = ?', (identifier,))
    cursor.execute(
        'INSERT INTO login_attempts (identifier, ip, succeeded, attempted_at) VALUES (?, ?, ?, ?)',
        (identifier, ip or 'unbekannt', 1 if succeeded else 0, _now_iso()),
    )
    # Gelegenheitsaufraeumen: alles ausserhalb des Zeitfensters ist wertlos.
    cursor.execute('DELETE FROM login_attempts WHERE attempted_at < ?', (_window_start_iso(),))
