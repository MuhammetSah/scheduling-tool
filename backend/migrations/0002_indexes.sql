-- shift_assignments wird bei jeder Warnungspruefung nach (date, employee_id)
-- durchsucht (constraint_warnings in app.py) und beim Laden eines Monats nach
-- schedule_id. Beides ohne Index.
CREATE INDEX IF NOT EXISTS ix_assignments_date_employee
    ON shift_assignments(date, employee_id);

CREATE INDEX IF NOT EXISTS ix_assignments_schedule
    ON shift_assignments(schedule_id);

CREATE INDEX IF NOT EXISTS ix_absences_date
    ON employee_absences(date);

-- Ein Platz ist durch (Plan, Datum, Schichtart, Index) eindeutig bestimmt.
-- Bisher hielt nur die Anwendungslogik das ein.
--
-- Achtung Produktion: existieren bereits doppelte Plaetze, schlaegt dieser
-- UNIQUE-Index beim Anlegen fehl. Vor dem Deploy pruefen mit:
--   SELECT schedule_id, date, shift_type_id, slot_index, COUNT(*)
--   FROM shift_assignments GROUP BY 1,2,3,4 HAVING COUNT(*) > 1;
-- und Duplikate von Hand bereinigen.
CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_slot
    ON shift_assignments(schedule_id, date, shift_type_id, slot_index)
