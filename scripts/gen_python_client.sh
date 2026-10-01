#!/usr/bin/env sh
# Generates the optional Python client (S12-07) from apps/api/openapi.json.
# Output: packages/api-client-py (not checked in, see .gitignore).
# Generator: openapi-python-client, pinned below, run via uvx (no change to the API lockfile).
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SPEC="${OPENAPI_SPEC:-$ROOT/apps/api/openapi.json}"
OUT="${OUT_DIR:-$ROOT/packages/api-client-py}"
GEN_VERSION="${OPENAPI_PYTHON_CLIENT_VERSION:-0.29.1}"

usage() {
  echo "Usage: $0 [--help]"
  echo "Generates the Python client from \$OPENAPI_SPEC (default apps/api/openapi.json)"
  echo "into \$OUT_DIR (default packages/api-client-py). Needs uv and network for first run."
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

[ -f "$SPEC" ] || { echo "OpenAPI spec not found: $SPEC (run make openapi)" >&2; exit 2; }
command -v uvx >/dev/null 2>&1 || { echo "uvx not found, install uv first" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/config.yml" <<CFG
project_name_override: mhvp-api-client
package_name_override: mhvp_api_client
CFG

# Regenerate cleanly (the output is not checked in, docs: docs/integrations/python-client.md).
rm -rf "$OUT"
mkdir -p "$(dirname "$OUT")"
( cd "$TMP" && uvx --from "openapi-python-client==$GEN_VERSION" openapi-python-client generate \
    --path "$SPEC" --config "$TMP/config.yml" --meta uv --output-path "$OUT" --overwrite )
echo "Python client written to $OUT"
