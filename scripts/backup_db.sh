#!/bin/bash

# Database backup script for GrowHaven

# Load environment variables
source .env

# Variables
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups"
BACKUP_FILE="${BACKUP_DIR}/growhaven_db_${TIMESTAMP}.sql"

# Create backup directory if it doesn't exist
mkdir -p ${BACKUP_DIR}

# Backup the database
echo "Creating database backup..."
pg_dump -h ${DB_HOST:-localhost} -U ${DB_USER} -d ${DB_NAME} -f ${BACKUP_FILE}

if [ $? -eq 0 ]; then
    echo "Backup completed successfully: ${BACKUP_FILE}"
    
    # Compress the backup
    gzip ${BACKUP_FILE}
    echo "Backup compressed: ${BACKUP_FILE}.gz"
    
    # Delete backups older than 30 days
    find ${BACKUP_DIR} -name "growhaven_db_*.sql.gz" -type f -mtime +30 -delete
    echo "Old backups cleaned up"
else
    echo "Backup failed!"
    exit 1
fi
