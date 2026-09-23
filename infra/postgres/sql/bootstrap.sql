-- MHVP database bootstrap (ADR 0002). Runs as a PostgreSQL superuser.
--
-- Idempotent: safe to run on every container start, in CI and locally.
-- Required psql variables:
--   db            database name            (e.g. mhvp)
--   migrator_role role owning schema/tables (e.g. mhvp_migrator)
--   migrator_pw   password of migrator_role
--   app_role      runtime role of api/worker (e.g. mhvp_app)
--   app_pw        password of app_role
--
-- Invariants established here (verified by apps/api/tests/integration/test_db_roles.py):
--   * app_role is LOGIN, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE, NOINHERIT
--     and is never the owner of schema objects, so row level security cannot be bypassed.
--   * migrator_role owns the database schema and all tables; it is NOSUPERUSER and
--     NOBYPASSRLS. Tenant tables use FORCE ROW LEVEL SECURITY, so the owner is bound too.
--   * Extensions that need superuser rights (vector) are created here, not in migrations.

\set ON_ERROR_STOP on
SET client_min_messages = warning;

-- Roles ---------------------------------------------------------------------------------

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT NOREPLICATION',
  :'migrator_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_role') \gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT NOREPLICATION',
  :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role') \gexec

-- Re-assert attributes on every run so a manual change cannot silently weaken isolation.
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT NOREPLICATION PASSWORD %L',
  :'migrator_role', :'migrator_pw') \gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT NOREPLICATION PASSWORD %L',
  :'app_role', :'app_pw') \gexec

-- The runtime role must not be member of any role: NOINHERIT does not prevent SET ROLE
-- into an owning or privileged role (direct or indirect).
SELECT format('REVOKE %I FROM %I', r.rolname, u.rolname)
  FROM pg_auth_members m
  JOIN pg_roles r ON r.oid = m.roleid
  JOIN pg_roles u ON u.oid = m.member
 WHERE u.rolname = :'app_role' \gexec

-- Database ------------------------------------------------------------------------------

SELECT format('CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0', :'db', :'migrator_role', 'UTF8')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'db', :'migrator_role') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'app_role') \gexec
SELECT format('GRANT CONNECT, CREATE, TEMPORARY ON DATABASE %I TO %I', :'db', :'migrator_role') \gexec

\connect :db
SET client_min_messages = warning;

-- Extensions (Section 3.2: pgcrypto, pg_trgm, pgvector, btree_gist) ----------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS vector;

-- Schema privileges ---------------------------------------------------------------------

SELECT format('ALTER SCHEMA public OWNER TO %I', :'migrator_role') \gexec
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_role') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'migrator_role') \gexec

-- Objects created later by the migrator are usable, but not owned, by the runtime role.
-- Append-only tables (domain_event, audit_log) revoke UPDATE/DELETE in their own migration.
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
  :'migrator_role', :'app_role') \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
  :'migrator_role', :'app_role') \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO %I',
  :'migrator_role', :'app_role') \gexec
