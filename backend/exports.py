"""Plaene als iCal und CSV.

Reine Formatierung ohne Datenbank und ohne Flask, wie coverage_model.py und
holidays.py: die Funktionen bekommen fertige Zuweisungszeilen und geben Text
zurueck.

Keine Bibliothek fuer beides. iCal ist ein Textformat (RFC 5545), und fuer
Termine mit Beginn, Ende und Titel sind es rund vierzig Zeilen; csv steht in
der Standardbibliothek. PDF und Excel braeuchten je eine Abhaengigkeit und
warten deshalb, bis jemand sie tatsaechlich verlangt - wer eine Tabelle will,
oeffnet die CSV.
"""

import csv
import io
from datetime import date, timedelta

# RFC 5545 verlangt CRLF. Ein haeufiger Fehler, und manche Kalender lehnen die
# Datei sonst wortlos ab - ohne Fehlermeldung, einfach ohne Termine.
CRLF = '\r\n'


def _escape(text):
    """Maskierung nach RFC 5545 Abschnitt 3.3.11.

    Backslash zuerst, sonst maskiert man die eigenen Maskierungen ein zweites
    Mal. Doppelpunkt und Anfuehrungszeichen brauchen es nicht - nur Backslash,
    Semikolon, Komma und Zeilenumbruch.
    """
    return (str(text)
            .replace('\\', '\\\\')
            .replace(';', '\\;')
            .replace(',', '\\,')
            .replace('\n', '\\n'))


def _stamp(day, hhmm):
    return f"{day.strftime('%Y%m%d')}T{hhmm.replace(':', '')}00"


def _event_times(iso_date, start_time, end_time):
    """(DTSTART, DTEND) eines Blocks, mit der Mitternachtsregel des Projekts.

    Ohne Zeitzone. Das Tool rechnet durchgaengig in Ortszeit und speichert
    keine Zone; eine erfundene waere eine Behauptung, die die Daten nicht
    tragen. Ein Kalender in einer anderen Zone verschiebt die Termine deshalb -
    das steht in der Spec und im README, statt es jemanden herausfinden zu
    lassen.
    """
    tag = date.fromisoformat(iso_date)
    ende_tag = tag if end_time > start_time else tag + timedelta(days=1)
    return _stamp(tag, start_time), _stamp(ende_tag, end_time)


def schedule_to_ical(assignments, calendar_name, now_stamp):
    """Ein VCALENDAR mit einem VEVENT je Zuweisung.

    `now_stamp` wird uebergeben statt hier erzeugt, damit die Ausgabe fuer
    einen gegebenen Plan reproduzierbar ist - ein Test, der die ganze Datei
    vergleicht, soll nicht an der Uhr scheitern.
    """
    zeilen = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Schichtplan-Tool//DE',
        'CALSCALE:GREGORIAN',
        f'X-WR-CALNAME:{_escape(calendar_name)}',
    ]

    for a in assignments:
        if not a.get('start_time') or not a.get('end_time'):
            continue
        beginn, ende = _event_times(a['date'], a['start_time'], a['end_time'])
        zeilen += [
            'BEGIN:VEVENT',
            # Stabil ueber Exporte hinweg: ein erneuter Import aktualisiert den
            # Termin, statt ihn ein zweites Mal anzulegen.
            f"UID:assignment-{a['id']}@schichtplan",
            f'DTSTAMP:{now_stamp}',
            f'DTSTART:{beginn}',
            f'DTEND:{ende}',
            f"SUMMARY:{_escape(a.get('shift_type_name') or calendar_name)}",
        ]
        # Nur die abweichende Pause. Die gesetzliche steht in jedem Block und
        # auf jeder Zeile dieselbe Zahl zu schreiben hilft niemandem.
        if a.get('break_minutes') is not None:
            beschreibung = f"Pause {a['break_minutes']} Min."
            zeilen.append(f'DESCRIPTION:{_escape(beschreibung)}')
        zeilen.append('END:VEVENT')

    zeilen.append('END:VCALENDAR')
    return CRLF.join(zeilen) + CRLF


CSV_HEADERS = ('Datum', 'Wochentag', 'Beginn', 'Ende', 'Pause (Min.)',
               'Arbeitszeit (Std.)', 'Schichtart', 'Mitarbeiter')


def schedule_to_csv(rows, weekday_labels):
    """Eine Zeile je Zuweisung, mit Kopfzeile.

    Semikolon als Trennzeichen und ein BOM davor - beides fuer Excel im
    deutschsprachigen Raum: ohne Semikolon landet alles in einer Spalte, ohne
    BOM werden Umlaute zu Kauderwelsch. Unschoen und richtig; eine CSV, die im
    Zielprogramm nicht aufgeht, ist kein Export.

    Unbesetzte Plaetze stehen mit leerem Mitarbeiterfeld drin. Sie
    wegzulassen hiesse, eine Luecke verschwinden zu machen.
    """
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=';', lineterminator=CRLF)
    schreiber.writerow(CSV_HEADERS)

    for row in rows:
        tag = date.fromisoformat(row['date'])
        schreiber.writerow([
            row['date'],
            weekday_labels[tag.weekday()],
            row.get('start_time') or '',
            row.get('end_time') or '',
            '' if row.get('break_minutes') is None else row['break_minutes'],
            row.get('working_hours', ''),
            row.get('shift_type_name') or '',
            row.get('employee_name') or '',
        ])

    return '﻿' + puffer.getvalue()
