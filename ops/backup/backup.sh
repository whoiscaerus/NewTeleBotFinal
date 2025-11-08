#!/bin/bash
# PR-067: Automated Database Backup to S3 with Encryption
# Usage: ./backup.sh [--dry-run] [--environment dev|staging|prod]

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/tmp/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DRY_RUN=false
ENVIRONMENT="${ENVIRONMENT:-production}"

# Prometheus metrics (pushgateway)
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"
BACKUP_SUCCESS_METRIC="backup_success_total"
BACKUP_BYTES_METRIC="backup_bytes_total"

# Database connection (from environment)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-trading_signals}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-}"

# S3 configuration
S3_BUCKET="${S3_BUCKET:-trading-signals-backups}"
S3_PREFIX="${S3_PREFIX:-backups/${ENVIRONMENT}}"
S3_REGION="${S3_REGION:-us-east-1}"

# Encryption configuration
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
ENCRYPTION_ALGORITHM="AES256"

# Retention policy (days)
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Logging
LOG_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    log "ERROR: $*" >&2
    send_metric "$BACKUP_SUCCESS_METRIC" 0 "environment=\"${ENVIRONMENT}\",status=\"failed\""
    exit 1
}

send_metric() {
    local metric_name=$1
    local metric_value=$2
    local labels=${3:-}
    
    if [ "$DRY_RUN" = false ]; then
        curl -s -X POST "${PUSHGATEWAY_URL}/metrics/job/backup" \
            --data-binary "# TYPE ${metric_name} counter
${metric_name}{${labels}} ${metric_value}" || true
    fi
}

check_dependencies() {
    log "Checking dependencies..."
    
    local missing_deps=()
    
    command -v pg_dump >/dev/null 2>&1 || missing_deps+=("pg_dump")
    command -v aws >/dev/null 2>&1 || missing_deps+=("aws-cli")
    command -v openssl >/dev/null 2>&1 || missing_deps+=("openssl")
    command -v gzip >/dev/null 2>&1 || missing_deps+=("gzip")
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        error "Missing dependencies: ${missing_deps[*]}"
    fi
    
    log "All dependencies present"
}

create_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        log "Creating backup directory: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR" || error "Failed to create backup directory"
    fi
}

perform_backup() {
    local backup_file="$BACKUP_DIR/${ENVIRONMENT}_${DB_NAME}_${TIMESTAMP}.sql"
    local compressed_file="${backup_file}.gz"
    local encrypted_file="${compressed_file}.enc"
    
    log "Starting database backup..."
    log "Database: ${DB_HOST}:${DB_PORT}/${DB_NAME}"
    log "Backup file: $backup_file"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would execute: pg_dump -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER} -d ${DB_NAME}"
        log "[DRY RUN] Would compress: gzip $backup_file"
        log "[DRY RUN] Would encrypt: openssl enc -${ENCRYPTION_ALGORITHM}"
        echo "$encrypted_file"
        return
    fi
    
    # Perform pg_dump
    PGPASSWORD="$DB_PASSWORD" pg_dump \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --format=plain \
        --no-owner \
        --no-acl \
        --clean \
        --if-exists \
        --verbose \
        --file="$backup_file" 2>> "$LOG_FILE" || error "pg_dump failed"
    
    local backup_size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null)
    log "Backup complete. Size: $(numfmt --to=iec-i --suffix=B "$backup_size" 2>/dev/null || echo "$backup_size bytes")"
    
    # Compress
    log "Compressing backup..."
    gzip -9 "$backup_file" || error "Compression failed"
    
    local compressed_size=$(stat -f%z "$compressed_file" 2>/dev/null || stat -c%s "$compressed_file" 2>/dev/null)
    log "Compression complete. Size: $(numfmt --to=iec-i --suffix=B "$compressed_size" 2>/dev/null || echo "$compressed_size bytes")"
    
    # Encrypt
    if [ -n "$ENCRYPTION_KEY" ]; then
        log "Encrypting backup..."
        openssl enc -"$ENCRYPTION_ALGORITHM" \
            -salt \
            -in "$compressed_file" \
            -out "$encrypted_file" \
            -k "$ENCRYPTION_KEY" || error "Encryption failed"
        
        # Remove unencrypted file
        rm -f "$compressed_file"
        log "Encryption complete"
        
        echo "$encrypted_file"
    else
        log "WARNING: No encryption key provided. Backup not encrypted!"
        echo "$compressed_file"
    fi
}

calculate_checksum() {
    local file=$1
    log "Calculating checksum..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would calculate: sha256sum $file"
        echo "dryrun_checksum"
        return
    fi
    
    local checksum
    if command -v sha256sum >/dev/null 2>&1; then
        checksum=$(sha256sum "$file" | awk '{print $1}')
    else
        checksum=$(shasum -a 256 "$file" | awk '{print $1}')
    fi
    
    log "Checksum: $checksum"
    echo "$checksum"
}

upload_to_s3() {
    local file=$1
    local checksum=$2
    local s3_path="s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "$file")"
    local checksum_path="${s3_path}.sha256"
    
    log "Uploading to S3..."
    log "Destination: $s3_path"
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would upload: aws s3 cp $file $s3_path"
        log "[DRY RUN] Would upload checksum to: $checksum_path"
        return
    fi
    
    # Upload backup file
    aws s3 cp "$file" "$s3_path" \
        --region "$S3_REGION" \
        --storage-class STANDARD_IA \
        --metadata "environment=${ENVIRONMENT},timestamp=${TIMESTAMP},checksum=${checksum}" \
        || error "S3 upload failed"
    
    # Upload checksum
    echo "$checksum" | aws s3 cp - "$checksum_path" \
        --region "$S3_REGION" || error "Checksum upload failed"
    
    local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    log "Upload complete. Size: $(numfmt --to=iec-i --suffix=B "$file_size" 2>/dev/null || echo "$file_size bytes")"
    
    # Send metrics
    send_metric "$BACKUP_BYTES_METRIC" "$file_size" "environment=\"${ENVIRONMENT}\""
}

cleanup_old_backups() {
    log "Cleaning up old backups (retention: ${RETENTION_DAYS} days)..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would list and delete backups older than ${RETENTION_DAYS} days"
        return
    fi
    
    # List and delete old backups from S3
    local cutoff_date=$(date -d "${RETENTION_DAYS} days ago" +%Y-%m-%d 2>/dev/null || date -v-${RETENTION_DAYS}d +%Y-%m-%d 2>/dev/null)
    log "Deleting backups older than: $cutoff_date"
    
    aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --recursive --region "$S3_REGION" | \
    while read -r line; do
        local file_date=$(echo "$line" | awk '{print $1}')
        local file_path=$(echo "$line" | awk '{print $4}')
        
        if [[ "$file_date" < "$cutoff_date" ]]; then
            log "Deleting old backup: $file_path"
            aws s3 rm "s3://${S3_BUCKET}/$file_path" --region "$S3_REGION" || log "WARNING: Failed to delete $file_path"
        fi
    done
    
    log "Cleanup complete"
}

cleanup_local() {
    log "Cleaning up local files..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would delete local backup files"
        return
    fi
    
    # Remove local backup files older than 1 day
    find "$BACKUP_DIR" -name "*.sql.gz*" -type f -mtime +1 -delete 2>/dev/null || true
    find "$BACKUP_DIR" -name "*.log" -type f -mtime +7 -delete 2>/dev/null || true
    
    log "Local cleanup complete"
}

verify_backup() {
    local file=$1
    log "Verifying backup integrity..."
    
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would verify file integrity"
        return
    fi
    
    # Check file size
    local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    if [ "$file_size" -lt 1024 ]; then
        error "Backup file too small: $file_size bytes"
    fi
    
    # Verify it's a valid gzip/encrypted file
    if [[ "$file" == *.enc ]]; then
        # Check openssl can read it
        openssl enc -"$ENCRYPTION_ALGORITHM" -d -in "$file" -k "$ENCRYPTION_KEY" | head -c 1 >/dev/null 2>&1 || error "Encrypted file verification failed"
    elif [[ "$file" == *.gz ]]; then
        gzip -t "$file" || error "Gzip verification failed"
    fi
    
    log "Backup verification passed"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    log "====================================================================="
    log "PR-067: Database Backup Script"
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
    
    # Create backup directory
    create_backup_dir
    
    # Perform backup
    local backup_file
    backup_file=$(perform_backup)
    
    if [ "$DRY_RUN" = false ]; then
        # Verify backup
        verify_backup "$backup_file"
        
        # Calculate checksum
        local checksum
        checksum=$(calculate_checksum "$backup_file")
        
        # Upload to S3
        upload_to_s3 "$backup_file" "$checksum"
        
        # Cleanup old backups
        cleanup_old_backups
        
        # Cleanup local files
        cleanup_local
        
        # Send success metric
        send_metric "$BACKUP_SUCCESS_METRIC" 1 "environment=\"${ENVIRONMENT}\",status=\"success\""
    fi
    
    log "====================================================================="
    log "Backup complete!"
    log "Log file: $LOG_FILE"
    log "====================================================================="
}

# Run main function
main "$@"
