# Design: Etappe 6b — Der Anmeldeweg

**Datum:** 2026-08-23
**Projekt:** scheduling-tool-main (Schichtplan-Tool)
**Status:** umgesetzt

---

## 1. Ziel

Das zweite Bündel aus den zurückgestellten Befunden. Beide Einträge betreffen die Drosselung am
Anmeldeweg, und beide beschreiben **einen Weg an ihr vorbei**:

| Befund | Woher |
|---|---|
| `password_not_set_yet`-Zweig in `login()` zählt keine Versuche | Review Etappe 0 |
| `is_locked_out`/`record_attempt` sind check-then-act ohne Zeilensperre | Review Etappe 0 |

Dazu der eine Testschuld-Eintrag, der in dieselbe Datei gehört: die Drosselungstests verdrahten
`10/9/11` fest, statt `security.MAX_FAILED_ATTEMPTS` zu benutzen.

**Vorher geprüft, ob die Befunde noch stimmen** — in Etappe 6a war einer längst behoben. Hier
stimmten beide.

## 2. Der eingeladene Zugang war kostenlos

Ein per Einladung angelegtes Konto hat noch kein Passwort. `login()` sagt das ausdrücklich, mit
einem 403 statt der einheitlichen 401 — eine **bewusste** Entscheidung: die Einladung ging in das
Postfach dieser Person, und „falsches Passwort" hilft niemandem, der nie eines gesetzt hat.

Diese Antwort verrät aber zugleich, dass es den Benutzernamen gibt — anders als die identische
Meldung auf jedem anderen Pfad. **Und der Zweig kehrte zurück, bevor irgendetwas gezählt wurde.**
Unbegrenzt und ungezählt: eine Namensliste zum Nulltarif.

Die Meldung bleibt — sie ist die richtige Abwägung, und sie zurückzunehmen hieße, einen
eingeladenen Menschen im Regen stehen zu lassen, um einen Angreifer zu ärgern, der die Liste auch
anders bekommt. **Der Versuch wird jetzt gezählt wie jeder andere**, damit der Zweig zusammen mit
allem anderen ausläuft.

Das restliche Orakel bleibt bestehen und ist damit eine dokumentierte Entscheidung, keine Lücke,
die niemand gesehen hat.

## 3. Prüfen und Zählen waren zwei Schritte

`is_locked_out()` liest einen Zähler, den `record_attempt()` einen Augenblick später erhöht.
Klassisches check-then-act.

**Was das kostet:** N gleichzeitige Anfragen lesen alle denselben Stand unterhalb der Grenze und
kommen alle durch. Aus zehn Versuchen je Viertelstunde werden so viele, wie ein Angreifer
Verbindungen aufmacht. Die Drosselung ist dann keine Grenze mehr, sondern eine Empfehlung.

**Die Lösung stand schon im Projekt.** Der Migrations-Runner serialisiert zwei gleichzeitige
Gunicorn-Worker über einen Postgres-Advisory-Lock (`_migration_lock()`), samt Nebenläufigkeitstest
mit zwei Threads. `security.attempt_guard()` folgt demselben Muster:

- **Je Benutzername, nicht global.** Ein globaler Lock stellt jede Anmeldung im Haus hinter jede
  andere. Eigene Gegenprobe — sie wäre bei einem globalen Lock rot
- **Zwei-Zahlen-Form** (`pg_advisory_lock(class, key)`) statt der Einzahl-Form, die der
  Migrations-Runner benutzt. Postgres führt beide in getrennten Räumen; damit ist eine Kollision
  ausgeschlossen, statt sich darauf zu verlassen, dass zwei `crc32`-Werte verschieden ausfallen
- **Sitzungsgebunden, nicht transaktionsgebunden.** Der Sperrpfad antwortet mit 429, ohne zu
  committen; ein `xact`-Lock hinge dann bis zum Teardown der Anfrage. Die Freigabe steht im
  `finally` und hängt nicht davon ab, ob der Aufrufer committet

**Bewusst asymmetrisch: kein Lock auf SQLite.** Dieselbe Abwägung, die der Migrations-Runner
notiert — SQLite kommt hier nur lokal und nur als einzelner Prozess vor, die Race ist dort nicht
erreichbar, und ein Lock ohne erreichbare Race wäre ungetesteter Code auf dem Pfad, den jeder
Entwickler täglich benutzt.

## 4. Tests

| Ebene | Was |
|---|---|
| API (SQLite) | Die Meldung für den eingeladenen Zugang **bleibt** (Gegenprobe zuerst) |
| API (SQLite) | Nach dem Kontingent antwortet auch dieser Zweig mit 429 |
| API (SQLite) | Die Sperre gilt weiterhin je Benutzername, auch auf diesem Zweig |
| Postgres (CI) | Zwei Threads mit eigenen Sitzungen: genau **einer** kommt an der Sperre vorbei |
| Postgres (CI) | Zwei verschiedene Benutzernamen halten sich **nicht** gegenseitig auf |

**Die Race wird nachgebaut, nicht behauptet.** Zwei Threads mit je eigener Verbindung — also je
eigener Postgres-Sitzung, näher am Mehrprozessfall als nebenläufiger Python-Code —, und eine halbe
Sekunde zwischen Lesen und Schreiben, damit sie jedes Mal eintritt statt gelegentlich. Ein flakiger
Nebenläufigkeitstest ist schlimmer als keiner.

Die festen `10/9/11` in den Bestandstests sind durch `security.MAX_FAILED_ATTEMPTS` ersetzt. Ein
Test, der eine Konstante abschreibt, prüft ab der nächsten Änderung etwas anderes als das Programm
tut.

## 5. Bewusst nicht dabei

- **Die Meldung für eingeladene Konten vereinheitlichen.** Sie ist eine dokumentierte Abwägung
  zugunsten des eingeladenen Menschen; das Orakel ist der bekannte Preis
- **Eine IP-Komponente in der Drosselung.** Sie trifft ein Büro hinter einem gemeinsamen Anschluss
  vollständig und einen Angreifer mit wechselnden Adressen gar nicht
- **Ein Lock auf SQLite** (§3)
- **Exponentielles Zurückweichen statt eines festen Fensters.** Reizvoll, aber es macht die
  Meldung „in fünfzehn Minuten wieder" zu einer Unwahrheit, und die Meldung ist das, woran ein
  ausgesperrter Mensch sich hält
