"""Die beiden ArbZG-Regeln, die das Tool bislang der Personalabteilung ueberliess.

1. **Paragraph 4 Satz 3** - "Laenger als sechs Stunden hintereinander duerfen
   Arbeitnehmer nicht ohne Ruhepause beschaeftigt werden." Das Tool kannte
   bisher nur die DAUER der Pause, nicht ihre LAGE, und konnte den Satz
   deshalb gar nicht pruefen. Paragraph 4 Satz 1 verlangt ohnehin "im voraus
   feststehende Ruhepausen" - eine Dauer ohne Uhrzeit steht nicht fest.

2. **Paragraph 9 / Paragraph 10** - Sonn- und Feiertagsarbeit ist verboten,
   ausser der Betrieb faellt unter eine der Ausnahmen. Auf welcher Seite er
   steht, kann nur der Betreiber sagen. Bisher warnte das Tool bei Feiertagen
   immer und bei Sonntagen nie.

Was die Ausnahme NICHT abschaltet: die fuenfzehn freien Sonntage aus
Paragraph 11 Abs. 1 und den Ersatzruhetag aus Paragraph 11 Abs. 3. Beide sind
das Gegengewicht zu Paragraph 10 und gelten gerade dann, wenn er greift.
"""


def _platz(hr_client, datum, start='08:00', ende='16:00', jahr=2026, monat=10):
    """Ein Block mit eigenen Zeiten an diesem Datum.

    Die Schichtart wird nur angelegt, damit /schedules/generate ueberhaupt
    einen Plan erzeugt - der Block traegt seine Zeiten selbst.
    """
    hr_client.post('/shift-types', json={
        'name': 'Tag', 'start_time': '08:00', 'end_time': '16:00'})
    hr_client.post('/schedules/generate', json={'year': jahr, 'month': monat})
    antwort = hr_client.post('/schedules/%d/%d/slots' % (jahr, monat), json={
        'date': datum, 'start_time': start, 'end_time': ende})
    assert antwort.status_code in (200, 201), antwort.json
    return {'id': antwort.json['id'], 'start_time': start, 'end_time': ende}


def _setze(hr_client, platz, **felder):
    """Eine Zuweisung aendern, mit ihren Zeiten.

    PUT /assignments/<id> loescht ausgelassene Felder (siehe der Kommentar an
    der Route) - wer nur den Mitarbeiter setzt, verliert die Zeiten des Blocks,
    und ein Block ohne Vorlage hat dann gar keine mehr.
    """
    rumpf = {'start_time': platz['start_time'], 'end_time': platz['end_time']}
    rumpf.update(felder)
    return hr_client.put('/assignments/%d' % platz['id'], json=rumpf)


def _anna(hr_client, **abweichend):
    daten = {'name': 'Anna', 'email': 'anna@example.com'}
    daten.update(abweichend)
    return hr_client.post('/employees', json=daten).json


# ---------- Paragraph 4 Satz 3: die Lage der Pause ----------


def test_eine_pause_ganz_am_anfang_laesst_zu_lange_am_stueck(hr_client):
    """Der Kern.

    08:00 bis 16:00 mit einer halben Stunde Pause ab 08:00: danach folgen
    siebeneinhalb Stunden ohne Unterbrechung. Die Dauer stimmt, die Lage
    nicht - und genau das konnte das Tool bisher nicht sehen.
    """
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='08:00')

    assert antwort.status_code == 200, antwort.json
    assert any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_eine_pause_ganz_am_ende_ebenso(hr_client):
    """Beide Richtungen: davor sind es dann siebeneinhalb Stunden."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='15:30')

    assert any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_eine_pause_in_der_mitte_ist_in_ordnung(hr_client):
    """Gegenprobe, und die wichtigste: ohne sie waere eine Umsetzung, die
    jede Pausenlage bemaengelt, ebenfalls gruen."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='12:00')

    assert not any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_genau_sechs_stunden_am_stueck_sind_erlaubt(hr_client):
    """Die Grenze selbst: "laenger als sechs Stunden" heisst, sechs gehen.

    08:00 bis 16:00, Pause ab 14:00: davor genau sechs Stunden, danach
    eineinhalb.
    """
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='14:00')

    assert not any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_ein_kurzer_block_braucht_keine_pause(hr_client):
    """Gegenprobe: unter sechs Stunden verlangt Paragraph 4 gar keine, und
    ohne Pause gibt es auch keine Lage zu bemaengeln."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05', '08:00', '13:00')

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert not any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_ohne_angegebene_lage_wird_nichts_bemaengelt(hr_client):
    """Gegenprobe zur Zurueckhaltung.

    Bei jedem Block, den dieses Tool bauen kann - hoechstens zehn Stunden,
    mindestens dreissig Minuten Pause -, gibt es immer eine zulaessige Lage.
    Eine fehlende Angabe ist deshalb nie ein bekannter Verstoss, und wer sie
    trotzdem bemaengelt, warnt bei jedem einzelnen Block.
    """
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30)

    assert not any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_eine_pause_ausserhalb_des_blocks_wird_abgelehnt(hr_client):
    """Eine Pause um 20:00 in einer Schicht bis 16:00 ist keine Lage,
    sondern ein Tippfehler."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='20:00')

    assert antwort.status_code == 400, antwort.json


def test_eine_lage_ohne_dauer_wird_abgelehnt(hr_client):
    """Eine Uhrzeit ohne Dauer beschreibt keine Pause."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_start='12:00')

    assert antwort.status_code == 400, antwort.json


def test_die_lage_bleibt_gespeichert(hr_client):
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')

    _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='12:00')

    plan = hr_client.get('/schedules/2026/10').json
    zeile = [z for z in plan['assignments'] if z['id'] == platz['id']][0]
    assert zeile['break_start'] == '12:00'


def test_die_lage_gilt_auch_ueber_mitternacht(hr_client):
    """Eine Nachtschicht 22:00 bis 06:00 mit Pause um 02:00 ist mittig.

    Ohne die Mitternachtsrechnung laege 02:00 scheinbar vor dem Beginn und
    faelle aus dem Block - dieselbe Konvention wie ueberall sonst.
    """
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05', '22:00', '06:00')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='02:00')

    assert antwort.status_code == 200, antwort.json
    assert not any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


def test_eine_schlechte_lage_in_der_nachtschicht_wird_gemeldet(hr_client):
    """Gegenprobe zur Mitternachtsrechnung: dieselbe Schicht, Pause um 22:15,
    danach knapp acht Stunden am Stueck."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05', '22:00', '06:00')

    antwort = _setze(hr_client, platz, employee_id=anna['id'], break_minutes=30, break_start='22:15')

    assert any('Satz 3' in w for w in antwort.json['warnings']), antwort.json


# ---------- Paragraph 9 / Paragraph 10: faellt der Betrieb unter die Ausnahme ----------


def test_ohne_ausnahme_wird_sonntagsarbeit_gemeldet(hr_client):
    """Paragraph 9 Abs. 1 verbietet sie. Bisher sagte das Tool dazu nichts -
    es zaehlte nur das Jahresbudget aus Paragraph 11 Abs. 1."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-04')   # ein Sonntag

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert any('§ 9' in w for w in antwort.json['warnings']), antwort.json


def test_mit_ausnahme_schweigt_die_sonntagsmeldung(hr_client):
    """Ein Betrieb nach Paragraph 10 - Gaststaette, Klinik, Verkehr - darf am
    Sonntag arbeiten lassen. Ihn bei jedem Sonntag zu warnen erzieht dazu,
    Warnungen zu ueberlesen."""
    hr_client.put('/settings', json={'sunday_work_permitted': 'yes'})
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-04')

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert not any('§ 9' in w for w in antwort.json['warnings']), antwort.json


def test_die_ausnahme_schaltet_das_sonntagsbudget_nicht_ab(hr_client):
    """Der Punkt, den man uebersieht.

    Paragraph 11 Abs. 1 - fuenfzehn freie Sonntage - ist das Gegengewicht zu
    Paragraph 10 und gilt gerade dann, wenn er greift. Eine Ausnahme, die
    beides abschaltet, macht aus einer Erlaubnis eine Freistellung.
    """
    from app import get_db

    hr_client.put('/settings', json={'sunday_work_permitted': 'yes'})
    anna = _anna(hr_client)

    # Achtunddreissig Sonntage im Jahr bereits gearbeitet: bei 52 bleiben 14
    # frei, also einer zu wenig.
    with hr_client.application.app_context():
        connection = get_db()
        cursor = connection.cursor()
        cursor.execute("INSERT INTO schedules (year, month, status) VALUES (2026, 1, 'published')")
        schedule_id = cursor.lastrowid
        from datetime import date, timedelta
        tag = date(2026, 1, 4)
        gesetzt = 0
        while gesetzt < 38:
            if tag.weekday() == 6 and tag.month != 10:
                cursor.execute(
                    'INSERT INTO shift_assignments (schedule_id, date, shift_type_id, slot_index, '
                    "employee_id, start_time, end_time) VALUES (?, ?, NULL, ?, ?, '08:00', '16:00')",
                    (schedule_id, tag.isoformat(), gesetzt, anna['id']))
                gesetzt += 1
            tag += timedelta(days=7 if tag.weekday() == 6 else 1)
        connection.commit()

    platz = _platz(hr_client, '2026-10-04')
    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert any('Sonntag' in w and 'frei' in w for w in antwort.json['warnings']), antwort.json


def test_mit_ausnahme_schweigt_auch_die_feiertagsmeldung(hr_client):
    hr_client.put('/settings', json={'holiday_region': 'BY',
                                     'sunday_work_permitted': 'yes'})
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-03')   # Tag der Deutschen Einheit

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert not any('Feiertag' in w for w in antwort.json['warnings']), antwort.json


def test_ohne_ausnahme_meldet_der_feiertag_weiterhin(hr_client):
    """Gegenprobe: die Vorgabe bleibt "nicht ausgenommen"."""
    hr_client.put('/settings', json={'holiday_region': 'BY'})
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-03')

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert any('Feiertag' in w for w in antwort.json['warnings']), antwort.json


def test_ein_werktag_bleibt_von_beidem_unberuehrt(hr_client):
    """Gegenprobe: eine Umsetzung, die immer meldet, waere sonst gruen."""
    anna = _anna(hr_client)
    platz = _platz(hr_client, '2026-10-05')   # ein Montag

    antwort = _setze(hr_client, platz, employee_id=anna['id'])

    assert not any('§ 9' in w or 'Feiertag' in w
                   for w in antwort.json['warnings']), antwort.json
