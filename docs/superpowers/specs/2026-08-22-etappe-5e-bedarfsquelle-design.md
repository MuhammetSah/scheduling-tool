# Design: Etappe 5e — die alte Bedarfsquelle entfernen

**Datum:** 2026-08-22
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Übergeordnete Spec:** [`2026-08-16-zeitachsen-dienstplan-design.md`](2026-08-16-zeitachsen-dienstplan-design.md) §4.3, §10
**Status:** Entwurf

---

## 1. Ziel

Etappe 4 hat den Planer auf `coverage_requirements` umgestellt. `shift_requirements` wird
seither geschrieben und gespeichert, aber von nichts mehr gelesen, was den Plan beeinflusst —
die übergeordnete Spec sieht die Entfernung ausdrücklich „erst nach Etappe 4" vor.

Diese Etappe zieht das nach: Tabelle, Schreibpfad und API-Fläche verschwinden.

Kurz und ohne Nutzenversprechen an HR — es ist Aufräumen. Der Wert liegt darin, dass das Schema
wieder beschreibt, was das Tool tut.

## 2. Was verschwindet

| | |
|---|---|
| Tabelle `shift_requirements` | Migration `0010` |
| `replace_shift_requirements()` in `app.py` | samt der drei i18n-Schlüssel `requirements_length`, `requirements_must_be_int`, `requirements_must_not_be_negative` |
| `requirements` in `serialize_shift_type()` und `load_shift_types_for_scheduling()` | die Schichtart ist nur noch Vorlage: Name, Zeiten, Farbe |
| `requirements` im Rumpf von `POST`/`PUT /shift-types` | wird stillschweigend ignoriert statt abgelehnt — siehe §4 |
| `requirements` im Payload von `ShiftTypes.jsx` | seit Etappe 4 nur noch mitgeschickt, damit der Bestand nicht auf 0 fällt; ohne Tabelle entfällt der Grund |

## 3. Was bleibt, und warum

**`build_slots()` in `scheduler.py` bleibt.** Sie liest kein `shift_requirements` aus der
Datenbank, sondern erwartet die Zahlen im übergebenen `shift_types`-Dict. Zwei Aufrufer bleiben:

- `benchmark.py`, wo sie die Vergleichsbasis ist, an der die Umstellung aus Etappe 4 gemessen
  wurde;
- die 23 Tests in `test_scheduler.py`, die Rückwärtskompatibilitätsgarantie des Projekts.

Sie steht damit auf keinem Produktionspfad mehr, und **genau das gehört in ihren Docstring** —
sonst sucht die nächste Sitzung, wer sie aufruft.

**Migration `0007` bleibt unangetastet.** Sie hat einmal gegen echte Daten abgeleitet und ist
Geschichte. Auf einer frischen Datenbank läuft sie in der Reihenfolge `0001` → `0007` → `0010`
weiterhin durch: `0001` legt die Tabelle an, `0007` findet sie (leer, also leitet sie nichts
ab), `0010` entfernt sie.

## 4. Warum `requirements` im Rumpf ignoriert und nicht abgelehnt wird

Ein `POST /shift-types` mit `requirements` würde nach dieser Etappe einen Schlüssel enthalten,
den niemand mehr kennt. Ihn mit `400` abzulehnen wäre die strengere Lesart — aber es bräche
jeden Aufrufer, der noch die alte Form schickt, ohne dass er etwas falsch macht. Der Wert wird
schlicht nicht gelesen. Dieselbe Haltung wie bei allen anderen unbekannten Feldern im Projekt.

## 5. Die Migration

**`0010_drop_shift_requirements`**, als `.py`-Migration.

`up()` entfernt die Tabelle. `down()` legt sie wieder an — **leer**. Die Daten sind fort, und
das ist bei einem `DROP` nicht anders zu haben; der Docstring sagt es ausdrücklich, statt es
den Leser herausfinden zu lassen. Der Rundlauf `up → down → up` funktioniert damit, und das ist
die Anforderung aus Fallstrick 3.

Die Tabellendefinition in `down()` wird aus `0001_baseline.py` übernommen. Eine zweite Fassung
derselben Definition ist unschön, aber die Alternative — `0001` importieren — koppelt zwei
Migrationen aneinander, was schlimmer wäre: eine Migration muss lesbar bleiben, ohne dass man
ihre Vorgänger daneben legt.

## 6. Die Tests, die nachziehen müssen

**Die fest verdrahtete Tabellenliste in `test_migrations.py`** (Fallstrick 5: nicht in eine
Ableitung zurückverwandeln). `shift_requirements` bleibt in `BASELINE_TABELLEN` — nach `0001`
gibt es sie ja — und muss aus der Menge nach allen Migrationen herausgenommen werden.

**`test_ableitung_laesst_bestehende_baender_unangetastet`** legt seine Testdaten heute an,
nachdem alle Migrationen gelaufen sind, und schreibt dabei in `shift_requirements`. Nach `0010`
gibt es die Tabelle dort nicht mehr. Die Reihenfolge wird umgedreht: erst bis `0007`
zurückrollen, dann die Daten anlegen, dann wieder vorwärts. Das ist ohnehin die
wahrheitsgetreuere Anordnung — die Aussage des Tests ist „Altbestand liegt vor, wenn `0007`
läuft".

Die beiden übrigen `0007`-Tests bauen sich ein **synthetisches** Migrationsverzeichnis, das bei
`0006` endet. Sie sehen `0010` nie und bleiben unberührt.

## 7. Tests

| Ebene | Was |
|---|---|
| `test_migrations.py` | Rundlauf `0010` up → down → up; die Tabelle ist nach allen Migrationen weg und nach `0001` allein noch da |
| `test_migrations_postgres.py` | Postgres-Gegenstück zum Rundlauf |
| API | `POST /shift-types` liefert kein `requirements` mehr; ein Rumpf **mit** `requirements` wird angenommen und ignoriert, nicht abgelehnt |
| Frontend (Vitest) | Der bestehende `ShiftTypes`-Test deckt es ab — er prüft schon, dass keine Bedarfszahlen erscheinen |
| `test_scheduler.py` | Unverändert. `build_slots()` wird nicht angefasst |

## 8. Bewusst nicht dabei

- **`build_slots()` entfernen** — siehe §3
- **Migration `0007` anpassen** — sie ist Geschichte und läuft weiterhin durch
- **`requirements` im Rumpf ablehnen** — siehe §4
- Eine Datenrettung für die verschwindende Tabelle. Die Daten wurden in Migration `0007` in
  `coverage_requirements` überführt; das war ihr Zweck

## 9. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| Ein Aufrufer schickt weiter `requirements` und wundert sich | Wird ignoriert statt abgelehnt (§4); die Oberfläche schickt es nach dieser Etappe nicht mehr |
| `0007` läuft auf einer frischen Datenbank nicht mehr durch | Reihenfolge geprüft (§3); der Rundlauftest deckt es ab |
| Der Rollback von `0010` liefert eine leere Tabelle und jemand hält sie für vollständig | Steht im Docstring der Migration |
