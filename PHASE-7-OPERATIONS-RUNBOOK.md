# Phase 7: PR-023 Operations Runbook

**Purpose**: Step-by-step procedures for common operational tasks
**Status**: 🟢 PRODUCTION READY
**Last Updated**: October 26, 2025

---

## Table of Contents

1. [Deployment Runbooks](#deployment-runbooks)
2. [Monitoring Runbooks](#monitoring-runbooks)
3. [Troubleshooting Runbooks](#troubleshooting-runbooks)
4. [Emergency Procedures](#emergency-procedures)
5. [Maintenance Runbooks](#maintenance-runbooks)

---

## Deployment Runbooks

### Runbook 1: Fresh Production Deployment

**Time**: 30 minutes
**Difficulty**: Medium
**Prerequisites**: Docker, PostgreSQL 15, Redis 7, .env file configured

**Steps**:

1. **Verify Prerequisites** (3 min)
   ```bash
   # Check Docker
   docker --version
   # Expected: Docker version 20.10+

   # Check PostgreSQL connectivity
   psql -U bot -h prod-db -d postgres -c "SELECT version();"

   # Check Redis connectivity
   redis-cli -h prod-redis ping
   # Expected: PONG
   ```

2. **Initialize Database** (5 min)
   ```bash
   # Run migrations
   .venv/Scripts/python.exe -m alembic upgrade head

   # Verify tables created
   psql -d bot_production -c "\dt"
   # Expected: See reconciliation_logs, positions, users, audit_logs, signals, approvals

   # Verify indexes
   psql -d bot_production -c "\di"
   # Expected: See ix_reconciliation_user_created, ix_positions_user_id, etc.
   ```

3. **Start Application** (5 min)
   ```bash
   # Start all services
   docker-compose -f docker-compose.production.yml up -d

   # Verify services are running
   docker-compose ps
   # Expected: All services have "Up" status

   # Check logs for startup issues
   docker logs api | tail -20
   # Expected: "Uvicorn running on 0.0.0.0:8000"
   ```

4. **Health Checks** (5 min)
   ```bash
   # Test health endpoint
   curl -i http://localhost:8000/api/v1/health
   # Expected: 200 OK, JSON with status="healthy"

   # Test readiness
   curl -i http://localhost:8000/api/v1/ready
   # Expected: 200 OK, all checks passing

   # Test cache readiness
   curl -i http://localhost:8000/api/v1/ready | jq '.checks.redis'
   # Expected: "ready"
   ```

5. **Run Smoke Tests** (7 min)
   ```bash
   # Run basic endpoint tests
   pytest backend/tests/test_pr_023_phase5_routes.py::TestHealthCheckEndpoint -v
   # Expected: 2/2 PASSING

   # Run auth validation
   pytest backend/tests/test_pr_023_phase5_routes.py::TestReconciliationStatusEndpoint::test_get_reconciliation_status_without_auth -v
   # Expected: 1/1 PASSING
   ```

6. **Document Deployment** (2 min)
   ```bash
   # Record deployment info
   echo "
   Deployment: $(date)
   Image: $(docker images | grep bot-api | head -1)
   Database: $(psql -d bot_production -c "SELECT count(*) FROM users;")
   " >> /var/log/deployments.log
   ```

**Rollback** (if needed):
```bash
docker-compose down
docker pull bot-api:phase-5
docker-compose -f docker-compose.production.yml up -d
```

---

### Runbook 2: Blue-Green Deployment (Zero Downtime)

**Time**: 20 minutes
**Difficulty**: Advanced
**Prerequisites**: Load balancer (nginx), two API instances

**Steps**:

1. **Prepare Green Environment** (8 min)
   ```bash
   # Pull new image
   docker pull bot-api:latest

   # Start green instance on port 8001
   docker run -d \
     --name api-green \
     -p 8001:8000 \
     -e DATABASE_URL=$DATABASE_URL \
     -e REDIS_URL=$REDIS_URL \
     bot-api:latest

   # Wait for startup
   sleep 10
   ```

2. **Verify Green Health** (5 min)
   ```bash
   # Run health checks on green
   curl -i http://localhost:8001/api/v1/health
   # Expected: 200 OK

   # Run smoke tests on green
   pytest backend/tests/test_pr_023_phase5_routes.py::TestHealthCheckEndpoint -v
   # Expected: PASSING
   ```

3. **Switch Traffic** (2 min)
   ```bash
   # Update nginx upstream to point to green
   # Edit nginx.conf:
   # upstream api {
   #   server localhost:8001;  # was 8000
   # }

   # Reload nginx
   nginx -s reload

   # Verify traffic switched
   curl http://localhost/api/v1/health
   # Should respond from green instance
   ```

4. **Monitor Green** (3 min)
   ```bash
   # Watch logs
   docker logs -f api-green | grep -i "error\|warning"

   # Monitor latency
   watch -n 1 'curl -w "%{time_total}\n" -o /dev/null http://localhost:8001/api/v1/health'
   ```

5. **Keep Blue as Standby** (2 min)
   ```bash
   # Stop but don't remove old instance
   docker stop api

   # Quick rollback: docker stop api-green && docker start api
   ```

**Rollback** (if needed):
```bash
# Switch traffic back
# Edit nginx.conf to point to port 8000
nginx -s reload

# Verify
curl http://localhost/api/v1/health
```

---

## Monitoring Runbooks

### Runbook 3: Daily Health Check

**Time**: 5 minutes
**Frequency**: Every morning (08:00 UTC)
**Owner**: Operations team

**Steps**:

1. **Service Status** (1 min)
   ```bash
   docker-compose ps
   ```
   **Success**: All services show "Up"
   **Action if Failed**: Run Runbook 8 (Emergency Container Restart)

2. **Response Time Check** (1 min)
   ```bash
   curl -w "Time: %{time_total}s\n" -o /dev/null http://localhost:8000/api/v1/health
   ```
   **Success**: < 100ms
   **Action if Failed**: Run Runbook 4 (Performance Diagnosis)

3. **Error Rate** (1 min)
   ```bash
   curl -s http://localhost:8000/metrics | grep 'errors_total{' | head -5
   ```
   **Success**: All values show < 10 (low absolute errors)
   **Action if Failed**: Run Runbook 6 (Error Investigation)

4. **Cache Health** (1 min)
   ```bash
   redis-cli INFO stats | grep hits_percentage
   ```
   **Success**: > 70% (warmed up) or > 40% (early morning)
   **Action if Failed**: Run Runbook 9 (Cache Troubleshooting)

5. **Database Check** (1 min)
   ```bash
   psql -d bot_production -c "SELECT now();"
   ```
   **Success**: Returns current timestamp
   **Action if Failed**: Run Runbook 10 (Database Troubleshooting)

**Report Template**:
```
[DATE] Daily Health Check
✅ Services: All running
✅ Response Time: 15ms
✅ Error Rate: 0.1%
✅ Cache Hit Rate: 82%
✅ Database: Healthy
Status: PASS
```

---

### Runbook 4: Performance Diagnosis

**Time**: 15 minutes
**Triggers**: P95 latency > 50ms, user complaints about slowness

**Steps**:

1. **Measure Current Latency** (2 min)
   ```bash
   # Run 10 requests and measure
   for i in {1..10}; do
     curl -w "%{time_total}\n" -o /dev/null \
       http://localhost:8000/api/v1/reconciliation/status
   done
   ```
   **Expected**: 10-50ms (with cache hits)

2. **Check Cache Hit Rate** (2 min)
   ```bash
   # Get before metrics
   BEFORE=$(redis-cli INFO stats | grep total_commands_processed)

   # Wait 30 seconds
   sleep 30

   # Get after metrics
   AFTER=$(redis-cli INFO stats | grep total_commands_processed)

   # Low hit rate = cache issue
   ```

3. **Check Database Load** (2 min)
   ```bash
   psql -d bot_production -c "SELECT count(*) FROM pg_stat_activity WHERE state='active';"
   ```
   **Normal**: < 5 active queries
   **High Load**: > 10 active queries → scale database

4. **Check Application Load** (3 min)
   ```bash
   docker stats api
   ```
   **Normal**: CPU < 50%, Memory < 500MB
   **High Load**: CPU > 80% or Memory > 1GB → scale API

5. **Check Redis Memory** (2 min)
   ```bash
   redis-cli INFO memory | grep used_memory_human
   ```
   **Normal**: < 100MB
   **Warning**: > 500MB → clear old cache entries

6. **Decision Tree**:
   ```
   Is P95 latency > 100ms?
   ├─ NO (< 50ms): ✅ PASS, continue monitoring
   ├─ YES (50-100ms): Check cache hit rate
   │  ├─ Low (< 60%): Run Runbook 9 (Cache Fix)
   │  └─ High (> 80%): Check database
   │     ├─ High load: Scale database (add replicas)
   │     └─ Normal: Scale API instances
   └─ YES (> 100ms): CRITICAL
      └─ Run Runbook 8 (Emergency Restart)
   ```

---

### Runbook 5: Capacity Planning Review

**Time**: 30 minutes
**Frequency**: Weekly on Monday
**Owner**: Infrastructure team

**Steps**:

1. **Collect Metrics** (10 min)
   ```bash
   # Get weekly averages from Prometheus
   curl 'http://prometheus:9090/api/v1/query' \
     --data-urlencode 'query=avg_over_time(http_requests_in_progress[1w])'

   # Get database stats
   psql -d bot_production -c "
     SELECT
       COUNT(*) as total_queries,
       AVG(query_duration_ms) as avg_duration
     FROM pg_stat_queries
     WHERE query_time > now() - interval '1 week';
   "
   ```

2. **Analyze Trends** (10 min)
   - Peak concurrent users: ____ (target: 100)
   - P95 latency: ____ (target: < 50ms)
   - Error rate: ____ (target: < 1%)
   - Cache hit rate: ____ (target: > 80%)
   - Database CPU: ____ (target: < 60%)

3. **Capacity Decision** (10 min)
   ```
   If any metric exceeds target:
   - Scale API: Add more instances (horizontal)
   - Scale Database: Add read replicas or increase resources (vertical)
   - Scale Cache: Increase Redis memory or instances

   Document decision and implement
   ```

---

## Troubleshooting Runbooks

### Runbook 6: High Error Rate (> 1%)

**Time**: 10 minutes
**Severity**: 🔴 CRITICAL

**Steps**:

1. **Identify Error Type** (2 min)
   ```bash
   curl -s http://localhost:8000/metrics | grep errors_total | head -10
   ```
   **Example output**:
   ```
   errors_total{status="500"} 15
   errors_total{status="401"} 2
   errors_total{status="503"} 1
   ```

2. **Check Application Logs** (3 min)
   ```bash
   # Get last 50 error lines
   docker logs api | grep -i "error\|exception" | tail -50
   ```
   **Look for**:
   - Database connection errors
   - JWT validation errors
   - Redis connection errors
   - Timeout errors

3. **By Error Type**:

   **If 500 errors**:
   ```bash
   # Check database connectivity
   psql -d bot_production -c "SELECT 1;"

   # If fails: Restart database
   docker restart db
   ```

   **If 401 errors**:
   ```bash
   # Check JWT configuration
   echo $JWT_SECRET_KEY

   # If empty: Set environment variable
   export JWT_SECRET_KEY=<your-secret>
   docker restart api
   ```

   **If 503 errors**:
   ```bash
   # Service unavailable = resource exhausted
   docker stats api

   # If CPU/Memory high: Restart
   docker restart api

   # If still high: Scale up
   docker-compose up -d --scale api=4
   ```

4. **Monitor Fix** (5 min)
   ```bash
   # Watch error rate decline
   watch -n 1 'curl -s http://localhost:8000/metrics | grep "errors_total{status=\"500\"}"'
   ```
   **Success**: Error count stops increasing

---

### Runbook 7: Slow Database (Queries > 1 second)

**Time**: 15 minutes
**Severity**: 🟡 WARNING

**Steps**:

1. **Find Slow Queries** (3 min)
   ```bash
   psql -d bot_production -c "
     SELECT
       query,
       calls,
       total_time,
       mean_time
     FROM pg_stat_statements
     WHERE mean_time > 1000  -- > 1 second
     ORDER BY mean_time DESC;
   " | head -10
   ```

2. **Analyze Query** (3 min)
   ```bash
   # Example: reconciliation_logs query
   EXPLAIN ANALYZE
   SELECT * FROM reconciliation_logs
   WHERE user_id = 'user-123'
   ORDER BY created_at DESC
   LIMIT 100;
   ```
   **Look for**: Sequential scans (should use indexes)

3. **Apply Fix**:

   **If missing index**:
   ```bash
   psql -d bot_production -c "
     CREATE INDEX IF NOT EXISTS ix_reconciliation_user_created
     ON reconciliation_logs(user_id, created_at DESC);
   "
   ```

   **If index unused**:
   ```bash
   # Analyze table
   ANALYZE reconciliation_logs;

   # Re-run explain
   EXPLAIN ANALYZE SELECT ...;
   ```

4. **Verify Fix** (3 min)
   ```bash
   # Re-run query
   EXPLAIN ANALYZE SELECT * FROM reconciliation_logs WHERE user_id = 'user-123' LIMIT 100;
   ```
   **Success**: Index used, execution time < 100ms

---

### Runbook 8: Emergency Container Restart

**Time**: 5 minutes
**Severity**: 🔴 CRITICAL
**Use When**: Unresponsive service, memory leak, stuck process

**Steps**:

1. **Stop Service** (1 min)
   ```bash
   docker-compose stop api
   ```

2. **Wait** (1 min)
   ```bash
   sleep 60
   ```

3. **Start Service** (1 min)
   ```bash
   docker-compose up -d api
   ```

4. **Verify** (2 min)
   ```bash
   docker-compose ps
   curl http://localhost:8000/api/v1/health
   ```
   **Success**: Service responding, health check green

**If Still Not Working**:
- Go to Runbook 12 (Full System Recovery)

---

### Runbook 9: Cache Troubleshooting

**Time**: 10 minutes
**Trigger**: Cache hit rate < 60% or Redis errors in logs

**Steps**:

1. **Check Redis Status** (2 min)
   ```bash
   redis-cli ping
   # Expected: PONG

   redis-cli INFO
   # Look for: connected_clients, used_memory, evicted_keys
   ```

2. **Check Cache Keys** (2 min)
   ```bash
   redis-cli KEYS "prod_*" | wc -l
   # Expected: > 100 keys

   redis-cli DBSIZE
   # Expected: > 100 keys in database
   ```

3. **Clear Cache** (1 min)
   ```bash
   redis-cli FLUSHDB
   ```

4. **Warm Cache** (3 min)
   ```bash
   # Run requests to populate cache
   for i in {1..10}; do
     curl -s http://localhost:8000/api/v1/reconciliation/status > /dev/null
   done

   # Check hit rate improved
   redis-cli INFO stats | grep hits_percentage
   ```

5. **Monitor** (2 min)
   ```bash
   watch -n 2 'redis-cli INFO stats | grep -E "hits|misses"'
   ```
   **Success**: Hit rate increasing

---

### Runbook 10: Database Troubleshooting

**Time**: 15 minutes
**Trigger**: Database connection errors, slow queries

**Steps**:

1. **Test Connection** (2 min)
   ```bash
   psql -U bot -h prod-db -d bot_production -c "SELECT 1;"
   ```
   **If fails**: Check credentials and network

2. **Check Connections** (2 min)
   ```bash
   psql -d bot_production -c "SELECT count(*) FROM pg_stat_activity;"
   # If > 20: Connection pool exhausted
   ```

3. **Check Disk Space** (2 min)
   ```bash
   # In database container
   docker exec db df -h
   # If < 10% free: Clean up or expand volume
   ```

4. **Analyze Slow Queries** (5 min)
   - See Runbook 7

5. **Restart If Needed** (2 min)
   ```bash
   docker restart db
   sleep 10

   # Verify
   psql -d bot_production -c "SELECT 1;"
   ```

---

## Emergency Procedures

### Runbook 11: Major Incident Response

**Time**: 30 minutes
**Severity**: 🔴 CRITICAL
**Trigger**: System down, data loss, security breach

**Escalation Path**:
```
1. Declare Incident (Incident Commander)
2. Assemble Team (Backend lead, DBA, DevOps)
3. Investigate (Run Runbook 12)
4. Communicate (Status page, user notifications)
5. Fix (Apply emergency patches)
6. Verify (Full test suite)
7. Post-Mortem (What went wrong, prevention)
```

**Steps**:

1. **Declare Emergency** (1 min)
   ```bash
   # Post to #incident-response Slack channel
   # "🔴 INCIDENT DECLARED: [Description]"
   # Assign Incident Commander
   # Assign Communications Lead
   ```

2. **Immediate Assessment** (5 min)
   - What's down? (API, Database, Cache)
   - How many users affected?
   - What's the impact? (no trading, slow trading, data loss)
   - When did it start?

3. **Triage** (5 min)
   - Run Runbook 12 (Full System Recovery) if applicable
   - Check backups available
   - Prepare for rollback

4. **Execute Fix** (15 min)
   - Document every action
   - Have second person review
   - Deploy carefully
   - Monitor closely

5. **Communicate Status** (ongoing)
   - Every 5 minutes to affected teams
   - Every 10 minutes to users (if applicable)
   - Final update when resolved

6. **Post-Mortem** (next day)
   - Root cause analysis
   - Prevention measures
   - Update playbooks
   - Communication review

---

### Runbook 12: Full System Recovery

**Time**: 45 minutes
**Use When**: Complete system failure, cascading errors

**Steps**:

1. **Stop Everything** (2 min)
   ```bash
   docker-compose down
   ```

2. **Check Data Integrity** (5 min)
   ```bash
   # Verify database backup exists
   ls -lh /backups/db_*.sql.gz | tail -1

   # Verify backup is valid
   gunzip -t /backups/db_20251026.sql.gz
   # Expected: No output (valid)
   ```

3. **Restore Database** (10 min)
   ```bash
   docker-compose up -d db
   sleep 30

   # Restore from backup
   gunzip < /backups/db_20251026.sql.gz | \
     psql -U bot -h localhost -d bot_production

   # Verify
   psql -d bot_production -c "SELECT count(*) FROM reconciliation_logs;"
   ```

4. **Start Cache** (2 min)
   ```bash
   docker-compose up -d cache

   # Verify
   redis-cli ping
   # Expected: PONG
   ```

5. **Start API** (5 min)
   ```bash
   docker-compose up -d api

   # Wait for startup
   sleep 15

   # Check logs
   docker logs api | tail -20
   ```

6. **Run Health Checks** (10 min)
   ```bash
   # Health endpoints
   curl http://localhost:8000/api/v1/health
   curl http://localhost:8000/api/v1/ready

   # Run tests
   pytest backend/tests/test_pr_023_phase5_routes.py::TestHealthCheckEndpoint -v
   ```

7. **Verify Data** (10 min)
   ```bash
   # Check critical tables
   psql -d bot_production -c "
     SELECT 'users' as table_name, count(*) as rows FROM users
     UNION ALL
     SELECT 'signals', count(*) FROM signals
     UNION ALL
     SELECT 'approvals', count(*) FROM approvals
     UNION ALL
     SELECT 'reconciliation_logs', count(*) FROM reconciliation_logs;
   "
   ```

**Success**: All services up, data restored, tests passing

---

## Maintenance Runbooks

### Runbook 13: Database Maintenance (Monthly)

**Time**: 30 minutes
**Frequency**: First Sunday of month, 02:00 UTC

**Steps**:

1. **Vacuum Database** (10 min)
   ```bash
   psql -d bot_production -c "VACUUM ANALYZE;"
   ```

2. **Reindex** (10 min)
   ```bash
   psql -d bot_production -c "REINDEX DATABASE bot_production;"
   ```

3. **Check Table Sizes** (5 min)
   ```bash
   psql -d bot_production -c "
     SELECT
       schemaname,
       tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
     FROM pg_tables
     WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
     ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   "
   ```

4. **Archive Old Logs** (5 min)
   ```bash
   psql -d bot_production -c "
     INSERT INTO reconciliation_logs_archive
     SELECT * FROM reconciliation_logs
     WHERE created_at < now() - interval '90 days';

     DELETE FROM reconciliation_logs
     WHERE created_at < now() - interval '90 days';
   "
   ```

---

### Runbook 14: Cache Optimization (Weekly)

**Time**: 15 minutes
**Frequency**: Every Wednesday 03:00 UTC

**Steps**:

1. **Check Memory Usage** (2 min)
   ```bash
   redis-cli INFO memory | grep -E "used_memory|maxmemory"
   ```

2. **Set Eviction Policy** (2 min)
   ```bash
   redis-cli CONFIG SET maxmemory-policy allkeys-lru
   ```

3. **Monitor Hit Rate** (3 min)
   ```bash
   redis-cli INFO stats | grep -E "hits|misses"
   ```

4. **Clear Unused Keys** (3 min)
   ```bash
   # Remove keys not accessed in 24 hours
   redis-cli SCAN 0 | while read key; do
     TTL=$(redis-cli TTL "$key")
     if [ $TTL -eq -1 ]; then
       redis-cli EXPIRE "$key" 3600
     fi
   done
   ```

5. **Rebuild Index** (5 min)
   ```bash
   redis-cli BGSAVE
   ```

---

**Emergency Contact**: [Your Name] @ [phone/email]
**Escalation**: [Manager Name] @ [email]
**Incident Channel**: #incident-response
