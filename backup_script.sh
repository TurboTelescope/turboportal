#!/bin/bash
# backup_script.sh
#
# Daily SkyPortal backup (run from cron; output appended to backups/backup_log.log).
# Produces a single tarball and always prints its final path on the last line.

# Add path so cron knows where to look for program executables
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAS_DIR="/mnt/waziyata/backups/skyportal"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="skyportal_backup_$TIMESTAMP"
BACKUP_DIR="$SCRIPT_DIR/backups/$BACKUP_NAME"
mkdir -p "$BACKUP_DIR"

echo "Starting SkyPortal backup: $BACKUP_NAME"

# 1. Backup the database (logical dump; consistent even while the DB is live)
echo "Dumping PostgreSQL database..."
docker exec postgres14.4 pg_dump -U skyportal skyportal > "$BACKUP_DIR/db_dump.sql"

# 2. Backup named volumes (thumbnails & persistentdata)
echo "Archiving thumbnails volume..."
docker run --rm \
  -v thumbnails:/volume \
  -v "$BACKUP_DIR":/backup \
  alpine tar -czf /backup/thumbnails.tar.gz -C /volume .

echo "Archiving persistentdata volume..."
docker run --rm \
  -v persistentdata:/volume \
  -v "$BACKUP_DIR":/backup \
  alpine tar -czf /backup/persistentdata.tar.gz -C /volume .

# 3. Backup config and the raw DB bind mount.
# pgdata is owned by the postgres container's uid, so root is needed to read it.
# (sudo -n: fail loudly instead of hanging on a password prompt under cron.)
echo "Copying local configs and data..."
cp -r "$SCRIPT_DIR/config" "$BACKUP_DIR/config_backup"
sudo -n cp -r "$SCRIPT_DIR/data/dbdata" "$BACKUP_DIR/dbdata_raw"
sudo -n chown -R "$(id -u):$(id -g)" "$BACKUP_DIR/dbdata_raw"

# 4. Final compression
cd "$SCRIPT_DIR/backups"
tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

# 5. Move to the NAS if it's mounted; otherwise keep the tarball locally.
FINAL_PATH="$SCRIPT_DIR/backups/$BACKUP_NAME.tar.gz"
if mountpoint -q /mnt/waziyata && mkdir -p "$NAS_DIR" 2>/dev/null; then
    mv "$FINAL_PATH" "$NAS_DIR/$BACKUP_NAME.tar.gz"
    FINAL_PATH="$NAS_DIR/$BACKUP_NAME.tar.gz"
else
    echo "WARNING: /mnt/waziyata not mounted or $NAS_DIR not writable; backup kept locally" >&2
fi

echo "Backup complete: $FINAL_PATH"
