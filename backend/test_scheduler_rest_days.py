"""Sechstageregel und freie Sonntage im Suchkern.

Paragraph 11 Abs. 3 ArbZG verlangt fuer jeden gearbeiteten Sonntag einen
Ersatzruhetag binnen zwei Wochen. Das ist eine Bedingung ueber das FEHLEN von
Zuweisungen und fuer einen Backtracking-Suchlauf schlecht greifbar. Wer nie
mehr als sechs Tage in Folge arbeitet, hat aber spaetestens alle sieben Tage
frei - damit ist das Zweiwochenfenster erfuellt und das Achtwochenfenster der
Feiertage erst recht. Die Regel ist dafuer strenger als die Norm; das ist eine
bewusste Vereinfachung, siehe Spec Paragraph 2.

Paragraph 11 Abs. 1 verlangt mindestens 15 beschaeftigungsfreie Sonntage im
Kalenderjahr.

Die Helfer sind bewusst aus test_scheduler_split_shifts.py wiederholt statt
importiert: zwei Testmodule, die einander importieren, sind schwerer zu lesen
als zwanzig Zeilen Wiederholung - und person() bekommt hier zwei zusaetzliche
Felder.
"""

from datetime import date, timedelta

from scheduler import CHRONOLOGICAL, generate_schedule


def person(employee_id, **abweichend):
    basis = {
        'id': employee_id,
        'max_shifts_per_month': None,
        'unavailable_weekdays': set(),
        'unavailable_dates': set(),
        'allowed_shift_types': None,
        'weekly_hours': None,
        'min_rest_hours': 0,          # Ruhezeit hier abgeschaltet: geprueft wird
        'max_daily_hours': None,      # die Tagesfolge, nicht die Stundenlage
        # Wie min_rest_hours: das Gesetz legt die Zahl fest, geprueft wird
        # trotzdem nur, was der Aufrufer mitgibt. So bleiben die 23
        # Bestandstests in test_scheduler.py unberuehrt, die nur mit
        # Schichtzahlen arbeiten.
        'max_consecutive_days': 6,
        'availability_mode': 'anytime',
        'availability': [],
    }
    basis.update(abweichend)
    return basis


def block(iso_date, start_time, end_time, slot_index=0, shift_type_id=None):
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


def plan(bloecke, leute, jahr=2026, monat=9):
    return generate_schedule(jahr, monat, leute, [], ordering=CHRONOLOGICAL, slots=bloecke)


def tagesbloecke(tage, jahr=2026, monat=9):
    return [block(f'{jahr}-{monat:02d}-{tag:02d}', '08:00', '16:00', 0) for tag in tage]


# ---------- Sechstageregel ----------


def test_der_siebte_tag_in_folge_bleibt_offen():
    ergebnis = plan(tagesbloecke(range(1, 8)), [person(1)])

    assert ergebnis['unfilled_count'] == 1


def test_sechs_tage_in_folge_gehen():
    """Gegenprobe: ohne sie waere eine Umsetzung gruen, die schon bei sechs sperrt."""
    ergebnis = plan(tagesbloecke(range(1, 7)), [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_die_kette_baut_sich_auch_von_hinten_auf():
    """Der Fall, den eine Nur-nach-links-Zaehlung durchliesse.

    Die Bloecke werden in umgekehrter Kalenderreihenfolge angeboten. Wer die
    Kette nur nach links zaehlt, sieht bei jedem einzelnen Block eine Kette der
    Laenge eins und laesst alle sieben zu. Der Suchkern ordnet die Slots zwar
    bei CHRONOLOGICAL um, aber MOST_CONSTRAINED tut das nicht - und AUTO
    benutzt beide.
    """
    ergebnis = plan(tagesbloecke(range(7, 0, -1)), [person(1)])

    assert ergebnis['unfilled_count'] == 1


def test_eine_luecke_setzt_die_kette_zurueck():
    """Sieben Tage mit einem freien Tag in der Mitte sind zwei kurze Ketten."""
    ergebnis = plan(tagesbloecke([1, 2, 3, 5, 6, 7, 8]), [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_die_vorgeschichte_verlaengert_die_kette_ueber_den_monatsanfang():
    """Wer schon vier Tage im Vormonat gearbeitet hat, darf nur noch zwei."""
    ergebnis = plan(tagesbloecke([1, 2, 3]), [person(1, days_worked_before_month=4)])

    assert ergebnis['unfilled_count'] == 1


def test_ohne_vorgeschichte_beginnt_die_kette_am_monatsersten():
    """Fehlt days_worked_before_month, gilt der Vormonat als frei."""
    ergebnis = plan(tagesbloecke([1, 2, 3]), [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_ohne_max_consecutive_days_wird_gar_nicht_geprueft():
    """Der Zweig, der die 23 Bestandstests in test_scheduler.py gruen haelt.

    Sie arbeiten nur mit Schichtzahlen und liefern das Feld nicht - dann darf
    die Regel nicht greifen, sonst aendert sich ihr Ergebnis. Dieselbe Haltung
    wie bei weekly_hours, min_rest_hours und max_daily_hours: das Gesetz legt
    die Zahl fest, geprueft wird trotzdem nur, was der Aufrufer mitgibt.

    Sieben Tage in Folge, sonst identisch zum ersten Test dieser Datei - dort
    bleibt einer offen, hier keiner.
    """
    ohne_feld = person(1)
    del ohne_feld['max_consecutive_days']

    ergebnis = plan(tagesbloecke(range(1, 8)), [ohne_feld])

    assert ergebnis['unfilled_count'] == 0


# ---------- Freie Sonntage ----------
#
# 2026 hat 52 Sonntage. 52 - 15 = 37 duerfen gearbeitet werden.


def test_das_sonntagsbudget_bindet():
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=37)])

    assert ergebnis['unfilled_count'] == 1


def test_ein_sonntag_unter_dem_budget_geht():
    """Gegenprobe: ohne sie waere eine Umsetzung gruen, die jeden Sonntag sperrt."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=36)])

    assert ergebnis['unfilled_count'] == 0


def test_ein_zweiter_block_am_selben_sonntag_kostet_kein_zweites_budget():
    """Ein geteilter Dienst macht aus einem Sonntag keine zwei.

    Beschaeftigungsfrei heisst: kein einziger Block an dem Tag. Ohne diese
    Ausnahme waere ein geteilter Dienst am Sonntag teurer als einer unter der
    Woche - wofuer es im Gesetz keinen Grund gibt, und was genau das Feature
    aus Etappe 4 bestrafen wuerde.
    """
    ergebnis = plan(
        [block('2026-09-06', '08:00', '12:00', 0),
         block('2026-09-06', '16:00', '20:00', 1)],
        [person(1, sundays_worked_in_year=36)],
    )

    assert ergebnis['unfilled_count'] == 0


def test_zwei_verschiedene_sonntage_kosten_zwei():
    """Gegenprobe zum Test darueber: verschiedene Daten zaehlen sehr wohl einzeln."""
    ergebnis = plan(
        [block('2026-09-06', '08:00', '16:00', 0),
         block('2026-09-13', '08:00', '16:00', 0)],
        [person(1, sundays_worked_in_year=36)],
    )

    assert ergebnis['unfilled_count'] == 1


def test_ein_negatives_budget_sperrt_nur_und_wirft_nicht():
    """Wer die Grenze in der Vergangenheit schon gerissen hat, wird nicht weiter
    eingeplant - aber der Planer wirft keinen Fehler ueber Daten, die er nicht
    verursacht hat."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=99)])

    assert ergebnis['unfilled_count'] == 1


def test_werktage_beruehrt_das_budget_nicht():
    """Der 07.09.2026 ist ein Montag."""
    ergebnis = plan([block('2026-09-07', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=99)])

    assert ergebnis['unfilled_count'] == 0


def test_ohne_sundays_worked_in_year_wird_gar_nicht_geprueft():
    """Derselbe Kompatibilitaetszweig wie bei der Sechstageregel."""
    ergebnis = plan([block('2026-09-06', '08:00', '16:00', 0)], [person(1)])

    assert ergebnis['unfilled_count'] == 0


def test_ein_jahr_mit_53_sonntagen_hat_ein_groesseres_budget():
    """2028 hat 53 Sonntage, also 38 statt 37 erlaubte.

    Ohne diesen Test waere eine fest verdrahtete 52 ebenfalls gruen. Der 03.09.
    2028 ist ein Sonntag; mit 37 bereits gearbeiteten bleibt genau einer uebrig.
    """
    ergebnis = plan([block('2028-09-03', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=37)], jahr=2028)

    assert ergebnis['unfilled_count'] == 0


def test_dasselbe_jahr_mit_38_gearbeiteten_sonntagen_ist_ausgeschoepft():
    """Gegenprobe: auch 53 Sonntage sind endlich."""
    ergebnis = plan([block('2028-09-03', '08:00', '16:00', 0)],
                    [person(1, sundays_worked_in_year=38)], jahr=2028)

    assert ergebnis['unfilled_count'] == 1
