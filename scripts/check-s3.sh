#!/usr/bin/env bash
# Object storage check (ADR 0005, IONOS S3 Object Storage): connectivity, bucket existence and
# a put/get/delete round trip with the MHVP_S3_* variables the API reads
# (mhvp.core.config.Settings, prefix MHVP_). Secrets are never printed.
#
# Usage:
#   scripts/check-s3.sh                      variables from the current environment
#   scripts/check-s3.sh --env-file .env.prod variables from a dotenv file (not exported)
#   MHVP_S3_BUCKET=mhvp-backup scripts/check-s3.sh --env-file .env.prod   check another bucket
#   scripts/check-s3.sh --no-write           skip the round trip (read only keys)
# Exit codes: 0 all checks passed, 1 a check failed, 2 usage or missing variables.
#
# boto3 comes from the api project (uv run --project apps/api); without uv the script falls
# back to the python3 on PATH, which then must have boto3 installed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=""
WRITE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) [[ $# -ge 2 ]] || { echo "check-s3: --env-file needs a path" >&2; exit 2; }; ENV_FILE="$2"; shift 2 ;;
    --no-write) WRITE=0; shift ;;
    -h|--help) sed -n '2,14p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "check-s3: unknown argument $1" >&2; exit 2 ;;
  esac
done

if [[ -n "$ENV_FILE" ]]; then
  [[ -r "$ENV_FILE" ]] || { echo "check-s3: cannot read $ENV_FILE" >&2; exit 2; }
  # Load only the S3 variables; values already set in the environment win (allows checking
  # the backup bucket with MHVP_S3_BUCKET=... against the credentials of the file).
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?(MHVP_S3_[A-Z_]+)=(.*)$ ]] || continue
    name="${BASH_REMATCH[2]}"; value="${BASH_REMATCH[3]}"
    value="${value%%[[:space:]]#*}"          # trailing comment
    value="${value%"${value##*[![:space:]]}"}" # trailing whitespace
    if [[ "$value" =~ ^\"(.*)\"$ || "$value" =~ ^\'(.*)\'$ ]]; then value="${BASH_REMATCH[1]}"; fi
    [[ -n "${!name:-}" ]] || export "$name=$value"
  done < "$ENV_FILE"
fi

missing=0
for name in MHVP_S3_ENDPOINT_URL MHVP_S3_ACCESS_KEY_ID MHVP_S3_SECRET_ACCESS_KEY; do
  [[ -n "${!name:-}" ]] || { echo "check-s3: $name is not set" >&2; missing=1; }
done
[[ "$missing" -eq 0 ]] || exit 2
case "${MHVP_S3_ENDPOINT_URL}" in
  *"["*"]"*) echo "check-s3: MHVP_S3_ENDPOINT_URL still contains a placeholder" >&2; exit 2 ;;
esac
export MHVP_S3_REGION="${MHVP_S3_REGION:-us-east-1}"
export MHVP_S3_BUCKET="${MHVP_S3_BUCKET:-mhvp}"
export MHVP_CHECK_S3_WRITE="$WRITE"

if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/apps/api/pyproject.toml" ]]; then
  PY=(uv run --quiet --project "$ROOT/apps/api" python)
else
  PY=(python3)
fi

exec "${PY[@]}" - <<'PYEOF'
import os
import sys
import time
import uuid
from urllib.parse import urlsplit

try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    print("check-s3: boto3 is not installed (run via uv or pip install boto3)", file=sys.stderr)
    sys.exit(2)

endpoint = os.environ["MHVP_S3_ENDPOINT_URL"]
region = os.environ["MHVP_S3_REGION"]
bucket = os.environ["MHVP_S3_BUCKET"]
access_key = os.environ["MHVP_S3_ACCESS_KEY_ID"]
secret_key = os.environ["MHVP_S3_SECRET_ACCESS_KEY"]
write = os.environ.get("MHVP_CHECK_S3_WRITE", "1") == "1"


def masked(value: str) -> str:
    return value[:4] + "..." if len(value) > 6 else "***"


parts = urlsplit(endpoint)
if parts.scheme not in ("http", "https") or not parts.netloc:
    print(f"FAIL endpoint: MHVP_S3_ENDPOINT_URL must be a http(s) URL", file=sys.stderr)
    sys.exit(2)
print(f"check-s3: endpoint {parts.scheme}://{parts.netloc}  region {region}  bucket {bucket}")
print(f"check-s3: access key {masked(access_key)}  secret key set ({len(secret_key)} chars)")
if parts.scheme != "https" and parts.hostname not in ("127.0.0.1", "localhost", "objectstore"):
    print("WARN endpoint without TLS; production must use https")

# Same client options as mhvp.core.storage.create_s3_client.
client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=BotoConfig(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        connect_timeout=5,
        read_timeout=10,
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)

failed = False


def step(label: str, fn):
    global failed
    started = time.monotonic()
    try:
        result = fn()
    except ClientError as exc:
        err = exc.response.get("Error", {})
        print(f"FAIL {label}: {err.get('Code', '?')} {err.get('Message', '')}".rstrip())
        failed = True
        return None
    except BotoCoreError as exc:
        print(f"FAIL {label}: {exc.__class__.__name__}: {exc}")
        failed = True
        return None
    ms = int((time.monotonic() - started) * 1000)
    print(f"ok   {label} ({ms} ms){': ' + result if isinstance(result, str) else ''}")
    return result if result is not None else True


# 1. Connectivity and credentials: list_buckets needs a valid signature.
buckets = step("connect and sign (list buckets)", lambda: [b["Name"] for b in client.list_buckets().get("Buckets", [])])
if buckets is None:
    sys.exit(1)

# 2. Bucket exists and is reachable with these keys.
if step(f"bucket {bucket} exists (head bucket)", lambda: client.head_bucket(Bucket=bucket)) is None:
    if bucket not in (buckets or []):
        print(f"     bucket {bucket} is not in the bucket list of this key; create it in the IONOS console")
    sys.exit(1)

# 3. Public access must be blocked: an anonymous head request has to fail.
def anonymous_head():
    from botocore import UNSIGNED
    anon = boto3.client("s3", endpoint_url=endpoint, region_name=region,
                        config=BotoConfig(signature_version=UNSIGNED, s3={"addressing_style": "path"},
                                          connect_timeout=5, read_timeout=10))
    try:
        anon.list_objects_v2(Bucket=bucket, MaxKeys=1)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in ("AccessDenied", "403", "InvalidAccessKeyId", "NoSuchBucket", "404"):
            return "anonymous access refused"
        raise
    raise RuntimeError("bucket answers anonymous requests")

try:
    step("bucket is private (anonymous list refused)", anonymous_head)
except RuntimeError as exc:
    print(f"FAIL bucket is private: {exc}")
    failed = True

# 4. Round trip with a unique key under a check prefix; always cleaned up.
if write:
    key = f"_mhvp-check/{uuid.uuid4()}.txt"
    payload = f"mhvp check-s3 {time.time():.0f}".encode()

    def put():
        client.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="text/plain")

    def get():
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if body != payload:
            raise RuntimeError("content mismatch")
        return f"{len(body)} bytes"

    def delete():
        client.delete_object(Bucket=bucket, Key=key)
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code", "")) in ("404", "NoSuchKey", "NotFound"):
                return "object gone"
            raise
        raise RuntimeError("object still present after delete")

    if step("put object", put) is not None:
        try:
            step("get object", get)
        except RuntimeError as exc:
            print(f"FAIL get object: {exc}"); failed = True
        try:
            step("delete object", delete)
        except RuntimeError as exc:
            print(f"FAIL delete object: {exc}"); failed = True
else:
    print("skip put/get/delete (--no-write)")

print("check-s3: " + ("FAILED" if failed else "all checks passed"))
sys.exit(1 if failed else 0)
PYEOF
