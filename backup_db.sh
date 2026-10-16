#!/usr/bin/env bash
# BilisLikas 2.0: daily database backup (ISO/IEC 25010 Reliability - Recoverability)
set -euo pipefail
cd "$(dirname "$0")"
getv() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//' || true; }
DB_USER=$(getv POSTGRES_USER); DB_PASS=$(getv POSTGRES_PASSWORD); DB_NAME=$(getv POSTGRES_DB)
DB_HOST=$(getv POSTGRES_HOST); DB_PORT=$(getv POSTGRES_PORT)
DEST="$HOME/bilislikas_backups"; mkdir -p "$DEST" logs
FILE="$DEST/bilislikas_$(date +%Y-%m-%d_%H%M).sql.gz"
PGPASSWORD="$DB_PASS" pg_dump -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
ls -1t "$DEST"/bilislikas_*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date '+%F %T') backup saved: $FILE ($(du -h "$FILE" | cut -f1))"
