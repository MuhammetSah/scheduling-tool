"""Bestehenden Schichtbedarf einmalig in Bedarfsbaender ueberfuehren.

0006_coverage.py hat die drei Tabellen angelegt, coverage_requirements dabei
aber leer gelassen (siehe dortiger Docstring: "keine Ableitung von Bedarf -
das ist eine spaetere Etappe"). Diese Migration ist diese spaetere Etappe:
sie liest fuer jeden Wochentag die Schichtarten samt ihrem required_count
(shift_types verbunden mit shift_requirements), schickt sie durch
coverage_curve() aus coverage_model.py und schreibt das Ergebnis nach
coverage_requirements - damit ein laufender Betrieb mit gepflegten
Schichtarten nach dieser Migration nicht bei einem leeren Bedarf anfaengt.

Eine eigene Migration statt einer Erweiterung von 0006_coverage.py: eine
Schemamigration und eine Datenmigration tragen unterschiedliche Risiken und
brauchen unterschiedliche Ruecknahmen. Getrennt laesst sich die Ableitung
zurueckrollen, ohne die drei Tabellen aus 0006 zu verlieren - stellt sich die
Kurve als falsch heraus, ist die Korrektur eine Zeile Rollback statt einer
Rekonstruktion der Tabellen samt Bestandsdaten.

Der Import von coverage_curve aus coverage_model hier in einer Migration ist
ungewoehnlich, aber bewusst: die Alternative waere, die Kurvenlogik ein
zweites Mal in dieser Datei nachzubauen. Zwei Kopien derselben Rechenlogik
driften ueber die Zeit auseinander, sobald coverage_model.py sich
weiterentwickelt (neue Randfaelle, ein behobener Fehler) und diese Migration
davon nichts erfaehrt, weil sie laengst gelaufen und nie wieder angefasst
wird. Ein einziger Ort fuer die Kurve ist deshalb wichtiger als die sonst in
diesem Projekt uebliche Unabhaengigkeit einer Migration von Anwendungscode.
"""

from coverage_model import coverage_curve


def up(cursor):
    """Leitet Bedarfsbaender aus den Schichtarten ab, aber nur auf leerem Bestand.

    Der Waechter unten (die Zaehlung von coverage_requirements) ist keine
    Optimierung, sondern die inhaltlich richtige Grenze: laeuft diese
    Migration ein zweites Mal - etwa nach einem Rollback ueber down() - auf
    einer Datenbank, in der zwischenzeitlich von Hand Baender gepflegt
    wurden, wuerde ein blindes Neuableiten diese Handarbeit stillschweigend
    ueberschreiben. Gleichzeitig ist genau diese Pruefung die Grundlage fuer
    die Wiederholbarkeit: nach down() (das die Baender loescht, siehe unten)
    ist die Tabelle wieder leer, und ein erneutes up() leitet sauber neu ab.
    """
    cursor.execute('SELECT COUNT(*) AS anzahl FROM coverage_requirements')
    if cursor.fetchone()['anzahl'] > 0:
        return

    for wochentag in range(7):
        cursor.execute(
            'SELECT st.start_time AS start_time, st.end_time AS end_time, '
            'sr.required_count AS required_count '
            'FROM shift_types st '
            'JOIN shift_requirements sr ON sr.shift_type_id = st.id '
            'WHERE sr.weekday = ?',
            (wochentag,))
        schichtarten = cursor.fetchall()

        for band in coverage_curve(schichtarten):
            cursor.execute(
                'INSERT INTO coverage_requirements (weekday, start_time, end_time, required_count) '
                'VALUES (?, ?, ?, ?)',
                (wochentag, band['start_time'], band['end_time'], band['required_count']))


def down(cursor):
    """Loescht nur die Baender, nicht die Tabelle.

    coverage_requirements gehoert 0006_coverage.py - diese Migration hat sie
    nicht angelegt und darf sie deshalb auch nicht wieder entfernen (siehe
    dortiges down(), das alle drei Tabellen selbst zuruecknimmt). Ein DELETE
    ohne WHERE trifft hier sowohl abgeleitete als auch zwischenzeitlich von
    Hand gepflegte Baender gleichermassen - das ist die bewusste Grenze
    dieser Ruecknahme: nach dem Einfuegen weiss keine Zeile mehr, ob sie aus
    der Ableitung stammt oder von Hand angelegt wurde.
    """
    cursor.execute('DELETE FROM coverage_requirements')
