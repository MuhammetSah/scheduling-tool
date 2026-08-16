-- Arbeitszeitfenster: "Anna kann montags 08:00-14:00".
--
-- Mehrere Zeilen pro (employee_id, weekday) sind erlaubt und beschreiben
-- einen geteilten Dienst. Eine Schicht muss vollstaendig in EIN Fenster
-- passen, nicht in die Vereinigung mehrerer.
--
-- end_time <= start_time bedeutet Ueberschreitung nach Mitternacht, wie
-- ueberall sonst im Projekt (siehe scheduler.shift_duration_minutes).
--
-- valid_from/valid_until sind ISO-Daten oder NULL fuer unbegrenzt, beide
-- Grenzen einschliesslich. Damit laesst sich "ab September gilt etwas
-- anderes" abbilden, ohne die alte Zeile zu verlieren.
CREATE TABLE IF NOT EXISTS employee_availability(
    id {auto_id},
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    valid_from TEXT,
    valid_until TEXT
);

CREATE INDEX IF NOT EXISTS ix_availability_employee
    ON employee_availability(employee_id, weekday);

-- 'anytime' = wie bisher, keine Uhrzeit-Einschraenkung. 'windows' = nur
-- innerhalb der Fenster oben. Der Schalter ist absichtlich explizit: ohne
-- ihn waere "hat keine Fenster" mehrdeutig, und jeder Bestandsdatensatz
-- muesste geraten werden. Der Standard haelt alle vorhandenen Mitarbeiter
-- unveraendert gueltig.
ALTER TABLE employees ADD COLUMN availability_mode TEXT NOT NULL DEFAULT 'anytime'
