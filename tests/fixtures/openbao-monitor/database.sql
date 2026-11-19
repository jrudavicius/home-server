-- Run only on the example's dedicated PostgreSQL instance.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitor_reader') THEN
    CREATE ROLE monitor_reader NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bao_issuer') THEN
    CREATE ROLE bao_issuer LOGIN CREATEROLE;
  END IF;
END
$$;
ALTER ROLE bao_issuer SET createrole_self_grant = 'inherit';
REVOKE ALL ON DATABASE telemetry FROM PUBLIC;
GRANT CONNECT ON DATABASE telemetry TO monitor_reader, bao_issuer;
GRANT monitor_reader TO bao_issuer WITH ADMIN OPTION;
CREATE SCHEMA IF NOT EXISTS metrics;
CREATE TABLE IF NOT EXISTS metrics.heartbeat (id integer PRIMARY KEY);
INSERT INTO metrics.heartbeat VALUES (1) ON CONFLICT DO NOTHING;
GRANT USAGE ON SCHEMA metrics TO monitor_reader;
GRANT SELECT ON metrics.heartbeat TO monitor_reader;
