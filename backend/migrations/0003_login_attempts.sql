-- Anmeldeversuche, um Passwortraten auszubremsen.
--
-- In der Datenbank statt im Arbeitsspeicher: der Zaehler muss einen Neustart
-- ueberleben und ueber mehrere Gunicorn-Worker hinweg derselbe sein. Das ist
-- ausserdem der erste Baustein des Audit-Logs aus Etappe 5.
--
-- attempted_at ist TEXT im ISO-Format mit Offset (z.B. ...+00:00), nicht
-- TIMESTAMP: is_locked_out() in security.py vergleicht ihn direkt in SQL
-- (attempted_at >= ?) gegen einen in Python berechneten Grenzwert-String -
-- das muss auf SQLite und Postgres als reiner Zeichenkettenvergleich
-- identisch funktionieren, deshalb TEXT statt TIMESTAMP.
--
-- password_invitations.expires_at macht es NICHT genauso, auch wenn der
-- Name es nahelegt: das ist eine echte TIMESTAMP-Spalte und traegt einen
-- naiven (offset-losen) UTC-Wert statt eines aware Werts wie hier -
-- absichtlich, siehe der Kommentar bei issue_invitation() in app.py. Der
-- Vergleich dafuer laeuft ausserdem in Python nach dem Lesen
-- (as_datetime()/load_invitation() in app.py), nicht als SQL-String-
-- Vergleich wie bei attempted_at oben.
CREATE TABLE IF NOT EXISTS login_attempts(
    id {auto_id},
    identifier TEXT NOT NULL,
    ip TEXT NOT NULL,
    succeeded INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_login_attempts_lookup
    ON login_attempts(identifier, attempted_at)
