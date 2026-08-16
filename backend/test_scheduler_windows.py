"""Tests fuer die Arbeitszeitfenster-Pruefung in structurally_eligible().

Reine Funktionen, keine Datenbank - siehe Etappenplan, Abschnitt
"Die zentrale Semantik". Jede Zeile der dortigen Beispieltabelle taucht hier
als eigener Test auf.
"""
import unittest

from scheduler import (
    structurally_eligible,
    time_to_minutes,
    window_contains_shift,
    window_is_valid_on,
)


def _employee(**overrides):
    """Minimales, gueltiges Mitarbeiter-Dict fuer structurally_eligible().

    Enthaelt absichtlich weder 'availability_mode' noch 'availability', sofern
    nicht explizit ueberschrieben - das ist der Bestandszustand vor dieser
    Etappe.
    """
    base = {
        'id': 1,
        'unavailable_weekdays': set(),
        'unavailable_dates': set(),
        'allowed_shift_types': None,
    }
    base.update(overrides)
    return base


def _slot(**overrides):
    """Minimaler Slot wie ihn build_slots() erzeugt. 2026-08-14 ist ein Freitag."""
    base = {
        'date': '2026-08-14',
        'weekday': 4,
        'shift_type_id': 1,
        'start_time': '08:00',
        'end_time': '14:00',
    }
    base.update(overrides)
    return base


class ZeitInMinuten(unittest.TestCase):
    def test_hh_mm_wird_in_minuten_seit_mitternacht_umgerechnet(self):
        self.assertEqual(time_to_minutes('00:00'), 0)
        self.assertEqual(time_to_minutes('08:00'), 480)
        self.assertEqual(time_to_minutes('23:59'), 1439)


class FensterEnthaeltSchicht(unittest.TestCase):
    """Jede Zeile der Beispieltabelle aus dem Etappenplan, eine pro Test."""

    def test_exakt_gleiche_zeiten_sind_erlaubt(self):
        fenster = {'start_time': '08:00', 'end_time': '14:00'}
        self.assertTrue(window_contains_shift(fenster, '08:00', '14:00'))

    def test_echt_enthaltene_schicht_ist_erlaubt(self):
        fenster = {'start_time': '08:00', 'end_time': '14:00'}
        self.assertTrue(window_contains_shift(fenster, '09:00', '13:00'))

    def test_schicht_beginnt_zu_frueh_ist_verboten(self):
        fenster = {'start_time': '08:00', 'end_time': '14:00'}
        self.assertFalse(window_contains_shift(fenster, '06:00', '14:00'))

    def test_schicht_endet_zu_spaet_ist_verboten(self):
        fenster = {'start_time': '08:00', 'end_time': '14:00'}
        self.assertFalse(window_contains_shift(fenster, '08:00', '16:00'))

    def test_nachtschicht_passt_nicht_in_tagfenster(self):
        # [1320,1800] (22:00-06:00 mit Mitternachtsueberschreitung) liegt nicht
        # in [480,840] (08:00-14:00).
        fenster = {'start_time': '08:00', 'end_time': '14:00'}
        self.assertFalse(window_contains_shift(fenster, '22:00', '06:00'))

    def test_nachtschicht_passt_in_ueber_mitternacht_reichendes_fenster(self):
        fenster = {'start_time': '20:00', 'end_time': '06:00'}
        self.assertTrue(window_contains_shift(fenster, '22:00', '06:00'))

    def test_schicht_beginnt_vor_dem_ueber_mitternacht_reichenden_fenster(self):
        fenster = {'start_time': '20:00', 'end_time': '06:00'}
        self.assertFalse(window_contains_shift(fenster, '19:00', '23:00'))


class FensterGueltigkeit(unittest.TestCase):
    def test_ohne_grenzen_ist_ein_fenster_immer_gueltig(self):
        self.assertTrue(window_is_valid_on({'valid_from': None, 'valid_until': None}, '2026-08-14'))

    def test_gueltig_ab_schliesst_den_stichtag_ein(self):
        fenster = {'valid_from': '2026-08-14', 'valid_until': None}
        self.assertTrue(window_is_valid_on(fenster, '2026-08-14'))
        self.assertFalse(window_is_valid_on(fenster, '2026-08-13'))

    def test_gueltig_bis_schliesst_den_stichtag_ein(self):
        fenster = {'valid_from': None, 'valid_until': '2026-08-14'}
        self.assertTrue(window_is_valid_on(fenster, '2026-08-14'))
        self.assertFalse(window_is_valid_on(fenster, '2026-08-15'))


class Rueckwaertskompatibilitaet(unittest.TestCase):
    def test_ohne_modus_verhaelt_sich_alles_wie_bisher(self):
        """Ein Mitarbeiter-Dict ohne die neuen Schluessel darf nie eingeschraenkt werden."""
        mitarbeiter = _employee()  # weder 'availability_mode' noch 'availability' im Dict
        schicht_ausserhalb_jeder_denkbaren_zeit = _slot(start_time='02:00', end_time='03:00')
        self.assertTrue(structurally_eligible(mitarbeiter, schicht_ausserhalb_jeder_denkbaren_zeit))

    def test_anytime_ignoriert_vorhandene_fenster(self):
        """Wer auf 'anytime' steht, ist auch dann frei, wenn Fenster eingetragen sind -
        der Schalter entscheidet, nicht die Anwesenheit von Zeilen."""
        mitarbeiter = _employee(
            availability_mode='anytime',
            availability=[{'weekday': 4, 'start_time': '08:00', 'end_time': '14:00',
                           'valid_from': None, 'valid_until': None}],
        )
        schicht_ausserhalb_des_eingetragenen_fensters = _slot(start_time='02:00', end_time='03:00')
        self.assertTrue(structurally_eligible(mitarbeiter, schicht_ausserhalb_des_eingetragenen_fensters))


class ModusWindows(unittest.TestCase):
    def test_windows_ohne_fenster_fuer_diesen_wochentag_verbietet(self):
        """Kein Fenster am Freitag heisst freitags gar nicht."""
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[{'weekday': 1, 'start_time': '08:00', 'end_time': '14:00',  # nur dienstags
                           'valid_from': None, 'valid_until': None}],
        )
        schicht_freitag = _slot(weekday=4, start_time='08:00', end_time='14:00')
        self.assertFalse(structurally_eligible(mitarbeiter, schicht_freitag))

    def test_schicht_innerhalb_des_fensters_ist_erlaubt(self):
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[{'weekday': 4, 'start_time': '08:00', 'end_time': '14:00',
                           'valid_from': None, 'valid_until': None}],
        )
        schicht = _slot(weekday=4, start_time='09:00', end_time='13:00')
        self.assertTrue(structurally_eligible(mitarbeiter, schicht))

    def test_schicht_ausserhalb_des_fensters_ist_verboten(self):
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[{'weekday': 4, 'start_time': '08:00', 'end_time': '14:00',
                           'valid_from': None, 'valid_until': None}],
        )
        schicht = _slot(weekday=4, start_time='06:00', end_time='14:00')
        self.assertFalse(structurally_eligible(mitarbeiter, schicht))

    def test_zwei_fenster_am_selben_tag_schicht_muss_in_eines_passen(self):
        """08:00-12:00 und 16:00-20:00; eine Schicht 11:00-17:00 passt in keines,
        obwohl sie von der Vereinigung ueberdeckt waere."""
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[
                {'weekday': 4, 'start_time': '08:00', 'end_time': '12:00',
                 'valid_from': None, 'valid_until': None},
                {'weekday': 4, 'start_time': '16:00', 'end_time': '20:00',
                 'valid_from': None, 'valid_until': None},
            ],
        )
        schicht_ueberbrueckend = _slot(weekday=4, start_time='11:00', end_time='17:00')
        self.assertFalse(structurally_eligible(mitarbeiter, schicht_ueberbrueckend))

        # Gegenprobe: innerhalb jeweils eines der beiden Einzelfenster geht es.
        self.assertTrue(structurally_eligible(mitarbeiter, _slot(weekday=4, start_time='08:00', end_time='12:00')))
        self.assertTrue(structurally_eligible(mitarbeiter, _slot(weekday=4, start_time='16:00', end_time='20:00')))

    def test_gueltigkeitszeitraum_grenzen_sind_einschliessend(self):
        """valid_from == Slotdatum und valid_until == Slotdatum gelten beide noch."""
        fenster = {'weekday': 4, 'start_time': '08:00', 'end_time': '14:00',
                   'valid_from': '2026-08-14', 'valid_until': '2026-08-14'}
        mitarbeiter = _employee(availability_mode='windows', availability=[fenster])

        schicht_am_stichtag = _slot(date='2026-08-14', weekday=4, start_time='08:00', end_time='14:00')
        self.assertTrue(structurally_eligible(mitarbeiter, schicht_am_stichtag))

        schicht_einen_tag_davor = _slot(date='2026-08-13', weekday=3, start_time='08:00', end_time='14:00')
        self.assertFalse(structurally_eligible(mitarbeiter, schicht_einen_tag_davor))

        schicht_einen_tag_danach = _slot(date='2026-08-15', weekday=5, start_time='08:00', end_time='14:00')
        self.assertFalse(structurally_eligible(mitarbeiter, schicht_einen_tag_danach))

    def test_nachtschicht_wird_gegen_den_wochentag_des_beginns_geprueft(self):
        """Freitag 22:00-06:00 gegen Freitagsfenster, nicht gegen Samstag."""
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[{'weekday': 4, 'start_time': '20:00', 'end_time': '06:00',  # nur freitags
                           'valid_from': None, 'valid_until': None}],
        )
        nachtschicht_als_freitagsslot = _slot(date='2026-08-14', weekday=4, start_time='22:00', end_time='06:00')
        self.assertTrue(structurally_eligible(mitarbeiter, nachtschicht_als_freitagsslot))

        # Dieselben Uhrzeiten, aber der Slot traegt den Samstags-Wochentag -
        # das Fenster gilt nur freitags, also verboten.
        nachtschicht_als_samstagsslot = _slot(date='2026-08-15', weekday=5, start_time='22:00', end_time='06:00')
        self.assertFalse(structurally_eligible(mitarbeiter, nachtschicht_als_samstagsslot))

    def test_slot_ohne_zeiten_wird_nicht_eingeschraenkt(self):
        """build_slots() setzt start_time/end_time auf None, wenn die Schichtart
        keine Zeiten hat. Dann gibt es nichts zu pruefen - so wie die
        Ruhezeit-Pruefung es auch haelt."""
        mitarbeiter = _employee(
            availability_mode='windows',
            availability=[{'weekday': 1, 'start_time': '08:00', 'end_time': '14:00',  # nur dienstags
                           'valid_from': None, 'valid_until': None}],
        )
        schicht_ohne_zeiten_an_einem_tag_ohne_fenster = _slot(weekday=4, start_time=None, end_time=None)
        self.assertTrue(structurally_eligible(mitarbeiter, schicht_ohne_zeiten_an_einem_tag_ohne_fenster))


if __name__ == '__main__':
    unittest.main()
