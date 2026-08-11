#!/bin/bash
# restore_script.sh
#
# DESTRUCTIVE: restores a backup tarball in-place onto the LIVE compose project
# (stops the stack, replaces config/ and data/dbdata, re-imports the SQL dump).
# For restore-into-a-throwaway-container testing, do NOT use this script.

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: ./restore_script.sh /path/to/skyportal_backup_TIMESTAMP.tar.gz"
    exit 1
fi

BACKUP_FILE=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP_DIR="$SCRIPT_DIR/restore_temp"

echo "Preparing to restore from $BACKUP_FILE..."

# 1. Unpack the backup
mkdir -p "$TEMP_DIR"
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR" --strip-components=1

# 2. Stop the containers to prevent file corruption during file swap
echo "Stopping SkyPortal services..."
docker-compose stop

# 3. Restore local config and raw data.
# pgdata contents are owned by the postgres container's uid, so root is needed
# to remove/replace them (the container entrypoint re-chowns pgdata on start).
echo "Restoring config files..."
rm -rf "$SCRIPT_DIR/config"
cp -r "$TEMP_DIR/config_backup" "$SCRIPT_DIR/config"

echo "Restoring raw dbdata files..."
sudo -n rm -rf "$SCRIPT_DIR/data/dbdata"
mkdir -p "$SCRIPT_DIR/data"
sudo -n cp -r "$TEMP_DIR/dbdata_raw" "$SCRIPT_DIR/data/dbdata"

# 4. Restore named volumes (thumbnails & persistentdata)
echo "Restoring thumbnails volume..."
docker run --rm \
  -v thumbnails:/volume \
  -v "$TEMP_DIR":/backup \
  alpine sh -c "rm -rf /volume/* && tar -xzf /backup/thumbnails.tar.gz -C /volume"

echo "Restoring persistentdata volume..."
docker run --rm \
  -v persistentdata:/volume \
  -v "$TEMP_DIR":/backup \
  alpine sh -c "rm -rf /volume/* && tar -xzf /backup/persistentdata.tar.gz -C /volume"

# 5. Start the DB container to perform the SQL restore
echo "Starting database for SQL restoration..."
docker-compose up -d db
echo "Waiting for database to be ready..."
sleep 10

# 6. SQL restore (logical dump). ON_ERROR_STOP so a failed restore cannot
# masquerade as a successful one.
echo "Re-importing SQL dump..."
docker exec -i postgres14.4 psql -U skyportal -d skyportal -v ON_ERROR_STOP=1 \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker exec -i postgres14.4 psql -U skyportal -d skyportal -v ON_ERROR_STOP=1 \
    < "$TEMP_DIR/db_dump.sql"

# 7. Finalize and restart everything
echo "Restarting all services..."
docker-compose up -d
rm -rf "$TEMP_DIR"

echo "Restore complete! SkyPortal is running."
