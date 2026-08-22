# Design: Etappe 5h — Exporte

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §10
**Status:** Entwurf

---

## 1. Ziel

Der Plan lebt heute ausschließlich in der Anwendung. Wer ihn im eigenen Kalender haben, an die
Lohnbuchhaltung geben oder ausdrucken will, muss abschreiben.

Zwei Exporte, die beide ohne neue Abhängigkeit auskommen:

| Format | Wofür | Wer |
|---|---|---|
| **iCal** (`.ics`) | Die eigenen Schichten im Telefonkalender | Jeder, für sich selbst; HR auch für andere |
| **CSV** | Weiterverarbeitung, Lohnbuchhaltung, Tabellenkalkulation | HR, ganzer Monat |

## 2. Die Abhängigkeitsfrage, und warum sie hier nicht gestellt wird

Die Roadmap nennt „PDF/Excel/iCal". PDF und Excel bräuchten je eine Bibliothek — das Projekt
hat bewusst fünf Laufzeitabhängigkeiten und hat i18n, den Migrations-Runner und den
Feiertagskalender selbst gebaut, statt sich welche zu holen.

**iCal ist ein Textformat** ([RFC 5545](https://datatracker.ietf.org/doc/html/rfc5545)), und für
das, was hier gebraucht wird — Termine mit Beginn, Ende, Titel — sind es rund vierzig Zeilen.
**CSV steht in der Standardbibliothek.** Beide gehen ohne.

PDF und Excel warten, bis jemand sie tatsächlich verlangt. Dann ist es eine Entscheidung mit
einem konkreten Anlass statt einer auf Vorrat — und wer eine Tabelle will, kann eine CSV in
jedem Tabellenprogramm öffnen.

## 3. iCal

`GET /employees/<id>/schedule.ics?year=&month=`

Zugriff nach `require_self_or_hr` — dieselbe Regel wie bei den Abwesenheiten und den
Arbeitszeitfenstern: die eigenen Schichten sieht man selbst, fremde nur als HR.

**Nur veröffentlichte Pläne.** Ein Entwurf ist für Mitarbeiter nicht vorhanden (Etappe 5f), und
ein Export, der ihn doch ausliefert, wäre die Hintertür durch die Wand daneben. Für HR gilt
dieselbe Regel — sonst verschickt jemand versehentlich einen Entwurf.

Ein Termin je Zuweisung:

| Feld | Inhalt |
|---|---|
| `SUMMARY` | Der Name der Schichtart, oder „Dienst" bei einem Block ohne Vorlage |
| `DTSTART`/`DTEND` | Die **tatsächlichen** Zeiten der Zuweisung, dreischichtig aufgelöst wie überall |
| `UID` | `assignment-<id>@schichtplan` — stabil, damit ein erneuter Import aktualisiert statt zu verdoppeln |
| `DESCRIPTION` | Die Ruhepause, wenn sie von der gesetzlichen abweicht |

**Zeitzone:** die Zeiten stehen ohne Zone (`DTSTART;VALUE=DATE-TIME` in lokaler Zeit), weil das
Tool durchgängig in Ortszeit rechnet und keine Zone speichert. Eine erfundene Zone wäre eine
Behauptung, die die Daten nicht tragen. Das gehört dokumentiert, weil ein Kalender in einer
anderen Zone die Termine sonst verschiebt.

**Zeilenumbruch `\\r\\n`**, wie RFC 5545 es verlangt — nicht `\\n`. Ein häufiger Fehler, und
manche Kalender lehnen die Datei sonst wortlos ab.

## 4. CSV

`GET /schedules/<year>/<month>/export.csv` (HR)

Eine Zeile je Zuweisung, mit Kopfzeile: Datum, Wochentag, Beginn, Ende, Pause (Minuten),
Arbeitszeit (Stunden, netto), Schichtart, Mitarbeiter. Unbesetzte Plätze stehen mit leerem
Mitarbeiterfeld drin — sie aus dem Export zu lassen hieße, eine Lücke verschwinden zu machen.

**Trennzeichen Semikolon und BOM.** Beides für Excel im deutschsprachigen Raum: ohne Semikolon
landet alles in einer Spalte, ohne BOM werden Umlaute zu Kauderwelsch. Das ist unschön und
richtig — eine CSV, die im Zielprogramm nicht aufgeht, ist kein Export.

**Auch nur veröffentlichte Pläne?** Nein. Die CSV ist HR-only und dient der Weiterverarbeitung;
ein Entwurf zu exportieren, um ihn zu prüfen, ist ein sinnvoller Vorgang. Der Unterschied zum
iCal ist der Empfänger: die CSV zieht HR für sich, das iCal landet im Telefon eines
Mitarbeiters.

## 5. Wo das im Code lebt

Neues Modul `backend/exports.py` — reine Formatierung, kein Datenbankzugriff, wie
`coverage_model.py` und `holidays.py`. Es bekommt fertige Zeilen und gibt Text zurück. Die
Routen holen die Daten über das bestehende `fetch_schedule()`.

## 6. Tests

| Ebene | Was |
|---|---|
| `test_exports.py` (neu) | Der iCal-Rumpf: `BEGIN:VCALENDAR`, ein `VEVENT` je Zuweisung, `\\r\\n` als Umbruch, stabile `UID`. Ein Termin über Mitternacht endet am Folgetag |
| `test_exports.py` | Zeichen, die in iCal maskiert werden müssen (Komma, Semikolon, Backslash, Zeilenumbruch) im Schichtartnamen |
| `test_exports.py` | CSV: Kopfzeile, Semikolon, BOM, unbesetzter Platz mit leerem Namen |
| API | iCal: self-or-HR; ein Entwurf liefert 404; ein fremder Mitarbeiter 403 |
| API | CSV: HR-only; ein Entwurf **wird** geliefert (Gegenprobe zum iCal) |
| API | `Content-Type` und `Content-Disposition` stimmen |

## 7. Bewusst nicht dabei

- **PDF und Excel** (§2)
- **Ein Abonnement-Link** (iCal-Feed mit Token, den der Kalender regelmäßig abruft). Reizvoll,
  aber ein dauerhaft gültiger Link auf personenbezogene Daten ist eine eigene Entscheidung mit
  eigenen Fragen — und ohne Widerruf wäre er ein Datenleck mit Ablaufdatum null
- **Zeitzonen im iCal** (§3)
- **Ein Export über mehrere Monate.** Die Monatsgrenze ist die bekannte Einschränkung des
  Werkzeugs

## 8. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Ein Kalender in anderer Zone verschiebt die Termine | Dokumentiert (§3); das Tool speichert keine Zone, eine erfundene wäre schlimmer |
| Ein Entwurf verlässt das Haus | Der iCal-Export liefert nur veröffentlichte Pläne, mit eigenem Test |
| Die CSV geht in Excel nicht auf | Semikolon und BOM, beides mit Test |
