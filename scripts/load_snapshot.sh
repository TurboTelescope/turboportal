#!/bin/bash
# load_snapshot.sh
#
# Load a snapshot produced by snapshot_live.sh into the MIRROR compose project.
#
# DESTRUCTIVE against the mirror: drops the mirror database and clears the mirror
# volumes. It will not touch the live project -- the guards below are the reason this
# is a separate script rather than a flag on the in-place restore_script.sh.
#
# Usage: scripts/load_snapshot.sh SNAPSHOT_DIR [--mirror-dir DIR]

set -euo pipefail

MIRROR_DIR="${MIRROR_DIR:-/home/tayamni/turboportal-mirror}"
MIRROR_PROJECT="${MIRROR_PROJECT:-turboportal-mirror}"
PROTECTED_PROJECTS="${PROTECTED_PROJECTS:-turboportal skyportal}"
DB_NAME=skyportal
DB_USER=skyportal
DB_PASS=password
PG_IMAGE=postgres:17

SNAP=""
while [ $# -gt 0 ]; do
    case "$1" in
        --mirror-dir) MIRROR_DIR="${2:?--mirror-dir needs a directory}"; shift 2 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        -*) echo "unknown option: $1" >&2; exit 1 ;;
        *) SNAP="$1"; shift ;;
    esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

[ -n "$SNAP" ] || die "usage: $0 SNAPSHOT_DIR [--mirror-dir DIR]"
SNAP=$(cd "$SNAP" 2>/dev/null && pwd) || die "no such snapshot dir: $SNAP"
MIRROR_DIR=$(cd "$MIRROR_DIR" 2>/dev/null && pwd) || die "no such mirror dir: $MIRROR_DIR"

# ---- Guards -----------------------------------------------------------------
# A misfire here would destroy the live instance, so the target is verified three
# independent ways before anything is written.

for p in $PROTECTED_PROJECTS; do
    [ "$MIRROR_PROJECT" = "$p" ] \
        && die "refusing to load into protected compose project '$p'"
done

[ -f "$MIRROR_DIR/docker-compose.yaml" ] \
    || die "$MIRROR_DIR has no docker-compose.yaml"

# The mirror dir must not be an app checkout; that would mean we are pointed at a
# real installation rather than the mirror's runtime-only directory.
[ -d "$MIRROR_DIR/skyportal" ] \
    && die "$MIRROR_DIR looks like an app checkout, not the mirror directory"

ACTUAL_PROJECT=$(cd "$MIRROR_DIR" && docker compose config --format json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')
[ "$ACTUAL_PROJECT" = "$MIRROR_PROJECT" ] \
    || die "compose in $MIRROR_DIR resolves to project '$ACTUAL_PROJECT', expected '$MIRROR_PROJECT'"

# ---- Snapshot validation ----------------------------------------------------
[ -f "$SNAP/DONE" ] || die "$SNAP has no DONE marker; snapshot is incomplete"
log "verifying snapshot checksums..."
( cd "$SNAP" && sha256sum -c SHA256SUMS ) || die "checksum mismatch in $SNAP"

# ---- Resolve mirror volumes ------------------------------------------------
volume_name() {
    local key=$1 name="${MIRROR_PROJECT}_$1"
    case "$name" in
        "${MIRROR_PROJECT}_"*) ;;
        *) die "refusing to write volume '$name': missing mirror prefix" ;;
    esac
    printf '%s' "$name"
}
THUMB_VOL=$(volume_name thumbnails)
PDATA_VOL=$(volume_name persistentdata)

log "loading $SNAP"
log "  into project '$MIRROR_PROJECT' ($MIRROR_DIR)"
log "  volumes: $THUMB_VOL $PDATA_VOL"

cd "$MIRROR_DIR"

log "stopping mirror web..."
docker compose stop web >/dev/null 2>&1 || true

log "starting mirror db..."
docker compose up -d db
for i in $(seq 1 60); do
    cid=$(docker compose ps -q db)
    [ -n "$cid" ] && [ "$(docker inspect "$cid" --format '{{.State.Health.Status}}')" = "healthy" ] && break
    [ "$i" -eq 60 ] && die "mirror db did not become healthy"
    sleep 2
done

NET=$(docker inspect "$(docker compose ps -q db)" \
    --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
[ -n "$NET" ] || die "could not resolve mirror network"

psql_admin() {
    docker run --rm --network "$NET" -e PGPASSWORD="$DB_PASS" "$PG_IMAGE" \
        psql -h db -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 "$@"
}

log "recreating mirror database..."
psql_admin -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE)"
psql_admin -c "CREATE DATABASE $DB_NAME OWNER $DB_USER"

log "restoring dump (this takes a while)..."
docker run --rm --network "$NET" \
    -v "$SNAP":/snapshot:ro \
    -e PGPASSWORD="$DB_PASS" "$PG_IMAGE" \
    pg_restore -h db -U "$DB_USER" -d "$DB_NAME" -j4 \
        --no-owner --no-privileges /snapshot/skyportal.dump \
    || die "pg_restore failed"

restore_volume() {
    local vol=$1 archive=$2
    # root so it can clear whatever is there and restore ownership from the archive
    # (files are uid 1000, matching the container's skyportal user).
    docker run --rm \
        -v "$vol":/volume \
        -v "$SNAP":/snapshot:ro \
        alpine sh -c "rm -rf /volume/..?* /volume/.[!.]* /volume/* 2>/dev/null; tar -xzf /snapshot/$archive -C /volume"
}

log "restoring thumbnails volume..."
restore_volume "$THUMB_VOL" thumbnails.tar.gz

log "restoring persistentdata volume..."
restore_volume "$PDATA_VOL" persistentdata.tar.gz

log "starting mirror..."
docker compose up -d

log "verifying against manifest..."
FAIL=0
for t in candidates objs photometry thumbnails sources; do
    want=$(awk -F': ' "/^rows_$t:/ {print \$2}" "$SNAP/manifest.txt")
    got=$(docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -At -c "SELECT count(*) FROM $t")
    if [ "$want" = "$got" ]; then
        printf '  %-12s %s ✓\n' "$t" "$got"
    else
        printf '  %-12s got %s, expected %s ✗\n' "$t" "$got" "$want"; FAIL=1
    fi
done
want_files=$(awk -F': ' '/^thumbnail_files:/ {print $2}' "$SNAP/manifest.txt")
got_files=$(docker run --rm -v "$THUMB_VOL":/v:ro alpine sh -c 'find /v -type f | wc -l' | tr -d ' ')
if [ "$want_files" = "$got_files" ]; then
    printf '  %-12s %s ✓\n' "thumb files" "$got_files"
else
    printf '  %-12s got %s, expected %s ✗\n' "thumb files" "$got_files" "$want_files"; FAIL=1
fi

[ "$FAIL" -eq 0 ] || die "verification failed"
log "load complete; mirror is up on http://127.0.0.1:8010"
