#!/bin/bash
# backup_script.sh

# Cronjob is set to automatically backup every day @ 10:00 AM

# Add path so cron knows where to look for program executables
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Exit on error
set -e

# Resolve script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PGDATA_PATH="$SCRIPT_DIR/data/dbdata/pgdata"

# Ensure ACLs are always restored
cleanup() {
    if [[ -d "$PGDATA_PATH" ]]; then
        sudo setfacl -R -b "$PGDATA_PATH"
    fi
}
trap cleanup EXIT


# Temporarily grant turbo access to pgdata
sudo setfacl -R -m u:turbo:rwX,m:rwX "$PGDATA_PATH"


TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="skyportal_backup_$TIMESTAMP"
BACKUP_DIR="$SCRIPT_DIR/backups/$BACKUP_NAME"
mkdir -p "$BACKUP_DIR"


echo "Starting SkyPortal backup: $BACKUP_NAME"

# 1. Backup the Database
echo "Dumping PostgreSQL database..."
docker exec postgres14.4 pg_dump -U skyportal skyportal > "$BACKUP_DIR/db_dump.sql"


# 2. Backup Named Volumes (thumbnails & persistentdata)
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


# 3. Backup Config and DB Bind Mount
echo "Copying local configs and data..."
cp -r "$SCRIPT_DIR/config" "$BACKUP_DIR/config_backup"
cp -r "$SCRIPT_DIR/data/dbdata" "$BACKUP_DIR/dbdata_raw"


# 4. Final compression
cd "$SCRIPT_DIR/backups"
tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"
mv "$BACKUP_NAME.tar.gz" "/mnt/waz/nas/backups/$BACKUP_NAME.tar.gz"
rm -rf "$BACKUP_NAME"


echo "Backup complete: /mnt/waz/nas/backups/$BACKUP_NAME.tar.gz" 