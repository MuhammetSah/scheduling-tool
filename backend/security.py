"""Absicherung der HTTP-Schicht.

Zwei Dinge, die nichts mit Fachlogik zu tun haben und deshalb nicht in app.py
gehoeren: die Pflicht zu einem echten Signierschluessel und die Header, die
jede Antwort tragen soll.
"""

import os
from datetime import datetime, timedelta, timezone

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
