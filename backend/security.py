"""Absicherung der HTTP-Schicht.

Zwei Dinge, die nichts mit Fachlogik zu tun haben und deshalb nicht in app.py
gehoeren: die Pflicht zu einem echten Signierschluessel und die Header, die
jede Antwort tragen soll.
"""

import os

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
