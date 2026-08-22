# Design: Etappe 5d — Feiertagskalender

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Geschwister:** [`5b — Sechstageregel und freie Sonntage`](2026-08-22-etappe-5b-sonntage-design.md), [`5c — Achtstundenschnitt`](2026-08-22-etappe-5c-durchschnitt-design.md)
**Status:** Entwurf

---

## 1. Ziel

Das Tool weiß nicht, welche Tage gesetzliche Feiertage sind. [§ 9](https://www.gesetze-im-internet.de/arbzg/__9.html)
verbietet Feiertagsarbeit, nennt aber **keine Feiertage** — er benutzt den Begriff und überlässt
die Füllung dem Landesrecht. Deshalb ist der Kalender eine Tabelle je Bundesland, und deshalb
war er beim Ausarbeiten von 5b als eigenes Stück herausgelöst worden.

Diese Etappe holt ihn nach: Kennzeichnung und Warnung — **und** sie schließt die Lücke, die 5c
ausdrücklich offengelassen hat.

## 2. Was der Kalender leistet, und was nicht

Beim Zuschnitt von 5b war festgestellt worden, dass ein Feiertagskalender **keine der
Arbeitszeitregeln durchsetzt**: § 11 Abs. 3 für Feiertage ist von der Sechstageregel abgedeckt,
§ 9 wird über die Öffnungszeiten entschieden, § 11 Abs. 1 betrifft nur Sonntage. Das gilt
unverändert.

Was er leistet:

| | |
|---|---|
| **Kennzeichnung** | HR sieht im Plan, dass der 3. Oktober ein Feiertag ist — vor dem Veröffentlichen, nicht danach |
| **Warnung** | Eine Zuweisung an einem Feiertag meldet, nicht blockierend wie alles auf diesem Pfad |
| **Der Nenner aus 5c** | 5c rechnet Feiertage als Werktage mit und ist dadurch **zu nachsichtig** — rund drei Prozent über 24 Wochen. Mit dem Kalender fällt das weg, und das ist der einzige Punkt, an dem diese Etappe eine Rechnung genauer macht statt nur etwas sichtbar |

**Feiertage werden nicht automatisch geschlossen.** So entschieden: das Tool kann nicht wissen,
ob der Betrieb unter § 10 fällt, und ein Krankenhaus oder eine Gaststätte am 3. Oktober
zuzusperren wäre schlicht falsch. Die Öffnungszeiten entscheiden weiter.

## 3. Der Kalender

Neues Modul `backend/holidays.py` — reine Rechenlogik ohne Datenbank, wie `coverage_model.py`
und `block_planner.py`.

**Bundesweit** (alle sechzehn Länder): Neujahr 01.01., Karfreitag (Ostern −2), Ostermontag
(+1), Tag der Arbeit 01.05., Christi Himmelfahrt (+39), Pfingstmontag (+50), Tag der Deutschen
Einheit 03.10., 1. und 2. Weihnachtstag 25./26.12.

**Regional:**

| Feiertag | Datum | Länder |
|---|---|---|
| Heilige Drei Könige | 06.01. | BW, BY, ST |
| Internationaler Frauentag | 08.03. | BE, MV |
| Ostersonntag | Ostern | BB |
| Pfingstsonntag | Ostern +49 | BB |
| Fronleichnam | Ostern +60 | BW, BY, HE, NW, RP, SL |
| Mariä Himmelfahrt | 15.08. | SL |
| Weltkindertag | 20.09. | TH |
| Reformationstag | 31.10. | BB, HB, HH, MV, NI, SN, ST, SH, TH |
| Allerheiligen | 01.11. | BW, BY, NW, RP, SL |
| Buß- und Bettag | Mittwoch vor dem 23.11. | SN |

**Ostern** über den anonymen gregorianischen Algorithmus (Gauß/Butcher). Keine Bibliothek: es
sind zwölf Zeilen Arithmetik, und das Projekt hat i18n und den Migrations-Runner aus demselben
Grund selbst gebaut.

### 3.1 Was der Kalender bewusst nicht kennt

Feiertage **unterhalb der Bundeslandebene**:

- Fronleichnam gilt in Sachsen und Thüringen nur in überwiegend katholischen Gemeinden;
- Mariä Himmelfahrt in Bayern nur in überwiegend katholischen Gemeinden;
- das Augsburger Friedensfest (08.08.) nur in der Stadt Augsburg.

Ein Bundesland allein entscheidet das nicht, und eine Gemeindeliste wäre ein eigenes Vorhaben.
Wer davon betroffen ist, trägt den Tag wie bisher als Öffnungszeit-Ausnahme ein. **Der Kalender
ist damit in der nachsichtigen Richtung unvollständig** — er kennt einen Feiertag zu wenig, nie
einen zu viel.

## 4. Die Einstellung

Es gibt keine Einstellungstabelle im Projekt. Diese Etappe legt eine an:

**Migration `0011_settings`:**

```
settings(name TEXT PRIMARY KEY, value TEXT NOT NULL)
```

`name`, nicht `key` — `key` ist in manchen Dialekten heikel, und die Dialektschicht des
Projekts soll sich damit nicht befassen müssen.

Ein Schlüssel wird gesetzt: `holiday_region`, der zweistellige Ländercode. **Ohne Eintrag kennt
das Tool keine Feiertage** und verhält sich wie bisher — kein Standard-Bundesland, weil es
keinen gibt, den man raten könnte.

Eine Schlüssel-Wert-Tabelle für eine Einstellung ist grenzwertig YAGNI. Sie gewinnt trotzdem:
es gibt keinen anderen Ort, an den die Einstellung gehört, und aus Etappe 5 kommen absehbar
weitere (Veröffentlichen-Workflow, Aufbewahrungsfristen). Eine Spalte an einer fachfremden
Tabelle wäre der schlechtere Kompromiss.

## 5. API

| Methode | Route | Zweck |
|---|---|---|
| GET | `/settings` | Alle Einstellungen als Objekt (HR) |
| PUT | `/settings` | Setzt die übergebenen Schlüssel, lässt die übrigen stehen (HR) |

`PUT` **ersetzt nicht vollständig** — anders als die Constraint-Listen. Eine Einstellung ist
kein Bestand, den man am Stück pflegt, und ein Aufrufer, der einen Schlüssel setzt, soll die
anderen nicht kennen müssen. Ein unbekannter Schlüssel ist `400`: hier ist Strenge richtig,
weil ein Tippfehler sonst still ins Leere liefe.

`GET /schedules/<year>/<month>` liefert zusätzlich `holidays: [{date, name}]` für die Tage des
Monats. Leer, solange kein Bundesland gewählt ist.

**Warnung** `warn_public_holiday` auf dem Handkorrektur-Pfad.

## 6. Der Nenner aus 5c

`working_days_in(first, last)` bekommt einen optionalen Parameter mit den Feiertagsdaten des
Zeitraums. Ein Feiertag, der auf einen Werktag fällt, zählt nicht mehr mit; einer auf einem
Sonntag ändert nichts, weil der Sonntag ohnehin nicht zählte.

Damit fällt die Nachsicht weg, die 5c dokumentiert hat — **aber nur, wenn ein Bundesland
gewählt ist**. Ohne Auswahl bleibt es beim bisherigen Verhalten, und das gehört in denselben
Hinweis, der heute schon unter der Liste steht.

## 7. Frontend

- Eine Bundeslandauswahl. Sie gehört zu den Öffnungszeiten — dort steht schon alles, was den
  Betrieb als Ganzes betrifft
- Feiertage in `CalendarView` markieren, mit dem Namen als Titel
- Der Hinweis unter `AverageHours` wird abhängig davon formuliert, ob ein Bundesland gewählt ist

## 8. Tests

| Ebene | Was |
|---|---|
| `test_holidays.py` (neu) | Ostern für mehrere Jahre gegen bekannte Daten; die beweglichen Feiertage relativ dazu; Buß- und Bettag als Mittwoch vor dem 23.11. über mehrere Jahre; je ein Land mit und ohne einen regionalen Feiertag als **Paar** — Fronleichnam gilt in Bayern und nicht in Berlin |
| `test_holidays.py` | Ohne Bundesland kommt eine leere Menge, nicht ein Fehler |
| `test_migrations.py` / `_postgres.py` | Rundlauf `0011` |
| API | `GET`/`PUT /settings`; unbekannter Schlüssel ist 400; `holidays` im Monat; die Warnung mit Gegenprobe |
| API | **Die Gegenprobe zu §6:** derselbe Monat meldet den Achtstundenschnitt mit gewähltem Bundesland und ohne unterschiedlich, weil der Nenner sich ändert |
| Frontend | Auswahl vorhanden; Feiertag markiert |

## 9. Bewusst nicht dabei

- **Feiertage unterhalb der Bundeslandebene** (§3.1)
- **Automatisches Schließen** an Feiertagen (§2)
- **Mehrere Bundesländer gleichzeitig** — ein Betrieb, ein Standort. Wer mehrere hat, hat ein
  größeres Problem als diesen Kalender
- **Ein Feiertagsdatum überschreiben** — dafür gibt es die Öffnungszeit-Ausnahmen
- **§ 9 durchsetzen** (§2)

## 10. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Die Ländertabelle ist falsch | Jede Zeile hat einen Test, und die regionalen als Paar aus Land mit und ohne. Die Tabelle steht an genau einer Stelle |
| Der Kalender kennt einen Feiertag nicht | Nur unterhalb der Bundeslandebene, dokumentiert (§3.1), und in der nachsichtigen Richtung |
| Der Nenner ändert sich und alte Meldungen sehen anders aus | Das ist die Absicht — 5c hat die Nachsicht ausdrücklich als Lücke benannt. Der Hinweis unter der Liste sagt, welche Rechnung gerade gilt |
| Eine Einstellungstabelle für eine Einstellung | Bewusst, siehe §4 |
