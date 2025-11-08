# Backup & Restore Runbook

**PR-067: Owner Automations - Database Backup, Disaster Recovery, and Environment Promotion**

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Backup Procedures](#backup-procedures)
4. [Restore Procedures](#restore-procedures)
5. [Environment Promotion](#environment-promotion)
6. [Disaster Recovery](#disaster-recovery)
7. [Monitoring & Alerts](#monitoring--alerts)
8. [Troubleshooting](#troubleshooting)
9. [Emergency Contacts](#emergency-contacts)

---

## Overview

This runbook provides step-by-step procedures for backing up, restoring, and promoting database environments for the Trading Signal Platform. All scripts are located in the `/ops` directory.

### Files

- `/ops/backup/backup.sh` - Automated backup to S3 with encryption
- `/ops/backup/restore.sh` - Restore from S3 backup
- `/ops/promote/release.sh` - Promote releases between environments

### Retention Policy

- **Development**: 7 days
- **Staging**: 14 days
- **Production**: 30 days

### Backup Schedule

- **Development**: Daily at 2:00 AM UTC
- **Staging**: Daily at 3:00 AM UTC
- **Production**: Daily at 1:00 AM UTC + hourly snapshots

---

## Prerequisites

### Required Tools

```bash
# PostgreSQL client tools
sudo apt-get install postgresql-client-15

# AWS CLI
sudo apt-get install awscli

# Verify installation
pg_dump --version
psql --version
aws --version
openssl version
```

### Required Environment Variables

```bash
# Database connection
export DB_HOST="your-db-host.rds.amazonaws.com"
export DB_PORT="5432"
export DB_NAME="trading_signals"
export DB_USER="postgres"
export DB_PASSWORD="your-secure-password"

# S3 configuration
export S3_BUCKET="trading-signals-backups"
export S3_PREFIX="backups/production"
export S3_REGION="us-east-1"

# Encryption key (keep secure!)
export BACKUP_ENCRYPTION_KEY="your-32-char-encryption-key"

# Prometheus pushgateway
export PUSHGATEWAY_URL="http://prometheus-pushgateway:9091"
```

### AWS IAM Permissions

The backup user requires the following S3 permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::trading-signals-backups/*",
        "arn:aws:s3:::trading-signals-backups"
      ]
    }
  ]
}
```

---

## Backup Procedures

### Manual Backup (Production)

```bash
# Navigate to ops directory
cd /path/to/project/ops/backup

# Set environment variables
export ENVIRONMENT=production
export DB_HOST=prod-db.example.com
export DB_PASSWORD=***

# Run backup
./backup.sh

# Verify success
echo $?  # Should be 0
```

### Scheduled Backup (Cron)

Add to crontab:

```cron
# Production backup at 1:00 AM UTC daily
0 1 * * * /path/to/ops/backup/backup.sh --environment production >> /var/log/backup.log 2>&1

# Staging backup at 3:00 AM UTC daily
0 3 * * * /path/to/ops/backup/backup.sh --environment staging >> /var/log/backup.log 2>&1
```

### Backup with Docker

```bash
docker run --rm \
  -v /path/to/ops:/ops \
  -e DB_HOST=prod-db.example.com \
  -e DB_PASSWORD=*** \
  -e S3_BUCKET=trading-signals-backups \
  -e BACKUP_ENCRYPTION_KEY=*** \
  postgres:15 \
  /ops/backup/backup.sh --environment production
```

### Dry Run (Test Without Executing)

```bash
# Test backup script without actual execution
./backup.sh --dry-run --environment production

# Output will show:
# - [DRY RUN] Would execute: pg_dump ...
# - [DRY RUN] Would compress: gzip ...
# - [DRY RUN] Would encrypt: openssl ...
# - [DRY RUN] Would upload: aws s3 cp ...
```

### Backup Verification

```bash
# List recent backups
aws s3 ls s3://trading-signals-backups/backups/production/ --recursive | tail -n 20

# Download checksum
aws s3 cp s3://trading-signals-backups/backups/production/production_trading_signals_20250118_010000.sql.gz.enc.sha256 - | cat

# Verify checksum locally
sha256sum /tmp/backups/production_trading_signals_20250118_010000.sql.gz.enc
```

---

## Restore Procedures

### ⚠️ CRITICAL WARNING

**Restoring a database will OVERWRITE all existing data. Always:**

1. Create a backup of the current state before restoring
2. Test restore on a non-production database first
3. Notify all stakeholders before production restore
4. Have a rollback plan ready

### Restore to Production (Emergency)

```bash
# 1. List available backups
cd /path/to/project/ops/backup
./restore.sh --environment production

# Output shows available backups with timestamps

# 2. Choose specific backup by timestamp
./restore.sh \
  --environment production \
  --timestamp 20250118_010000

# 3. Confirm when prompted (type 'YES')

# 4. Monitor restore progress
tail -f /tmp/restores/restore_*.log
```

### Restore to Staging (Point-in-Time Recovery)

```bash
# Restore production backup to staging for testing
export RESTORE_DB_NAME=trading_signals_staging

./restore.sh \
  --environment production \
  --timestamp 20250118_010000 \
  --no-confirm
```

### Restore to Temporary Database (Analysis)

```bash
# Create throwaway database for analysis
export RESTORE_DB_NAME=trading_signals_analysis_$(date +%Y%m%d)

./restore.sh \
  --environment production \
  --timestamp 20250118_010000 \
  --no-confirm

# After analysis, drop database
psql -h $DB_HOST -U $DB_USER -d postgres -c "DROP DATABASE $RESTORE_DB_NAME;"
```

### Dry Run Restore

```bash
# Test restore process without executing
./restore.sh \
  --dry-run \
  --environment production \
  --timestamp 20250118_010000
```

### Restore from Specific File

```bash
# If you know the exact backup filename
./restore.sh \
  --environment production \
  --file production_trading_signals_20250118_010000.sql.gz.enc
```

### Post-Restore Verification

```bash
# 1. Check table counts
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
  SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del 
  FROM pg_stat_user_tables 
  ORDER BY n_tup_ins DESC 
  LIMIT 20;
"

# 2. Verify critical data
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
  SELECT 
    (SELECT COUNT(*) FROM users) as users,
    (SELECT COUNT(*) FROM signals) as signals,
    (SELECT COUNT(*) FROM approvals) as approvals,
    (SELECT COUNT(*) FROM journeys) as journeys;
"

# 3. Check latest timestamps
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
  SELECT 'signals' as table_name, MAX(created_at) as latest FROM signals
  UNION ALL
  SELECT 'approvals', MAX(created_at) FROM approvals
  UNION ALL
  SELECT 'users', MAX(created_at) FROM users;
"
```

---

## Environment Promotion

### Development → Staging

```bash
cd /path/to/project/ops/promote

# Promote with version tag
./release.sh \
  --from development \
  --to staging \
  --version v1.5.0

# What happens:
# 1. Tags Docker image: development-latest → staging-v1.5.0
# 2. Creates git tag: v1.5.0-staging
# 3. Runs database migrations on staging
# 4. Warms application caches
# 5. Verifies deployment health
# 6. Creates release notes
```

### Staging → Production

```bash
cd /path/to/project/ops/promote

# Promote to production (requires confirmation)
./release.sh \
  --from staging \
  --to production \
  --version v1.5.0

# Type 'YES' to confirm

# What happens:
# 1. Tags Docker image: staging-latest → production-v1.5.0
# 2. Creates git tag: v1.5.0-production
# 3. Runs database migrations on production
# 4. Updates Kubernetes deployment (if configured)
# 5. Warms application caches
# 6. Verifies deployment health
# 7. Sends Prometheus metrics
# 8. Creates release notes
```

### Dry Run Promotion

```bash
# Test promotion without executing
./release.sh \
  --dry-run \
  --from staging \
  --to production \
  --version v1.5.0

# Output shows all steps that would execute
```

### Skip Migrations

```bash
# Promote without running migrations (already run manually)
./release.sh \
  --from staging \
  --to production \
  --version v1.5.0 \
  --no-migrations
```

### Skip Cache Warming

```bash
# Promote without cache warming (low-traffic deployment)
./release.sh \
  --from staging \
  --to production \
  --version v1.5.0 \
  --no-cache-warming
```

### Rollback Release

```bash
# 1. Tag previous version as current
docker tag ghcr.io/who-is-caerus/trading-signals-backend:production-v1.4.0 \
           ghcr.io/who-is-caerus/trading-signals-backend:production-latest

# 2. Push rollback tag
docker push ghcr.io/who-is-caerus/trading-signals-backend:production-latest

# 3. Rollback Kubernetes deployment
kubectl --context production-cluster \
  rollout undo deployment/backend

# 4. Rollback database migration (if needed)
cd backend
alembic downgrade -1

# 5. Verify rollback
curl https://api.production.example.com/api/v1/health
```

---

## Disaster Recovery

### Scenario 1: Database Corruption

**Symptoms**: Database queries failing, data inconsistencies

**Recovery Steps**:

```bash
# 1. Take immediate snapshot of corrupted state (for forensics)
./backup.sh --environment production

# 2. Identify last known good backup
aws s3 ls s3://trading-signals-backups/backups/production/ | grep -B 5 $(date -d '1 hour ago' +%Y%m%d)

# 3. Restore to temporary database for verification
export RESTORE_DB_NAME=trading_signals_verify
./restore.sh --environment production --timestamp 20250118_000000 --no-confirm

# 4. Verify data integrity in temporary database
psql -h $DB_HOST -U $DB_USER -d $RESTORE_DB_NAME -c "SELECT COUNT(*) FROM users;"

# 5. If verified, restore to production (CREATE BACKUP FIRST!)
./backup.sh --environment production  # Safety backup
./restore.sh --environment production --timestamp 20250118_000000

# 6. Verify application health
curl https://api.production.example.com/api/v1/health
```

**Estimated Recovery Time**: 15-30 minutes

---

### Scenario 2: Accidental Data Deletion

**Symptoms**: Critical data missing from production database

**Recovery Steps**:

```bash
# 1. IMMEDIATELY stop all write operations
# Pause application or set to read-only mode

# 2. Find backup BEFORE deletion occurred
# Check application logs for deletion timestamp
grep "DELETE FROM users" /var/log/app.log | tail -n 1
# Deletion occurred at: 2025-01-18 14:30:00

# 3. Identify backup taken BEFORE deletion
aws s3 ls s3://trading-signals-backups/backups/production/ | grep 20250118_14

# Backup at 14:00:00 is BEFORE deletion (use this)

# 4. Restore to temporary database
export RESTORE_DB_NAME=trading_signals_recovery
./restore.sh --environment production --timestamp 20250118_140000 --no-confirm

# 5. Extract deleted data
psql -h $DB_HOST -U $DB_USER -d $RESTORE_DB_NAME -c "
  COPY (SELECT * FROM users WHERE id IN ('user1', 'user2'))
  TO '/tmp/recovered_users.csv' CSV HEADER;
"

# 6. Import recovered data to production
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
  COPY users FROM '/tmp/recovered_users.csv' CSV HEADER;
"

# 7. Verify recovery
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT * FROM users WHERE id = 'user1';"

# 8. Resume normal operations
```

**Estimated Recovery Time**: 30-60 minutes

---

### Scenario 3: Complete Database Loss (RDS Failure)

**Symptoms**: Database unreachable, AWS reports outage

**Recovery Steps**:

```bash
# 1. Provision new RDS instance
# (Use AWS Console or Terraform)

# 2. Update DNS/connection strings to point to new instance
export DB_HOST=new-prod-db.example.com

# 3. Restore latest backup
./restore.sh --environment production --timestamp $(date -d '1 hour ago' +%Y%m%d_%H0000)

# 4. Run migrations to ensure schema is current
cd backend
alembic upgrade head

# 5. Update application configuration
kubectl --context production-cluster \
  set env deployment/backend \
  DB_HOST=new-prod-db.example.com

# 6. Verify application connectivity
curl https://api.production.example.com/api/v1/health

# 7. Monitor for errors
kubectl --context production-cluster logs -f deployment/backend
```

**Estimated Recovery Time**: 1-2 hours

**Data Loss**: Up to 1 hour (time since last backup)

---

### Scenario 4: Region-Wide AWS Outage

**Symptoms**: All AWS services in primary region unavailable

**Recovery Steps**:

```bash
# 1. Activate DR region
# Switch DNS to DR region load balancer

# 2. Restore latest cross-region backup
export S3_BUCKET=trading-signals-backups-dr
export S3_REGION=us-west-2
./restore.sh --environment production --timestamp latest

# 3. Update application configuration for DR region
kubectl --context dr-cluster set env deployment/backend \
  AWS_REGION=us-west-2 \
  DB_HOST=dr-prod-db.us-west-2.rds.amazonaws.com

# 4. Run health checks
curl https://api.dr.example.com/api/v1/health

# 5. Communicate with users about region switch
```

**Estimated Recovery Time**: 2-4 hours

**Data Loss**: Up to 4 hours (cross-region replication lag)

---

## Monitoring & Alerts

### Prometheus Metrics

```promql
# Backup success rate (last 24 hours)
rate(backup_success_total{status="success"}[24h])

# Backup failure alert
backup_success_total{status="failed"} > 0

# Backup size trend (detect anomalies)
backup_bytes_total

# Release promotion count
release_promoted_total{status="success"}
```

### Alert Rules

```yaml
# backup-alerts.yml
groups:
  - name: backup_alerts
    interval: 5m
    rules:
      - alert: BackupFailed
        expr: backup_success_total{status="failed"} > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Database backup failed"
          description: "Backup for {{ $labels.environment }} failed. Check logs immediately."
      
      - alert: BackupMissing
        expr: (time() - backup_success_total{status="success"}) > 86400
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "No backup in 24 hours"
          description: "No successful backup for {{ $labels.environment }} in the last 24 hours."
      
      - alert: BackupSizeAnomaly
        expr: |
          (backup_bytes_total - avg_over_time(backup_bytes_total[7d])) / 
          avg_over_time(backup_bytes_total[7d]) > 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Backup size anomaly detected"
          description: "Backup size for {{ $labels.environment }} is 50% larger than 7-day average."
```

### Health Check Endpoints

```bash
# Check if backup completed today
aws s3 ls s3://trading-signals-backups/backups/production/ | grep $(date +%Y%m%d)

# Check backup age
LATEST_BACKUP=$(aws s3 ls s3://trading-signals-backups/backups/production/ --recursive | tail -n 1 | awk '{print $1 " " $2}')
echo "Latest backup: $LATEST_BACKUP"
```

---

## Troubleshooting

### Problem: Backup Script Fails with "pg_dump: command not found"

**Solution**:
```bash
# Install PostgreSQL client tools
sudo apt-get update
sudo apt-get install postgresql-client-15

# Verify installation
pg_dump --version
```

---

### Problem: S3 Upload Fails with "Access Denied"

**Solution**:
```bash
# 1. Verify AWS credentials
aws sts get-caller-identity

# 2. Check S3 bucket permissions
aws s3api get-bucket-policy --bucket trading-signals-backups

# 3. Test S3 write access
echo "test" | aws s3 cp - s3://trading-signals-backups/test.txt
aws s3 rm s3://trading-signals-backups/test.txt
```

---

### Problem: Restore Fails with "Encrypted file verification failed"

**Solution**:
```bash
# 1. Verify encryption key is correct
echo $BACKUP_ENCRYPTION_KEY

# 2. Test decryption manually
openssl enc -d -AES256 \
  -in backup.sql.gz.enc \
  -out backup.sql.gz \
  -k "$BACKUP_ENCRYPTION_KEY"

# 3. If key is lost, restore from unencrypted backup (if available)
```

---

### Problem: Restore Creates Empty Database

**Solution**:
```bash
# 1. Verify backup file is not corrupted
aws s3 cp s3://trading-signals-backups/backups/production/backup.sql.gz.enc /tmp/
sha256sum /tmp/backup.sql.gz.enc

# 2. Check backup file size
ls -lh /tmp/backup.sql.gz.enc

# 3. Manually inspect SQL file
gunzip -c backup.sql.gz | head -n 100

# 4. If corrupted, use previous backup
./restore.sh --environment production --timestamp <earlier_timestamp>
```

---

### Problem: Migration Fails During Promotion

**Solution**:
```bash
# 1. Check Alembic version
cd backend
alembic current

# 2. Check migration history
alembic history

# 3. Run migration manually with verbose output
alembic upgrade head --verbose

# 4. If migration fails, rollback promotion
docker tag registry/image:previous registry/image:current-latest
docker push registry/image:current-latest
```

---

## Emergency Contacts

### On-Call Rotation

- **Primary**: ops-primary@example.com (PagerDuty: +1-555-0001)
- **Secondary**: ops-secondary@example.com (PagerDuty: +1-555-0002)
- **Manager**: ops-manager@example.com

### Escalation Path

1. **Level 1** (0-15 min): On-call engineer
2. **Level 2** (15-30 min): Senior engineer + manager
3. **Level 3** (30+ min): CTO + infrastructure team

### External Vendors

- **AWS Support**: +1-800-123-4567 (Enterprise Support)
- **Database Consultant**: dba@example.com

---

## Appendix

### Backup File Naming Convention

```
{environment}_{database}_{timestamp}.sql.gz.enc

Example:
production_trading_signals_20250118_010000.sql.gz.enc

Components:
- environment: production, staging, development
- database: trading_signals
- timestamp: YYYYMMDD_HHMMSS (UTC)
- .sql: PostgreSQL dump format
- .gz: Gzip compressed
- .enc: Encrypted with AES256
```

### Useful SQL Queries

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size('trading_signals'));

-- Table sizes
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;

-- Row counts for all tables
SELECT 
  schemaname,
  tablename,
  n_live_tup AS row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;

-- Check for long-running transactions
SELECT 
  pid,
  now() - pg_stat_activity.query_start AS duration,
  query,
  state
FROM pg_stat_activity
WHERE state != 'idle'
AND now() - pg_stat_activity.query_start > interval '5 minutes'
ORDER BY duration DESC;
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-18  
**Owner**: Platform Operations Team  
**Review Cycle**: Quarterly
