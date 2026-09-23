#!/bin/sh
# Executed once by the official postgres image entrypoint on an empty data directory
# (/docker-entrypoint-initdb.d). Delegates to the idempotent bootstrap script.
set -eu
export PGUSER="$POSTGRES_USER"
export PGDATABASE=postgres
unset PGHOST
MHVP_BOOTSTRAP_SQL=/opt/mhvp/postgres/sql/bootstrap.sql sh /opt/mhvp/postgres/bootstrap.sh
