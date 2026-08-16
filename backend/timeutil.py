"""Lokales Datum und Monatsgrenzen.

Warum ueberhaupt: "der aktuelle Monat" entscheidet, ob ein Mitarbeiterkonto
eine Krankmeldung eintragen darf. date.today() liefert das Datum der
Serverzeitzone - auf einem Hoster ist das UTC. Am Monatsersten zwischen 00:00
und 02:00 deutscher Zeit haelt der Server dann noch den Vormonat fuer aktuell
und weist die Meldung ab.
"""

import calendar
import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = 'Europe/Berlin'


def _configured_zone():
    """Die konfigurierte Zeitzone als ZoneInfo, oder Berlin falls sie unbekannt ist.

    Ein Tippfehler in der Umgebungsvariablen soll den Start nicht verhindern -
    eine falsche Zone ist ein Schoenheitsfehler, eine nicht startende
    Anwendung ist ein Ausfall. ZoneInfo(...) wird hier genau einmal, geschuetzt,
    aufgeloest; timezone_name() und today_local() nutzen beide dieses Ergebnis,
    statt die Zone ein zweites Mal ungeschuetzt aufzuloesen.
    """
    name = os.environ.get('APP_TIMEZONE', DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def timezone_name():
    """Der konfigurierte Zonenname, oder Berlin falls er unbekannt ist."""
    return _configured_zone().key


def today_local():
    """Das Datum, das gerade am Betriebsstandort gilt."""
    return datetime.now(_configured_zone()).date()


def month_bounds(day):
    """Erster und letzter Tag des Monats, in dem `day` liegt, als ISO-Strings."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1).isoformat(), day.replace(day=last_day).isoformat()
