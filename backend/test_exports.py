"""Exporte: iCal und CSV.

Reine Formatierungstests ohne Datenbank. Die interessanten Faelle sind die
beiden, an denen solche Exporte gern scheitern: der Zeilenumbruch im iCal und
die Excel-Eigenheiten der CSV. Beide fallen erst im Zielprogramm auf, und dort
ohne Fehlermeldung.
"""

from exports import CSV_HEADER_KEYS, schedule_to_csv, schedule_to_ical

STEMPEL = '20260823T120000Z'
WOCHENTAGE = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')
# Die Kopfzeile kommt seit der Zweisprachigkeit von aussen; hier steht die
# deutsche Fassung, wie sie i18n.py liefert.
KOPFZEILE = {
    'date': 'Datum', 'weekday': 'Wochentag', 'start': 'Beginn', 'end': 'Ende',
    'break': 'Pause (Min.)', 'working_hours': 'Arbeitszeit (Std.)',
    'shift_type': 'Schichtart', 'employee': 'Mitarbeiter',
}


def zuweisung(**abweichend):
    basis = {
        'id': 1,
        'date': '2026-09-01',
        'start_time': '08:00',
        'end_time': '16:00',
        'break_minutes': None,
        'effective_break_minutes': 30,
        'shift_type_name': 'Frühschicht',
        'employee_name': 'Anna',
        'working_hours': 7.5,
    }
    basis.update(abweichend)
    return basis


# ---------- iCal ----------


def test_der_rumpf_stimmt():
    text = schedule_to_ical([zuweisung()], 'Dienst', STEMPEL)

    assert text.startswith('BEGIN:VCALENDAR\r\n')
    assert text.rstrip().endswith('END:VCALENDAR')
    assert text.count('BEGIN:VEVENT') == 1
    assert text.count('END:VEVENT') == 1


def test_der_zeilenumbruch_ist_crlf():
    """RFC 5545 verlangt CRLF. Manche Kalender lehnen die Datei sonst wortlos
    ab - ohne Fehlermeldung, einfach ohne Termine."""
    text = schedule_to_ical([zuweisung()], 'Dienst', STEMPEL)

    assert '\r\n' in text
    # Kein einzelnes \n ohne vorangehendes \r.
    assert text.replace('\r\n', '') .count('\n') == 0


def test_zeiten_und_titel():
    text = schedule_to_ical([zuweisung()], 'Dienst', STEMPEL)

    assert 'DTSTART:20260901T080000' in text
    assert 'DTEND:20260901T160000' in text
    assert 'SUMMARY:Frühschicht' in text


def test_ein_termin_ueber_mitternacht_endet_am_folgetag():
    text = schedule_to_ical(
        [zuweisung(start_time='22:00', end_time='06:00')], 'Dienst', STEMPEL)

    assert 'DTSTART:20260901T220000' in text
    assert 'DTEND:20260902T060000' in text


def test_die_uid_ist_stabil():
    """Ein erneuter Import soll den Termin aktualisieren, nicht verdoppeln."""
    erst = schedule_to_ical([zuweisung()], 'Dienst', STEMPEL)
    erneut = schedule_to_ical([zuweisung()], 'Dienst', '20261231T235959Z')

    assert 'UID:assignment-1@schichtplan' in erst
    assert 'UID:assignment-1@schichtplan' in erneut


def test_sonderzeichen_im_namen_werden_maskiert():
    """Komma, Semikolon, Backslash und Zeilenumbruch nach RFC 5545 3.3.11.

    Ohne Maskierung zerteilt ein Komma im Schichtartnamen das Feld, und der
    Kalender liest den Rest als weiteren Parameter.
    """
    text = schedule_to_ical(
        [zuweisung(shift_type_name='Früh, spät; ganz\\quer')], 'Dienst', STEMPEL)

    assert r'SUMMARY:Früh\, spät\; ganz\\quer' in text


def test_ein_block_ohne_vorlage_bekommt_den_ersatznamen():
    text = schedule_to_ical([zuweisung(shift_type_name=None)], 'Dienst', STEMPEL)

    assert 'SUMMARY:Dienst' in text


def test_eine_abweichende_pause_steht_in_der_beschreibung():
    text = schedule_to_ical([zuweisung(break_minutes=60)], 'Dienst', STEMPEL)

    assert 'DESCRIPTION:Pause 60 Min.' in text


def test_auch_die_gesetzliche_pause_steht_in_der_beschreibung():
    """Der Kalender ist fuer die Belegschaft die einzige Stelle, an der der
    eigene Dienst auftaucht - 08:00-16:00 ohne ein Wort zur Pause heisst dort,
    dass es keine gibt."""
    text = schedule_to_ical([zuweisung(break_minutes=None)], 'Dienst', STEMPEL)

    assert 'DESCRIPTION:Pause 30 Min.' in text


def test_ohne_pause_steht_keine_beschreibung_drin():
    text = schedule_to_ical(
        [zuweisung(break_minutes=None, effective_break_minutes=0)], 'Dienst', STEMPEL)

    assert 'DESCRIPTION' not in text


def test_die_pausenzeile_laesst_sich_uebersetzen():
    text = schedule_to_ical(
        [zuweisung()], 'Shift', STEMPEL,
        break_note=lambda minuten: f'Break {minuten} min')

    assert 'DESCRIPTION:Break 30 min' in text


def test_der_kalendername_und_die_ersatzbeschriftung_sind_zwei_dinge():
    """Vorher stand beides in einer Angabe, und der abonnierte Dienstplan hiess
    im Telefon dann so wie ein Block ohne Vorlage."""
    text = schedule_to_ical(
        [zuweisung(shift_type_name=None)], 'Schichtplan September 2026', STEMPEL,
        free_block_label='Dienst')

    assert 'X-WR-CALNAME:Schichtplan September 2026' in text
    assert 'SUMMARY:Dienst' in text


def test_eine_zuweisung_ohne_zeiten_wird_uebersprungen():
    text = schedule_to_ical(
        [zuweisung(start_time=None, end_time=None)], 'Dienst', STEMPEL)

    assert 'BEGIN:VEVENT' not in text


# ---------- CSV ----------


def test_die_kopfzeile_steht_und_das_trennzeichen_ist_ein_semikolon():
    text = schedule_to_csv([zuweisung()], WOCHENTAGE, KOPFZEILE)

    zeilen = text.lstrip('﻿').split('\r\n')
    assert zeilen[0] == ';'.join(KOPFZEILE[key] for key in CSV_HEADER_KEYS)


def test_die_kopfzeile_folgt_der_sprache_der_anfrage():
    """Vorher deutsch, waehrend die Wochentage daneben uebersetzt waren."""
    englisch = {**KOPFZEILE, 'date': 'Date', 'weekday': 'Weekday',
                'employee': 'Employee'}
    text = schedule_to_csv([zuweisung()], ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'),
                           englisch)

    zeilen = text.lstrip('﻿').split('\r\n')
    assert zeilen[0].startswith('Date;Weekday;')
    assert zeilen[1].split(';')[1] == 'Tue'


def test_ein_bom_steht_davor():
    """Ohne BOM werden Umlaute in Excel zu Kauderwelsch."""
    assert schedule_to_csv([zuweisung()], WOCHENTAGE, KOPFZEILE).startswith('﻿')


def test_eine_zeile_je_zuweisung_mit_wochentag_und_nettozeit():
    text = schedule_to_csv([zuweisung()], WOCHENTAGE, KOPFZEILE)

    zeile = text.lstrip('﻿').split('\r\n')[1].split(';')
    assert zeile[0] == '2026-09-01'
    assert zeile[1] == 'Di'
    assert zeile[5] == '7.5'
    assert zeile[7] == 'Anna'


def test_die_pausenspalte_zeigt_die_geltende_pause():
    """Vorher leer, sobald niemand von Hand etwas eingetragen hatte - und die
    Spalte daneben zog die gesetzliche Pause trotzdem ab. In einer
    Abrechnungsunterlage muss die Zeile aufgehen."""
    zeile = schedule_to_csv([zuweisung()], WOCHENTAGE, KOPFZEILE
                            ).lstrip('﻿').split('\r\n')[1].split(';')

    assert zeile[4] == '30'


def test_eine_abweichende_pause_gewinnt_gegen_die_gesetzliche():
    zeile = schedule_to_csv([zuweisung(break_minutes=45)], WOCHENTAGE, KOPFZEILE
                            ).lstrip('﻿').split('\r\n')[1].split(';')

    assert zeile[4] == '45'


def test_ein_unbesetzter_platz_steht_mit_leerem_namen_drin():
    """Ihn wegzulassen hiesse, eine Luecke verschwinden zu machen."""
    text = schedule_to_csv([zuweisung(employee_name=None)], WOCHENTAGE, KOPFZEILE)

    zeile = text.lstrip('﻿').split('\r\n')[1].split(';')
    assert zeile[7] == ''
    assert zeile[0] == '2026-09-01'
