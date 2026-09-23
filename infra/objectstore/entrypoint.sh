#!/bin/sh
# Start SeaweedFS (S3 API on 8333) with S3 identities generated from the environment.
# Credentials never live in the repository: they come from MHVP_S3_ACCESS_KEY_ID /
# MHVP_S3_SECRET_ACCESS_KEY and are written to a tmpfs file at container start.
#
# Flags verified against seaweedfs tag 4.47 (commit c5073360007d28385a33426a42ac3e4ec504c5a3):
#   https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.47/docker/entrypoint.sh
#     ("server" case adds -dir=/data -master.volumeSizeLimitMB=1024, drops root via su-exec)
#   https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.47/weed/command/server.go
#     (-s3, -s3.config, -ip, -ip.bind, -dir)
#   https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.47/docker/compose/s3.json
#     (identities JSON format)
#   https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.47/weed/s3api/s3api_server.go
#     (GET /healthz on the S3 port)
set -eu

: "${MHVP_S3_ACCESS_KEY_ID:?MHVP_S3_ACCESS_KEY_ID must be set}"
: "${MHVP_S3_SECRET_ACCESS_KEY:?MHVP_S3_SECRET_ACCESS_KEY must be set}"

# Reject characters that would break the generated JSON.
case "$MHVP_S3_ACCESS_KEY_ID$MHVP_S3_SECRET_ACCESS_KEY" in
  *'"'*|*'\'*) echo "S3 credentials must not contain quotes or backslashes" >&2; exit 1 ;;
esac

CONFIG_DIR="${MHVP_S3_CONFIG_DIR:-/tmp/mhvp-s3}"
mkdir -p "$CONFIG_DIR"
umask 077
cat > "$CONFIG_DIR/s3.json" <<JSON
{
  "identities": [
    {
      "name": "mhvp",
      "credentials": [
        {"accessKey": "$MHVP_S3_ACCESS_KEY_ID", "secretKey": "$MHVP_S3_SECRET_ACCESS_KEY"}
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
JSON

# No anonymous identity: every request must be signed.
exec /entrypoint.sh server \
  -ip="${MHVP_S3_ADVERTISE_HOST:-objectstore}" \
  -ip.bind=0.0.0.0 \
  -s3 \
  -s3.port=8333 \
  -s3.config="$CONFIG_DIR/s3.json" \
  "$@"
