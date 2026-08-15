-- Anmeldeversuche, um Passwortraten auszubremsen.
--
-- In der Datenbank statt im Arbeitsspeicher: der Zaehler muss einen Neustart
-- ueberleben und ueber mehrere Gunicorn-Worker hinweg derselbe sein. Das ist
-- ausserdem der erste Baustein des Audit-Logs aus Etappe 5.
--
-- attempted_at ist TEXT im ISO-Format, nicht TIMESTAMP: so laesst es sich in
-- SQLite und Postgres identisch mit einem in Python gerechneten Grenzwert
-- vergleichen. password_invitations.expires_at macht es genauso.
CREATE TABLE IF NOT EXISTS login_attempts(
    id {auto_id},
    identifier TEXT NOT NULL,
    ip TEXT NOT NULL,
    succeeded INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_login_attempts_lookup
    ON login_attempts(identifier, attempted_at)
