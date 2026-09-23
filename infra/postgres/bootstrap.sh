#!/bin/sh
# Apply infra/postgres/sql/bootstrap.sql (ADR 0002) against a PostgreSQL server.
#
# Usage: infra/postgres/bootstrap.sh
# Connection uses the standard libpq variables (PGHOST, PGPORT, PGUSER, PGPASSWORD)
# of a superuser. Role and database names are configurable, passwords are required:
#   MHVP_DB_NAME            default mhvp
#   MHVP_DB_MIGRATOR_ROLE   default mhvp_migrator
#   MHVP_DB_APP_ROLE        default mhvp_app
#   MHVP_DB_MIGRATOR_PASSWORD, MHVP_DB_APP_PASSWORD   required, no defaults
set -eu

: "${MHVP_DB_MIGRATOR_PASSWORD:?MHVP_DB_MIGRATOR_PASSWORD must be set}"
: "${MHVP_DB_APP_PASSWORD:?MHVP_DB_APP_PASSWORD must be set}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SQL_FILE="${MHVP_BOOTSTRAP_SQL:-$SCRIPT_DIR/sql/bootstrap.sql}"

psql -X -q -v ON_ERROR_STOP=1 --dbname "${PGDATABASE:-postgres}" \
  -v db="${MHVP_DB_NAME:-mhvp}" \
  -v migrator_role="${MHVP_DB_MIGRATOR_ROLE:-mhvp_migrator}" \
  -v migrator_pw="$MHVP_DB_MIGRATOR_PASSWORD" \
  -v app_role="${MHVP_DB_APP_ROLE:-mhvp_app}" \
  -v app_pw="$MHVP_DB_APP_PASSWORD" \
  -f "$SQL_FILE"

echo "mhvp bootstrap applied to database ${MHVP_DB_NAME:-mhvp}"
