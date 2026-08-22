#!/bin/bash
# snapshot_live.sh
#
# Read-only snapshot of the live SkyPortal stack, for loading into the mirror
# instance with load_snapshot.sh. Prints the snapshot directory on the last line.
#
# Container and volume names are resolved from the running compose project instead
# of being hardcoded: stale hardcoded names are what silently broke backup_script.sh
# (it dumped from a "postgres14.4" container and archived un-prefixed volumes).
#
# Usage: scripts/snapshot_live.sh [--out DIR]

set -euo pipefail

LIVE_PROJECT="${LIVE_PROJECT:-turboportal}"
OUT_ROOT="${OUT_ROOT:-/home/tayamni/turboportal-mirror/snapshots}"
DB_NAME="${DB_NAME:-skyportal}"
DB_USER="${DB_USER:-skyportal}"
MIN_FREE_MB=8000

OUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --out) OUT="${2:?--out needs a directory}"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

# Resolve a compose service's container by label rather than by name.
container_for() {
    local svc=$1 id
    id=$(docker ps -q \
        --filter "label=com.docker.compose.project=$LIVE_PROJECT" \
        --filter "label=com.docker.compose.service=$svc")
    [ -n "$id" ] || die "no running '$svc' container in compose project '$LIVE_PROJECT'"
    [ "$(printf '%s' "$id" | grep -c .)" -eq 1 ] || die "multiple '$svc' containers found"
    printf '%s' "$id"
}

# Resolve the named volume actually mounted at a path, so a renamed or re-pointed
# volume is picked up instead of silently archiving the wrong one.
volume_at() {
    local cid=$1 dest=$2 name
    name=$(docker inspect "$cid" --format \
        "{{range .Mounts}}{{if eq .Destination \"$dest\"}}{{.Name}}{{end}}{{end}}")
    [ -n "$name" ] || die "no named volume mounted at $dest in container $cid"
    printf '%s' "$name"
}

archive_volume() {
    local vol=$1 out_file=$2
    # Runs as the invoking user: every file in both volumes is world-readable, so
    # root is unnecessary and the archive comes out owned by us (no sudo, which is
    # what made backup_script.sh fail under cron).
    docker run --rm --user "$(id -u):$(id -g)" \
        -v "$vol":/volume:ro \
        -v "$(dirname "$out_file")":/backup \
        alpine tar -czf "/backup/$(basename "$out_file")" -C /volume .
}

count_rows() {
    docker exec "$DB_CID" psql -U "$DB_USER" -d "$DB_NAME" -At \
        -c "SELECT count(*) FROM $1"
}

command -v docker >/dev/null || die "docker not found"
DB_CID=$(container_for db)
WEB_CID=$(container_for web)

THUMB_VOL=$(volume_at "$WEB_CID" /skyportal/static/thumbnails)
PDATA_VOL=$(volume_at "$WEB_CID" /skyportal/persistentdata)

[ -n "$OUT" ] || OUT="$OUT_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
[ -e "$OUT" ] && die "snapshot dir already exists: $OUT"
mkdir -p "$OUT"

FREE_MB=$(df -Pm "$OUT" | awk 'NR==2 {print $4}')
[ "$FREE_MB" -ge "$MIN_FREE_MB" ] \
    || die "only ${FREE_MB}MB free at $OUT, need ${MIN_FREE_MB}MB"

log "snapshotting project '$LIVE_PROJECT' -> $OUT"
log "  db=$DB_CID thumbnails=$THUMB_VOL persistentdata=$PDATA_VOL"

# The DB is the index and the on-disk files are its referents, so the DB is
# captured FIRST: that way every row in the dump already has its file. The
# reverse order yields rows whose thumbnail files are missing, which renders as
# broken cutouts.
log "dumping database..."
docker exec "$DB_CID" pg_dump -U "$DB_USER" -Fc -Z3 "$DB_NAME" > "$OUT/skyportal.dump"

log "validating dump..."
TABLE_DATA=$(pg_restore -l "$OUT/skyportal.dump" | grep -c "TABLE DATA")
[ "$TABLE_DATA" -gt 100 ] || die "dump has only $TABLE_DATA TABLE DATA entries; refusing"

log "archiving thumbnails ($THUMB_VOL)..."
archive_volume "$THUMB_VOL" "$OUT/thumbnails.tar.gz"

log "archiving persistentdata ($PDATA_VOL)..."
archive_volume "$PDATA_VOL" "$OUT/persistentdata.tar.gz"

log "writing manifest..."
{
    echo "snapshot_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "live_project: $LIVE_PROJECT"
    echo "live_commit: $(git -C "$(dirname "$0")/.." rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "web_image: $(docker inspect "$WEB_CID" --format '{{.Config.Image}}')"
    echo "web_image_id: $(docker inspect "$WEB_CID" --format '{{.Image}}')"
    echo "pg_version: $(docker exec "$DB_CID" psql -U "$DB_USER" -d "$DB_NAME" -At -c 'SHOW server_version')"
    echo "src_thumbnails_volume: $THUMB_VOL"
    echo "src_persistentdata_volume: $PDATA_VOL"
    echo "dump_table_data_entries: $TABLE_DATA"
    echo "thumbnail_files: $(docker run --rm -v "$THUMB_VOL":/v:ro alpine sh -c 'find /v -type f | wc -l' | tr -d ' ')"
    for t in candidates objs photometry thumbnails sources; do
        echo "rows_$t: $(count_rows "$t")"
    done
} > "$OUT/manifest.txt"

log "checksumming..."
( cd "$OUT" && sha256sum skyportal.dump thumbnails.tar.gz persistentdata.tar.gz > SHA256SUMS )

# DONE is written last, so a partial snapshot is never mistaken for a usable one.
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/DONE"

log "snapshot complete ($(du -sh "$OUT" | cut -f1))"
cat "$OUT/manifest.txt"
echo "$OUT"
