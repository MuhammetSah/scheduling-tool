"""Exporte: iCal und CSV.

Reine Formatierungstests ohne Datenbank. Die interessanten Faelle sind die
beiden, an denen solche Exporte gern scheitern: der Zeilenumbruch im iCal und
die Excel-Eigenheiten der CSV. Beide fallen erst im Zielprogramm auf, und dort
ohne Fehlermeldung.
"""

from exports import CSV_HEADERS, schedule_to_csv, schedule_to_ical

STEMPEL = '20260823T120000Z'
WOCHENTAGE = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')


def zuweisung(**abweichend):
    basis = {
        'id': 1,
        'date': '2026-09-01',
        'start_time': '08:00',
        'end_time': '16:00',
        'break_minutes': None,
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


def test_die_gesetzliche_pause_steht_nicht_drin():
    """Gegenprobe: auf jeder Zeile dieselbe Zahl hilft niemandem."""
    text = schedule_to_ical([zuweisung(break_minutes=None)], 'Dienst', STEMPEL)

    assert 'DESCRIPTION' not in text


def test_eine_zuweisung_ohne_zeiten_wird_uebersprungen():
    text = schedule_to_ical(
        [zuweisung(start_time=None, end_time=None)], 'Dienst', STEMPEL)

    assert 'BEGIN:VEVENT' not in text


# ---------- CSV ----------


def test_die_kopfzeile_steht_und_das_trennzeichen_ist_ein_semikolon():
    text = schedule_to_csv([zuweisung()], WOCHENTAGE)

    zeilen = text.lstrip('﻿').split('\r\n')
    assert zeilen[0] == ';'.join(CSV_HEADERS)


def test_ein_bom_steht_davor():
    """Ohne BOM werden Umlaute in Excel zu Kauderwelsch."""
    assert schedule_to_csv([zuweisung()], WOCHENTAGE).startswith('﻿')


def test_eine_zeile_je_zuweisung_mit_wochentag_und_nettozeit():
    text = schedule_to_csv([zuweisung()], WOCHENTAGE)

    zeile = text.lstrip('﻿').split('\r\n')[1].split(';')
    assert zeile[0] == '2026-09-01'
    assert zeile[1] == 'Di'
    assert zeile[5] == '7.5'
    assert zeile[7] == 'Anna'


def test_ein_unbesetzter_platz_steht_mit_leerem_namen_drin():
    """Ihn wegzulassen hiesse, eine Luecke verschwinden zu machen."""
    text = schedule_to_csv([zuweisung(employee_name=None)], WOCHENTAGE)

    zeile = text.lstrip('﻿').split('\r\n')[1].split(';')
    assert zeile[7] == ''
    assert zeile[0] == '2026-09-01'
