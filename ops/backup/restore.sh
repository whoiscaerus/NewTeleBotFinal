#!/bin/bash
# PR-067: Database Restore from S3 Backup
# Usage: ./restore.sh [--dry-run] [--file <backup_file>] [--timestamp <YYYYMMDD_HHMMSS>] [--environment dev|staging|prod]

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESTORE_DIR="${RESTORE_DIR:-/tmp/restores}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DRY_RUN=false
ENVIRONMENT="${ENVIRONMENT:-production}"
BACKUP_FILE=""
BACKUP_TIMESTAMP=""

# Database connection (from environment)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-trading_signals}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Restore target (optional - restore to different DB)
RESTORE_DB_NAME="${RESTORE_DB_NAME:-$DB_NAME}"

# S3 configuration
S3_BUCKET="${S3_BUCKET:-trading-signals-backups}"
S3_PREFIX="${S3_PREFIX:-backups/${ENVIRONMENT}}"
S3_REGION="${S3_REGION:-us-east-1}"

# Encryption configuration
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
ENCRYPTION_ALGORITHM="AES256"

# Logging
LOG_FILE="${RESTORE_DIR}/restore_${TIMESTAMP}.log"

# Safety checks
REQUIRE_CONFIRMATION="${REQUIRE_CONFIRMATION:-true}"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    log "ERROR: $*" >&2
    exit 1
}

check_dependencies() {
    log "Checking dependencies..."
    
    local missing_deps=()
    
    command -v psql >/dev/null 2>&1 || missing_deps+=("psql")
    command -v aws >/dev/null 2>&1 || missing_deps+=("aws-cli")
    command -v openssl >/dev/null 2>&1 || missing_deps+=("openssl")
    command -v gunzip >/dev/null 2>&1 || missing_deps+=("gunzip")
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        error "Missing dependencies: ${missing_deps[*]}"
    fi
    
    log "All dependencies present"
}

create_restore_dir() {
    if [ ! -d "$RESTORE_DIR" ]; then
        log "Creating restore directory: $RESTORE_DIR"
        mkdir -p "$RESTORE_DIR" || error "Failed to create restore directory"
    fi
}

list_available_backups() {
    log "Available backups in S3:"
    log "Bucket: s3://${S3_BUCKET}/${S3_PREFIX}/"
    
    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --recursive --region "$S3_REGION" | \
    grep -E "\.sql\.gz(\.enc)?$" | \
    awk '{print $1, $2, $4}' | \
    tail -n 20
}

download_backup() {
    local s3_file=$1
    local local_file="${RESTORE_DIR}/$(basename "$s3_file")"
    local checksum_file="${local_file}.sha256"
    local s3_checksum="s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$s3_file").sha256"
    
    log "Downloading backup from S3..."
    log "Source: s3://${S3_BUCKET}/${S3_PREFIX}/$s3_file"
    log "Destination: $local_file"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would download: aws s3 cp s3://${S3_BUCKET}/${S3_PREFIX}/$s3_file $local_file"
        echo "$local_file"
        return
    fi
    
    # Download backup file
    aws s3 cp "s3://${S3_BUCKET}/${S3_PREFIX}/$s3_file" "$local_file" \
        --region "$S3_REGION" || error "Failed to download backup"
    
    # Download checksum
    if aws s3 cp "$s3_checksum" "$checksum_file" --region "$S3_REGION" 2>/dev/null; then
        log "Checksum file downloaded"
        
        # Verify checksum
        local expected_checksum=$(cat "$checksum_file")
        local actual_checksum
        if command -v sha256sum >/dev/null 2>&1; then
            actual_checksum=$(sha256sum "$local_file" | awk '{print $1}')
        else
            actual_checksum=$(shasum -a 256 "$local_file" | awk '{print $1}')
        fi
        
        if [ "$expected_checksum" != "$actual_checksum" ]; then
            error "Checksum verification failed! Expected: $expected_checksum, Got: $actual_checksum"
        fi
        
        log "Checksum verification passed"
    else
        log "WARNING: No checksum file found for this backup"
    fi
    
    log "Download complete"
    echo "$local_file"
}

decrypt_backup() {
    local encrypted_file=$1
    local decrypted_file="${encrypted_file%.enc}"
    
    if [[ ! "$encrypted_file" == *.enc ]]; then
        # Not encrypted, return as-is
        echo "$encrypted_file"
        return
    fi
    
    log "Decrypting backup..."
    
    if [ -z "$ENCRYPTION_KEY" ]; then
        error "Encrypted backup requires BACKUP_ENCRYPTION_KEY environment variable"
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would decrypt: openssl enc -d -${ENCRYPTION_ALGORITHM} -in $encrypted_file -out $decrypted_file"
        echo "$decrypted_file"
        return
    fi
    
    openssl enc -d -"$ENCRYPTION_ALGORITHM" \
        -in "$encrypted_file" \
        -out "$decrypted_file" \
        -k "$ENCRYPTION_KEY" || error "Decryption failed"
    
    log "Decryption complete"
    echo "$decrypted_file"
}

decompress_backup() {
    local compressed_file=$1
    local decompressed_file="${compressed_file%.gz}"
    
    log "Decompressing backup..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would decompress: gunzip -c $compressed_file > $decompressed_file"
        echo "$decompressed_file"
        return
    fi
    
    gunzip -c "$compressed_file" > "$decompressed_file" || error "Decompression failed"
    
    log "Decompression complete"
    echo "$decompressed_file"
}

verify_sql_file() {
    local sql_file=$1
    log "Verifying SQL file..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would verify SQL file structure"
        return
    fi
    
    # Check file size
    local file_size=$(stat -f%z "$sql_file" 2>/dev/null || stat -c%s "$sql_file" 2>/dev/null)
    if [ "$file_size" -lt 1024 ]; then
        error "SQL file too small: $file_size bytes"
    fi
    
    # Check for SQL header
    if ! head -n 10 "$sql_file" | grep -qi "postgresql\|sql"; then
        error "File does not appear to be a PostgreSQL dump"
    fi
    
    log "SQL file verification passed"
}

create_restore_database() {
    log "Creating restore database if needed..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would create database: $RESTORE_DB_NAME"
        return
    fi
    
    # Check if database exists
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -lqt | \
        cut -d \| -f 1 | grep -qw "$RESTORE_DB_NAME" && {
        log "Database $RESTORE_DB_NAME already exists"
        return
    }
    
    # Create database
    log "Creating database: $RESTORE_DB_NAME"
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres \
        -c "CREATE DATABASE $RESTORE_DB_NAME;" || error "Failed to create database"
    
    log "Database created successfully"
}

perform_restore() {
    local sql_file=$1
    
    log "Starting database restore..."
    log "Database: ${DB_HOST}:${DB_PORT}/${RESTORE_DB_NAME}"
    log "SQL file: $sql_file"
    
    if [ "$RESTORE_DB_NAME" != "$DB_NAME" ]; then
        log "WARNING: Restoring to different database: $RESTORE_DB_NAME (original: $DB_NAME)"
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would execute: psql -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${RESTORE_DB_NAME} < $sql_file"
        return
    fi
    
    # Restore database
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$RESTORE_DB_NAME" \
        -f "$sql_file" \
        --single-transaction \
        --set ON_ERROR_STOP=on \
        2>> "$LOG_FILE" || error "Database restore failed"
    
    log "Database restore complete"
}

verify_restore() {
    log "Verifying restore..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would verify table counts and row counts"
        return
    fi
    
    # Count tables
    local table_count
    table_count=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$RESTORE_DB_NAME" \
        -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
    
    log "Restored tables: $table_count"
    
    if [ "$table_count" -eq 0 ]; then
        error "No tables found after restore!"
    fi
    
    # Sample row counts from major tables
    log "Sample row counts:"
    for table in users signals approvals journeys; do
        local count
        count=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$RESTORE_DB_NAME" \
            -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | xargs || echo "0")
        log "  $table: $count rows"
    done
    
    log "Restore verification passed"
}

cleanup_local() {
    log "Cleaning up local files..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would delete downloaded backup files"
        return
    fi
    
    # Remove downloaded files
    rm -f "${RESTORE_DIR}"/*.sql 2>/dev/null || true
    rm -f "${RESTORE_DIR}"/*.sql.gz 2>/dev/null || true
    rm -f "${RESTORE_DIR}"/*.sql.gz.enc 2>/dev/null || true
    rm -f "${RESTORE_DIR}"/*.sha256 2>/dev/null || true
    
    log "Local cleanup complete"
}

confirm_restore() {
    if [ "$REQUIRE_CONFIRMATION" = false ] || [ "$DRY_RUN" = true ]; then
        return
    fi
    
    log ""
    log "====================================================================="
    log "WARNING: This will restore the database!"
    log "Environment: $ENVIRONMENT"
    log "Target database: ${DB_HOST}:${DB_PORT}/${RESTORE_DB_NAME}"
    log "====================================================================="
    log ""
    
    read -p "Are you sure you want to proceed? (type 'YES' to confirm): " confirmation
    
    if [ "$confirmation" != "YES" ]; then
        log "Restore cancelled by user"
        exit 0
    fi
    
    log "Confirmation received, proceeding with restore..."
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    log "====================================================================="
    log "PR-067: Database Restore Script"
    log "Environment: $ENVIRONMENT"
    log "====================================================================="
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                log "DRY RUN MODE ENABLED"
                shift
                ;;
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --file)
                BACKUP_FILE="$2"
                shift 2
                ;;
            --timestamp)
                BACKUP_TIMESTAMP="$2"
                shift 2
                ;;
            --no-confirm)
                REQUIRE_CONFIRMATION=false
                shift
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done
    
    # Validate environment
    if [[ ! "$ENVIRONMENT" =~ ^(dev|development|staging|production|prod)$ ]]; then
        error "Invalid environment: $ENVIRONMENT (must be dev, staging, or production)"
    fi
    
    # Normalize environment name
    [[ "$ENVIRONMENT" == "prod" ]] && ENVIRONMENT="production"
    [[ "$ENVIRONMENT" == "dev" ]] && ENVIRONMENT="development"
    
    # Check dependencies
    check_dependencies
    
    # Create restore directory
    create_restore_dir
    
    # If no backup file specified, list available backups
    if [ -z "$BACKUP_FILE" ] && [ -z "$BACKUP_TIMESTAMP" ]; then
        log "No backup file specified. Listing available backups..."
        list_available_backups
        error "Please specify --file <filename> or --timestamp <YYYYMMDD_HHMMSS>"
    fi
    
    # Determine backup file to restore
    if [ -z "$BACKUP_FILE" ]; then
        # Find backup by timestamp
        BACKUP_FILE=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --recursive --region "$S3_REGION" | \
            grep "${BACKUP_TIMESTAMP}" | \
            grep -E "\.sql\.gz(\.enc)?$" | \
            awk '{print $4}' | \
            head -n 1)
        
        if [ -z "$BACKUP_FILE" ]; then
            error "No backup found with timestamp: $BACKUP_TIMESTAMP"
        fi
        
        # Extract just the filename
        BACKUP_FILE=$(basename "$BACKUP_FILE")
    fi
    
    log "Using backup file: $BACKUP_FILE"
    
    # Confirm restore
    confirm_restore
    
    # Download backup
    local downloaded_file
    downloaded_file=$(download_backup "$BACKUP_FILE")
    
    if [ "$DRY_RUN" = false ]; then
        # Decrypt if encrypted
        local decrypted_file
        decrypted_file=$(decrypt_backup "$downloaded_file")
        
        # Decompress
        local sql_file
        sql_file=$(decompress_backup "$decrypted_file")
        
        # Verify SQL file
        verify_sql_file "$sql_file"
        
        # Create restore database
        create_restore_database
        
        # Perform restore
        perform_restore "$sql_file"
        
        # Verify restore
        verify_restore
        
        # Cleanup
        cleanup_local
    fi
    
    log "====================================================================="
    log "Restore complete!"
    log "Database: ${DB_HOST}:${DB_PORT}/${RESTORE_DB_NAME}"
    log "Log file: $LOG_FILE"
    log "====================================================================="
}

# Run main function
main "$@"
