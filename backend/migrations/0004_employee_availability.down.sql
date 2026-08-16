-- Nimmt nur die Tabelle zurueck, nicht die Spalte employees.availability_mode.
--
-- SQLite kann DROP COLUMN erst ab Version 3.35 und selbst dann nicht in
-- jeder Situation (z.B. auf Spalten mit CHECK-Constraint oder als Teil eines
-- Fremdschluessels). Eine zurueckgebliebene Spalte mit sinnvollem Standard
-- ('anytime', siehe 0004_employee_availability.sql) ist harmlos - jeder
-- Bestandsdatensatz bleibt genauso gueltig wie vor der Migration. Ein
-- Rollback, der an einem fehlenden DROP COLUMN scheitert, waere dagegen ein
-- Rollback, der nicht funktioniert - schlimmer als eine harmlose Spalte, die
-- liegen bleibt.
DROP INDEX IF EXISTS ix_availability_employee;
DROP TABLE IF EXISTS employee_availability
