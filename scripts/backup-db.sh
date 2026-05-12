#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_DB="$ROOT_DIR/app_server/inventory.db"
BACKUP_DIR="$ROOT_DIR/backups"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$SOURCE_DB" ]]; then
  echo "Database file not found at $SOURCE_DB" >&2
  exit 1
fi

TIMESTAMP="$(date +"%Y%m%d-%H%M%S")"
BACKUP_FILE="$BACKUP_DIR/inventory-$TIMESTAMP.db"

cp "$SOURCE_DB" "$BACKUP_FILE"
echo "Backup created at $BACKUP_FILE"
