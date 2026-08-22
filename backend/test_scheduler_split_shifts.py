"""Geteilter Dienst im Suchkern: mehrere Bloecke am selben Tag.

Bis Etappe 4 bekam jede Person hoechstens einen Block pro Tag. Der geteilte
Dienst - Spec Paragraph 4.4 nennt ihn ausdruecklich als Beispiel fuer
Arbeitszeitfenster - war damit nicht plan bar.

Was das Arbeitszeitgesetz dazu verlangt und was hier deshalb geprueft wird:

  Paragraph 2 Abs. 1  Arbeitszeit ist die Zeit vom Beginn bis zum Ende der
                      Arbeit OHNE die Ruhepausen. Bei einem geteilten Dienst
                      zaehlt die Unterbrechung nicht mit - die Tagesarbeitszeit
                      ist die Summe der Blockdauern, nicht die Spanne vom
                      ersten Beginn bis zum letzten Ende.
  Paragraph 3         Acht Stunden werktaeglich, auf zehn verlaengerbar nur bei
                      Ausgleich im Schnitt ueber sechs Kalendermonate. Den
                      Ausgleich prueft das Tool nicht (monatsweise Planung);
                      die harte Obergrenze steht in max_daily_hours.
  Paragraph 5 Abs. 1  Elf Stunden ununterbrochene Ruhezeit NACH BEENDIGUNG DER
                      TAEGLICHEN ARBEITSZEIT. Die Unterbrechung am selben Tag
                      ist keine Ruhezeit; gemessen wird vom Ende des letzten
                      Blocks eines Tages bis zum Beginn des ersten am naechsten.

Zu jeder dieser Regeln steht hier eine Gegenprobe, weil die jeweils falsche
Lesart sonst genauso gruen waere: die Spanne statt der Summe zu rechnen, oder
die Ruhezeit zwischen den Bloecken eines Tages zu pruefen.
"""

from scheduler import CHRONOLOGICAL, generate_schedule


def person(employee_id, **abweichend):
    basis = {
        'id': employee_id,
        'max_shifts_per_month': None,
        'unavailable_weekdays': set(),
        'unavailable_dates': set(),
        'allowed_shift_types': None,
        'weekly_hours': None,
        'min_rest_hours': 11,
        'max_daily_hours': 10,
        'availability_mode': 'anytime',
        'availability': [],
    }
    basis.update(abweichend)
    return basis


def block(iso_date, start_time, end_time, slot_index=0, shift_type_id=None):
    """Ein fertiger Block, wie block_planner.build_month_blocks() ihn liefert."""
    from datetime import date, timedelta

    tag = date.fromisoformat(iso_date)
    weekday = tag.weekday()
    dauer = ((int(end_time[:2]) * 60 + int(end_time[3:]))
             - (int(start_time[:2]) * 60 + int(start_time[3:])))
    if dauer <= 0:
        dauer += 24 * 60
    return {
        'date': iso_date,
        'weekday': weekday,
        'week_start': (tag - timedelta(days=weekday)).isoformat(),
        'shift_type_id': shift_type_id,
        'slot_index': slot_index,
        'is_weekend': weekday >= 5,
        'start_time': start_time,
        'end_time': end_time,
        'duration_minutes': dauer,
    }


def plan(bloecke, leute):
    return generate_schedule(2026, 9, leute, [], ordering=CHRONOLOGICAL, slots=bloecke)


def test_geteilter_dienst_geht_an_dieselbe_person():
    """Zwei ueberschneidungsfreie Bloecke an einem Tag, eine Person: beide."""
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 0
    assert {z['employee_id'] for z in ergebnis['assignments']} == {1}


def test_ueberschneidende_bloecke_gehen_nicht_an_dieselbe_person():
    """Niemand kann an zwei Orten zugleich sein - das bleibt hart."""
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '11:00', '15:00', 1)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_aneinandergrenzende_bloecke_ueberschneiden_sich_nicht():
    """Halboffene Grenze: 12:00 als Ende und als Beginn ist keine Ueberschneidung.

    Dieselbe Konvention wie ueberall sonst im Projekt (siehe
    coverage_model.bands_overlap).
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '12:00', '16:00', 1)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_tagesgrenze_bindet_ueber_die_summe_der_bloecke():
    """Paragraph 2 Abs. 1 ArbZG: gezaehlt wird die Arbeitszeit.

    Vier plus vier Stunden sind acht - mehr als die Grenze von sieben. Der
    zweite Block bleibt offen.
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1)],
        [person(1, max_daily_hours=7)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_die_spanne_allein_sprengt_die_tagesgrenze_nicht():
    """Die Gegenprobe zum Test darueber, und der eigentliche Punkt.

    Dieselben zwei Bloecke, Grenze acht Stunden. Von 08:00 bis 20:00 sind es
    zwoelf Stunden Spanne, aber nur acht Stunden Arbeitszeit - die
    Unterbrechung zaehlt nach Paragraph 2 Abs. 1 ArbZG nicht mit. Wer die
    Spanne rechnet, laesst hier faelschlich einen Block offen.
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1)],
        [person(1, max_daily_hours=8)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_ruhezeit_misst_ab_dem_ende_des_letzten_blocks():
    """Paragraph 5 Abs. 1 ArbZG: elf Stunden nach Beendigung der taeglichen Arbeitszeit.

    Der geteilte Dienst endet um 20:00, der naechste Morgen begaenne um 06:00 -
    das sind zehn Stunden. Einer der drei Bloecke muss offen bleiben.

    Diskriminierend, weil die falsche Lesart (Ruhezeit ab dem Ende des ERSTEN
    Blocks, 12:00) achtzehn Stunden ergaebe und alles durchliesse.
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1),
         block('2026-09-02', '06:00', '10:00', 0)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_die_unterbrechung_am_selben_tag_ist_keine_ruhezeit():
    """Die Gegenprobe: zwischen 12:00 und 16:00 liegen vier Stunden, weniger als
    min_rest_hours. Sie duerfen trotzdem nichts blockieren - die taegliche
    Arbeitszeit endet erst um 20:00, und erst danach laeuft die Ruhezeit.

    Wer die Ruhezeit zwischen den Bloecken eines Tages prueft, laesst hier
    faelschlich einen Block offen.
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_ruhezeit_zum_vortag_gilt_weiterhin():
    """Bestandsverhalten, hier nur mit einem geteilten Dienst am zweiten Tag.

    Der erste Tag endet um 22:00, der zweite begaenne um 06:00 - acht Stunden.
    Der Morgenblock ist damit gesperrt, der Abendblock desselben Tages nicht.
    """
    ergebnis = plan(
        [block('2026-09-01', '14:00', '22:00', 0),
         block('2026-09-02', '06:00', '10:00', 0),
         block('2026-09-02', '18:00', '22:00', 1)],
        [person(1)],
    )

    assert ergebnis['unfilled_count'] == 1
    besetzt = {(z['date'], z['start_time']) for z in ergebnis['assignments']
               if z['employee_id'] is not None}
    assert ('2026-09-02', '06:00') not in besetzt


def test_ohne_bekannte_zeiten_bleibt_es_bei_einem_block_pro_tag():
    """Rueckwaertskompatibilitaet, und der Grund, warum test_scheduler.py gruen bleibt.

    Bloecke ohne Uhrzeiten haben keine Minutenachse - ueberschneidungsfrei
    laesst sich da nichts pruefen. Fuer sie gilt weiterhin die alte Regel
    "einmal pro Tag", sonst saehe ein Test, der nur mit Schichtzahlen
    arbeitet, dieselbe Person ploetzlich mehrfach am selben Tag.
    """
    ohne_zeiten = [
        {**block('2026-09-01', '08:00', '12:00', 0),
         'start_time': None, 'end_time': None, 'duration_minutes': None},
        {**block('2026-09-01', '16:00', '20:00', 1),
         'start_time': None, 'end_time': None, 'duration_minutes': None},
    ]

    ergebnis = plan(ohne_zeiten, [person(1)])

    assert ergebnis['unfilled_count'] == 1


def test_zwei_personen_teilen_sich_den_tag_wenn_es_fairer_ist():
    """Der geteilte Dienst ist eine Moeglichkeit, keine Vorgabe.

    Bei zwei Leuten und zwei Bloecken muss das Fairness-Ziel dafuer sorgen,
    dass jeder einen bekommt, statt einem beide aufzuladen.
    """
    ergebnis = plan(
        [block('2026-09-01', '08:00', '12:00', 0),
         block('2026-09-01', '16:00', '20:00', 1)],
        [person(1), person(2)],
    )

    assert ergebnis['unfilled_count'] == 0
    assert {z['employee_id'] for z in ergebnis['assignments']} == {1, 2}


# ---------- Netto-Arbeitszeit (Etappe 5a) ----------


def test_die_tagesgrenze_rechnet_netto():
    """Paragraph 2 Abs. 1 ArbZG: Arbeitszeit ist die Spanne ohne die Ruhepause.

    Zwei Bloecke von je sieben Stunden sind vierzehn Stunden Anwesenheit, aber
    nur dreizehn Stunden Arbeitszeit - je 30 Minuten gesetzliche Pause gehen ab.
    Bei einer Grenze von dreizehn Stunden entscheidet genau das: brutto
    gerechnet bliebe ein Block offen, netto gehen beide.
    """
    ergebnis = plan(
        [block('2026-09-01', '06:00', '13:00', 0),
         block('2026-09-01', '14:00', '21:00', 1)],
        [person(1, max_daily_hours=13)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_die_tagesgrenze_bindet_trotzdem():
    """Gegenprobe zum Test darueber.

    Dieselben Bloecke, Grenze zwoelf Stunden. Auch netto sind es dreizehn -
    einer bleibt offen. Ohne diesen Test waere eine Umsetzung gruen, die die
    Grenze gar nicht mehr prueft.
    """
    ergebnis = plan(
        [block('2026-09-01', '06:00', '13:00', 0),
         block('2026-09-01', '14:00', '21:00', 1)],
        [person(1, max_daily_hours=12)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_die_wochengrenze_rechnet_netto():
    """Fuenf Achtstundentage sind 40 Stunden Anwesenheit, aber 37,5 Stunden
    Arbeitszeit. Bei einem Wochenziel von 38 Stunden entscheidet genau das."""
    bloecke = [block(f'2026-09-0{tag}', '08:00', '16:00', 0) for tag in range(1, 6)]

    ergebnis = plan(bloecke, [person(1, weekly_hours=38, max_daily_hours=None)])

    assert ergebnis['unfilled_count'] == 0


def test_die_wochengrenze_bindet_trotzdem():
    """Gegenprobe: bei einem Wochenziel von 37 Stunden reichen auch 37,5
    netto nicht - ein Tag bleibt offen."""
    bloecke = [block(f'2026-09-0{tag}', '08:00', '16:00', 0) for tag in range(1, 6)]

    ergebnis = plan(bloecke, [person(1, weekly_hours=37, max_daily_hours=None)])

    assert ergebnis['unfilled_count'] == 1
