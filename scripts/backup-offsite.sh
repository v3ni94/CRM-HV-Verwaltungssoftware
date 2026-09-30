#!/usr/bin/env bash
# Off-site copy of the backup (M9-02, operator decision 26.09.2026): the local backup artefacts
# of scripts/backup.sh (age encrypted database dump plus checksum), optional WAL archive
# segments and a copy of the documents from the primary IONOS bucket are encrypted with the
# public age key and uploaded to the operator's Hetzner S3 compatible Object Storage. The
# private age key stays with the operator, off the server (MASTER-PROMPT 3.5).
#
# Layout in the target bucket (BACKUP_S3_PREFIX, default "mhvp"):
#   <prefix>/runs/<STAMP>/db/<file>            dump and checksum of this run (already .age)
#   <prefix>/runs/<STAMP>/wal/<segment>.age    WAL segments new since the previous run
#   <prefix>/runs/<STAMP>/objects-manifest.json.age   list of the mirrored documents
#   <prefix>/runs/<STAMP>/status.json          run summary (no secrets, no personal data)
#   <prefix>/objects/<source key>.age          documents, encrypted per object, incremental,
#                                              never deleted by this script
# Retention (pruning by listing the runs/ prefix, GFS): keep BACKUP_OFFSITE_KEEP_DAILY (14)
# newest runs, BACKUP_OFFSITE_KEEP_WEEKLY (8) first runs of an ISO week, and
# BACKUP_OFFSITE_KEEP_MONTHLY (12) first runs of a month. Everything else under runs/ is deleted.
#
# Usage:
#   scripts/backup-offsite.sh [--stamp <STAMP>]     upload the run named by STAMP (default:
#                                                    newest mhvp-*.dump.age in BACKUP_DIR)
#   scripts/backup-offsite.sh --dry-run              connect, list, report; upload nothing
#   scripts/backup-offsite.sh --dry-run --list <file>  no S3 access at all: read a fake
#                                                    listing (one key per line) from <file>
#                                                    (or "-" for stdin) and print the pruning
#                                                    plan. For tests of the retention logic.
#   scripts/backup-offsite.sh --skip-objects         database and WAL only
#   scripts/backup-offsite.sh --wal-only             only new WAL segments (hourly, M9-06);
#                                                    status in BACKUP_DIR/offsite-wal-status
# Environment (infra/env.backup.example): BACKUP_DIR, BACKUP_S3_ENDPOINT_URL, BACKUP_S3_REGION,
#   BACKUP_S3_BUCKET, BACKUP_S3_ACCESS_KEY_ID, BACKUP_S3_SECRET_ACCESS_KEY,
#   BACKUP_AGE_PUBLIC_KEY (or BACKUP_AGE_RECIPIENT), optional BACKUP_WAL_DIR,
#   BACKUP_SOURCE_S3_* (primary IONOS bucket, read only key).
# Status: writes "$BACKUP_DIR/offsite-status" (one line "backup-offsite: status=ok|failed ...")
#   and prints the same line; read by scripts/healthcheck.sh. Exit code 0 only on full success,
#   1 on a failed step, 2 on usage or missing variables. A non zero exit lets the alarm of
#   scripts/backup.sh fire when this script is called from there.
# S3 access uses boto3 from the api project (uv run --project apps/api), like check-s3.sh;
# age must be installed on the server (docs/runbooks/server-setup.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP=""
DRY_RUN=0
LIST_FILE=""
SKIP_OBJECTS=0
WAL_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stamp) [[ $# -ge 2 ]] || { echo "backup-offsite: --stamp needs a value" >&2; exit 2; }; STAMP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --list) [[ $# -ge 2 ]] || { echo "backup-offsite: --list needs a file" >&2; exit 2; }; LIST_FILE="$2"; shift 2 ;;
    --skip-objects) SKIP_OBJECTS=1; shift ;;
    --wal-only) WAL_ONLY=1; shift ;;
    -h|--help) sed -n '2,36p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "backup-offsite: unknown argument $1" >&2; exit 2 ;;
  esac
done
if [[ -n "$LIST_FILE" && "$DRY_RUN" -ne 1 ]]; then
  echo "backup-offsite: --list is only allowed together with --dry-run" >&2; exit 2
fi

export BACKUP_AGE_PUBLIC_KEY="${BACKUP_AGE_PUBLIC_KEY:-${BACKUP_AGE_RECIPIENT:-}}"
export BACKUP_S3_REGION="${BACKUP_S3_REGION:-us-east-1}"
export BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-mhvp}"
export BACKUP_OFFSITE_KEEP_DAILY="${BACKUP_OFFSITE_KEEP_DAILY:-14}"
export BACKUP_OFFSITE_KEEP_WEEKLY="${BACKUP_OFFSITE_KEEP_WEEKLY:-8}"
export BACKUP_OFFSITE_KEEP_MONTHLY="${BACKUP_OFFSITE_KEEP_MONTHLY:-12}"
export MHVP_OFFSITE_STAMP="$STAMP" MHVP_OFFSITE_DRY_RUN="$DRY_RUN" MHVP_OFFSITE_LIST_FILE="$LIST_FILE"
export MHVP_OFFSITE_SKIP_OBJECTS="$SKIP_OBJECTS" MHVP_OFFSITE_WAL_ONLY="$WAL_ONLY"

if [[ -z "$LIST_FILE" ]]; then
  missing=0
  for name in BACKUP_DIR BACKUP_S3_ENDPOINT_URL BACKUP_S3_BUCKET BACKUP_S3_ACCESS_KEY_ID BACKUP_S3_SECRET_ACCESS_KEY BACKUP_AGE_PUBLIC_KEY; do
    [[ -n "${!name:-}" ]] || { echo "backup-offsite: $name is not set" >&2; missing=1; }
  done
  [[ "$missing" -eq 0 ]] || exit 2
  case "$BACKUP_S3_ENDPOINT_URL" in
    *"["*"]"*) echo "backup-offsite: BACKUP_S3_ENDPOINT_URL still contains a placeholder" >&2; exit 2 ;;
  esac
  if [[ "$BACKUP_AGE_PUBLIC_KEY" == AGE-SECRET-KEY-* ]]; then
    echo "backup-offsite: BACKUP_AGE_PUBLIC_KEY holds a private key; refused (3.5)" >&2; exit 2
  fi
  command -v age >/dev/null 2>&1 || { echo "backup-offsite: age is not installed" >&2; exit 2; }
fi

if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/apps/api/pyproject.toml" ]]; then
  PY=(uv run --quiet --project "$ROOT/apps/api" python)
else
  PY=(python3)
fi

exec "${PY[@]}" - <<'PYEOF'
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOG = "backup-offsite"
STAMP_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{6})Z$")


def log(msg: str) -> None:
    print(f"{LOG}: {msg}", flush=True)


def fail(msg: str, code: int = 1) -> None:
    print(f"{LOG}: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------------------------------------------------------------- retention (pure logic)
def run_stamps(keys: list[str], prefix: str) -> list[str]:
    """Distinct run stamps found under <prefix>/runs/ in a key listing."""
    base = f"{prefix}/runs/"
    stamps = set()
    for key in keys:
        if not key.startswith(base):
            continue
        stamp = key[len(base):].split("/", 1)[0]
        if STAMP_RE.match(stamp):
            stamps.add(stamp)
    return sorted(stamps)


def stamp_date(stamp: str) -> dt.date:
    m = STAMP_RE.match(stamp)
    assert m
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def prune_plan(stamps: list[str], daily: int, weekly: int, monthly: int) -> tuple[list[str], list[str]]:
    """GFS: keep the newest `daily` runs, the first run of the newest `weekly` ISO weeks and the
    first run of the newest `monthly` months. Returns (keep, delete), both sorted ascending."""
    ordered = sorted(set(stamps))
    keep: set[str] = set(ordered[-daily:] if daily > 0 else [])
    first_of_week: dict[tuple[int, int], str] = {}
    first_of_month: dict[tuple[int, int], str] = {}
    for stamp in ordered:  # ascending: the first run of a period wins
        d = stamp_date(stamp)
        iso = d.isocalendar()
        first_of_week.setdefault((iso[0], iso[1]), stamp)
        first_of_month.setdefault((d.year, d.month), stamp)
    keep.update(sorted(first_of_week.values())[-weekly:] if weekly > 0 else [])
    keep.update(sorted(first_of_month.values())[-monthly:] if monthly > 0 else [])
    delete = [s for s in ordered if s not in keep]
    return sorted(keep), delete


def env_int(name: str) -> int:
    try:
        value = int(os.environ.get(name, "0"))
    except ValueError:
        fail(f"{name} must be an integer", 2)
    if value < 0:
        fail(f"{name} must not be negative", 2)
    return value


KEEP_DAILY = env_int("BACKUP_OFFSITE_KEEP_DAILY")
KEEP_WEEKLY = env_int("BACKUP_OFFSITE_KEEP_WEEKLY")
KEEP_MONTHLY = env_int("BACKUP_OFFSITE_KEEP_MONTHLY")
PREFIX = os.environ["BACKUP_S3_PREFIX"].strip("/")
DRY_RUN = os.environ.get("MHVP_OFFSITE_DRY_RUN") == "1"
LIST_FILE = os.environ.get("MHVP_OFFSITE_LIST_FILE", "")

if LIST_FILE:
    text = sys.stdin.read() if LIST_FILE == "-" else Path(LIST_FILE).read_text()
    keys = [line.strip() for line in text.splitlines() if line.strip()]
    keep, delete = prune_plan(run_stamps(keys, PREFIX), KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY)
    log(f"plan from listing ({len(keys)} keys): keep daily {KEEP_DAILY}, weekly {KEEP_WEEKLY}, monthly {KEEP_MONTHLY}")
    for s in keep:
        print(f"keep   {PREFIX}/runs/{s}/")
    for s in delete:
        print(f"delete {PREFIX}/runs/{s}/")
    log(f"keep {len(keep)} runs, delete {len(delete)} runs")
    sys.exit(0)

# ---------------------------------------------------------------- S3 clients
try:
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    fail("boto3 is not installed (run via uv or pip install boto3)", 2)


def make_client(endpoint: str, region: str, key: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=10,
            read_timeout=120,
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


def masked(value: str) -> str:
    return value[:4] + "..." if len(value) > 6 else "***"


BACKUP_DIR = Path(os.environ["BACKUP_DIR"])
WAL_ONLY = os.environ.get("MHVP_OFFSITE_WAL_ONLY") == "1"
# The hourly WAL run (M9-06) has its own status file so that it never masks a missing daily run.
STATUS_FILE = BACKUP_DIR / ("offsite-wal-status" if WAL_ONLY else "offsite-status")
BUCKET = os.environ["BACKUP_S3_BUCKET"]
ENDPOINT = os.environ["BACKUP_S3_ENDPOINT_URL"]
RECIPIENT = os.environ["BACKUP_AGE_PUBLIC_KEY"]
SKIP_OBJECTS = os.environ.get("MHVP_OFFSITE_SKIP_OBJECTS") == "1"
WAL_DIR = os.environ.get("BACKUP_WAL_DIR", "").strip()
SRC_BUCKET = os.environ.get("BACKUP_SOURCE_S3_BUCKET", "").strip()
started = time.monotonic()
summary: dict = {"status": "failed", "uploaded": 0, "bytes": 0, "objects_new": 0, "objects_total": 0,
                 "wal": 0, "pruned": 0, "dry_run": DRY_RUN}


def write_status(status: str, detail: str = "") -> None:
    summary["status"] = status
    summary["stamp"] = summary.get("stamp", "")
    summary["at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary["seconds"] = int(time.monotonic() - started)
    parts = [f"{k}={summary[k]}" for k in ("status", "stamp", "at", "uploaded", "bytes", "objects_new",
                                             "objects_total", "wal", "pruned", "seconds", "dry_run")]
    if detail:
        parts.append(f"detail={detail.replace(' ', '_')}")
    line = f"{LOG}: " + " ".join(parts)
    print(line, flush=True)
    if not DRY_RUN:
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            tmp = STATUS_FILE.with_suffix(".part")
            tmp.write_text(line + "\n")
            tmp.replace(STATUS_FILE)
        except OSError as exc:
            print(f"{LOG}: cannot write status file: {exc}", file=sys.stderr)


def step_fail(msg: str) -> None:
    write_status("failed", msg)
    fail(msg)


log(f"target {ENDPOINT} bucket {BUCKET} prefix {PREFIX}/ region {os.environ['BACKUP_S3_REGION']}")
log(f"access key {masked(os.environ['BACKUP_S3_ACCESS_KEY_ID'])}  age recipient {RECIPIENT[:12]}...")
if not ENDPOINT.startswith("https://"):
    log("WARN endpoint without TLS; production must use https")

target = make_client(ENDPOINT, os.environ["BACKUP_S3_REGION"], os.environ["BACKUP_S3_ACCESS_KEY_ID"],
                     os.environ["BACKUP_S3_SECRET_ACCESS_KEY"])
try:
    target.head_bucket(Bucket=BUCKET)
except (ClientError, BotoCoreError) as exc:
    step_fail(f"target bucket {BUCKET} not reachable: {exc}")
log("ok   target bucket reachable")


# ---------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def age_encrypt(src: Path, dst: Path) -> None:
    subprocess.run(["age", "--recipient", RECIPIENT, "--output", str(dst), str(src)], check=True)


def list_keys(client, bucket: str, prefix: str) -> dict[str, int]:
    """key -> size for every object under prefix."""
    out: dict[str, int] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            out[obj["Key"]] = int(obj["Size"])
    return out


def upload_verified(path: Path, key: str, metadata: dict[str, str] | None = None) -> None:
    """Uploads and verifies by size (head_object) and sha256 stored as metadata. Multipart
    ETags are not comparable, so the checksum travels in metadata and the size is checked."""
    size = path.stat().st_size
    digest = sha256_file(path)
    meta = {"sha256": digest, **(metadata or {})}
    if DRY_RUN:
        log(f"dry  would upload {key} ({size} bytes)")
        return
    target.upload_file(str(path), BUCKET, key, ExtraArgs={"Metadata": meta})
    head = target.head_object(Bucket=BUCKET, Key=key)
    if int(head["ContentLength"]) != size:
        raise RuntimeError(f"size mismatch after upload of {key}: local {size}, remote {head['ContentLength']}")
    if head.get("Metadata", {}).get("sha256") != digest:
        raise RuntimeError(f"checksum metadata missing after upload of {key}")
    summary["uploaded"] += 1
    summary["bytes"] += size
    log(f"ok   uploaded {key} ({size} bytes, sha256 {digest[:12]}...)")


# ---------------------------------------------------------------- 1. run selection
stamp = os.environ.get("MHVP_OFFSITE_STAMP", "")
if not stamp:
    dumps = sorted(BACKUP_DIR.glob("mhvp-2*.dump.age"), key=lambda p: p.stat().st_mtime)
    if not dumps:
        step_fail(f"no encrypted dump (mhvp-*.dump.age) in {BACKUP_DIR}")
    stamp = dumps[-1].name[len("mhvp-"):-len(".dump.age")]
if not STAMP_RE.match(stamp):
    step_fail(f"stamp {stamp!r} is not of the form YYYYMMDDTHHMMSSZ", )
summary["stamp"] = stamp
run_prefix = f"{PREFIX}/runs/{stamp}"
db_files = sorted(p for p in BACKUP_DIR.glob(f"mhvp-*{stamp}*") if p.is_file())
if not any(p.name.endswith(".dump.age") for p in db_files):
    step_fail(f"run {stamp}: no encrypted dump found; unencrypted dumps are never copied off-site (3.5)")
for p in db_files:
    if p.name.endswith(".dump") or p.name.endswith(".tar"):
        step_fail(f"run {stamp}: {p.name} is unencrypted; refused")
log(f"run {stamp}: {len(db_files)} database file(s)")

work = Path(tempfile.mkdtemp(prefix="mhvp-offsite-"))
try:
    # ------------------------------------------------------------ 2. database artefacts
    if not WAL_ONLY:
        for p in db_files:
            upload_verified(p, f"{run_prefix}/db/{p.name}")

    # ------------------------------------------------------------ 3. WAL archive segments
    if WAL_DIR:
        wal_dir = Path(WAL_DIR)
        if not wal_dir.is_dir():
            step_fail(f"BACKUP_WAL_DIR {WAL_DIR} is not a directory")
        # A segment is uploaded once: existing keys under any run's wal/ are skipped.
        existing_wal = {k.rsplit("/", 1)[-1] for k in list_keys(target, BUCKET, f"{PREFIX}/runs/") if "/wal/" in k}
        segments = sorted(p for p in wal_dir.iterdir() if p.is_file() and not p.name.endswith(".partial"))
        for seg in segments:
            name = f"{seg.name}.age"
            if name in existing_wal:
                continue
            enc = work / name
            age_encrypt(seg, enc)
            upload_verified(enc, f"{run_prefix}/wal/{name}")
            enc.unlink()
            summary["wal"] += 1
        log(f"wal: {summary['wal']} new segment(s) of {len(segments)}")
    else:
        log("wal: BACKUP_WAL_DIR not set, skipped (WAL archiving not configured, see backup.md)")

    # ------------------------------------------------------------ 4. documents (bucket to bucket)
    manifest: dict = {"source_bucket": SRC_BUCKET, "objects": {}}
    if WAL_ONLY:
        log("objects: skipped (--wal-only)")
    elif SKIP_OBJECTS:
        log("objects: skipped (--skip-objects)")
    elif not SRC_BUCKET:
        log("objects: BACKUP_SOURCE_S3_BUCKET not set, skipped")
    else:
        src_missing = [n for n in ("BACKUP_SOURCE_S3_ENDPOINT_URL", "BACKUP_SOURCE_S3_ACCESS_KEY_ID",
                                   "BACKUP_SOURCE_S3_SECRET_ACCESS_KEY") if not os.environ.get(n)]
        if src_missing:
            step_fail("objects: missing " + ", ".join(src_missing))
        source = make_client(os.environ["BACKUP_SOURCE_S3_ENDPOINT_URL"],
                             os.environ.get("BACKUP_SOURCE_S3_REGION", "us-east-1"),
                             os.environ["BACKUP_SOURCE_S3_ACCESS_KEY_ID"],
                             os.environ["BACKUP_SOURCE_S3_SECRET_ACCESS_KEY"])
        src_keys = list_keys(source, SRC_BUCKET, "")
        mirror_prefix = f"{PREFIX}/objects/"
        mirrored = list_keys(target, BUCKET, mirror_prefix)
        # Mirrored objects carry the source ETag and size in metadata; re-copy on change.
        for key, size in sorted(src_keys.items()):
            if key.startswith("_mhvp-check/"):
                continue
            head = source.head_object(Bucket=SRC_BUCKET, Key=key)
            etag = head.get("ETag", "").strip('"')
            tkey = f"{mirror_prefix}{key}.age"
            manifest["objects"][key] = {"size": size, "etag": etag}
            if tkey in mirrored:
                try:
                    th = target.head_object(Bucket=BUCKET, Key=tkey)
                    tm = th.get("Metadata", {})
                    if tm.get("source-etag") == etag and tm.get("source-size") == str(size):
                        continue
                except ClientError:
                    pass
            plain = work / "object.bin"
            enc = work / "object.age"
            source.download_file(SRC_BUCKET, key, str(plain))
            if plain.stat().st_size != size:
                raise RuntimeError(f"download of {key} incomplete")
            age_encrypt(plain, enc)
            upload_verified(enc, tkey, {"source-etag": etag, "source-size": str(size)})
            plain.unlink()
            enc.unlink()
            summary["objects_new"] += 1
        summary["objects_total"] = len(manifest["objects"])
        log(f"objects: {summary['objects_total']} in source, {summary['objects_new']} copied (target never pruned)")
        mpath = work / "objects-manifest.json"
        mpath.write_text(json.dumps(manifest, sort_keys=True))
        menc = work / "objects-manifest.json.age"
        age_encrypt(mpath, menc)
        upload_verified(menc, f"{run_prefix}/objects-manifest.json.age")

    # ------------------------------------------------------------ 5. retention
    keys = [] if WAL_ONLY else list(list_keys(target, BUCKET, f"{PREFIX}/runs/"))
    keep, delete = (
        ([], []) if WAL_ONLY
        else prune_plan(run_stamps(keys, PREFIX), KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY)
    )
    if stamp in delete:
        raise RuntimeError("retention would delete the current run; check BACKUP_OFFSITE_KEEP_*")
    for old in delete:
        old_keys = [k for k in keys if k.startswith(f"{PREFIX}/runs/{old}/")]
        if DRY_RUN:
            log(f"dry  would delete run {old} ({len(old_keys)} keys)")
            continue
        for i in range(0, len(old_keys), 1000):
            target.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in old_keys[i:i + 1000]], "Quiet": True})
        summary["pruned"] += 1
        log(f"ok   pruned run {old} ({len(old_keys)} keys)")
    if WAL_ONLY:
        log("retention: skipped (--wal-only)")
    else:
        log(f"retention: keep {len(keep)} run(s), pruned {summary['pruned']}")

    # ------------------------------------------------------------ 6. run summary
    if not DRY_RUN and not WAL_ONLY:
        status_doc = {k: summary[k] for k in ("stamp", "uploaded", "bytes", "objects_new", "objects_total", "wal", "pruned")}
        status_doc["files"] = [p.name for p in db_files]
        status_doc["at"] = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        target.put_object(Bucket=BUCKET, Key=f"{run_prefix}/status.json",
                          Body=json.dumps(status_doc, sort_keys=True).encode(), ContentType="application/json")
except (ClientError, BotoCoreError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
    step_fail(f"{exc.__class__.__name__}: {exc}")
finally:
    shutil.rmtree(work, ignore_errors=True)

write_status("ok")
PYEOF
