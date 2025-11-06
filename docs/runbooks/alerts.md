# Operational Runbook: Alert Response Procedures

## Table of Contents
- [Alert Severity Levels](#alert-severity-levels)
- [General Escalation Path](#general-escalation-path)
- [API Health Alerts](#api-health-alerts)
- [Business Health Alerts](#business-health-alerts)
- [Infrastructure Alerts](#infrastructure-alerts)

---

## Alert Severity Levels

| Severity | Response Time | Description | Example |
|----------|---------------|-------------|---------|
| **Critical** | 5 minutes | Service degradation or revenue impact | Payment failures, API down, DB disconnected |
| **Warning** | 30 minutes | Performance degradation or potential issue | High latency, elevated error rate |
| **Info** | Best effort | Informational, no immediate action | Config changes, deployments |

---

## General Escalation Path

1. **On-Call Engineer** (Primary): Responds within SLA, investigates, mitigates
2. **Senior Engineer** (Secondary): Escalate if issue unresolved after 30 minutes
3. **Engineering Manager**: Escalate for revenue-impacting incidents (payment failures, billing outages)
4. **CTO**: Escalate for critical incidents affecting >50% of users

**Escalation Channels**:
- PagerDuty: For critical alerts
- Slack: `#oncall-alerts` (all alerts), `#incident-response` (active incidents)
- Email: oncall@example.com

---

## API Health Alerts

### HighAPILatency / CriticalAPILatency

**Symptoms**:
- p95 API latency > 1 second (warning) or > 5 seconds (critical)
- User complaints about slow dashboard loads
- Increased timeout errors

**Investigation**:
1. Check Grafana dashboard: Identify which endpoints are slow
   ```bash
   # Query top slow endpoints
   curl -s "http://localhost:9090/api/v1/query?query=topk(5, histogram_quantile(0.95, sum(rate(request_duration_seconds_bucket[5m])) by (le, route)))"
   ```

2. Check database connection pool:
   ```bash
   # Check pool size
   curl -s "http://localhost:9090/api/v1/query?query=db_connection_pool_size"
   ```

3. Check database query latency:
   ```bash
   # Check slow queries
   curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))"
   ```

4. Check Redis connection:
   ```bash
   # Check Redis status
   curl -s "http://localhost:9090/api/v1/query?query=redis_connected"
   ```

5. Check external API latency (if using third-party services):
   ```bash
   # Check backend logs for external API calls
   docker logs backend | grep "external_api" | tail -n 50
   ```

**Remediation**:
- **Database slow**: Scale up DB instance, add indexes, optimize queries
- **Connection pool exhausted**: Increase pool size in config, restart backend
- **Redis down**: Restart Redis service, check network connectivity
- **External API slow**: Enable circuit breaker, use cached responses, contact vendor
- **General overload**: Scale horizontally (add backend replicas)

**Example Commands**:
```bash
# Scale backend replicas (Kubernetes)
kubectl scale deployment backend --replicas=5

# Increase DB connection pool (update config, restart)
# In backend/.env
DB_POOL_SIZE=50
docker-compose restart backend

# Restart Redis
docker-compose restart redis
```

**Escalation**:
- If latency > 10 seconds for > 10 minutes: Escalate to Senior Engineer
- If revenue-impacting (billing, payments): Escalate to Engineering Manager

---

### HighErrorRate / CriticalErrorRate

**Symptoms**:
- Error rate > 0.1 errors/sec (warning) or > 1 error/sec (critical)
- Increased 4xx/5xx HTTP responses
- User reports of "something went wrong" errors

**Investigation**:
1. Check which endpoints are failing:
   ```bash
   # Query error rate by endpoint
   curl -s "http://localhost:9090/api/v1/query?query=topk(5, sum(rate(errors_total[5m])) by (endpoint, status))"
   ```

2. Check backend logs for error details:
   ```bash
   # Check recent errors
   docker logs backend --since 10m | grep "ERROR"

   # Check specific endpoint errors
   docker logs backend --since 10m | grep "/api/v1/signals" | grep "ERROR"
   ```

3. Check database errors:
   ```bash
   # Check for DB connection errors
   docker logs backend | grep "database" | grep "ERROR"
   ```

4. Check if errors are authentication-related:
   ```bash
   # Query auth failures
   curl -s "http://localhost:9090/api/v1/query?query=rate(auth_login_total{result=\"failure\"}[5m])"
   ```

**Remediation**:
- **500 errors (server-side)**: Check backend logs, fix bugs, deploy hotfix
- **400 errors (client-side)**: Check if recent frontend deployment broke API contract
- **401 errors (auth)**: Check JWT expiry, Redis session cache, auth service
- **Database errors**: Check DB connectivity, query syntax, schema migrations
- **Dependency failures**: Check external API status, enable circuit breakers

**Example Commands**:
```bash
# Rollback to previous deployment (if recent deploy caused issue)
kubectl rollout undo deployment/backend

# Restart backend (if transient issue)
docker-compose restart backend

# Check database connectivity
docker exec backend python -c "from backend.app.core.db import engine; print(engine.connect())"
```

**Escalation**:
- If error rate > 5 errors/sec: Escalate immediately to Senior Engineer
- If revenue-impacting: Escalate to Engineering Manager

---

### DatabaseConnectionPoolExhausted

**Symptoms**:
- DB connection pool size > 90
- "Connection pool exhausted" errors in logs
- Slow database queries, timeouts

**Investigation**:
1. Check current pool size:
   ```bash
   curl -s "http://localhost:9090/api/v1/query?query=db_connection_pool_size"
   ```

2. Check for long-running queries:
   ```sql
   -- Connect to PostgreSQL
   docker exec -it postgres psql -U postgres -d trading_signals

   -- Check active connections
   SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

   -- Check long-running queries
   SELECT pid, now() - query_start AS duration, query
   FROM pg_stat_activity
   WHERE state = 'active'
   ORDER BY duration DESC
   LIMIT 10;
   ```

3. Check if connections are being leaked (not closed):
   ```bash
   # Check backend logs for connection warnings
   docker logs backend | grep "connection" | grep -E "leak|timeout|exhausted"
   ```

**Remediation**:
1. **Immediate**: Increase pool size
   ```bash
   # Update backend/.env
   DB_POOL_SIZE=100
   docker-compose restart backend
   ```

2. **Short-term**: Kill long-running queries
   ```sql
   -- Kill specific query (use PID from above)
   SELECT pg_terminate_backend(12345);
   ```

3. **Long-term**: Fix connection leaks in code
   - Ensure all DB sessions use `async with` context manager
   - Add connection timeout to SQLAlchemy config
   - Review code for unclosed connections

**Escalation**:
- If pool exhaustion persists after restart: Escalate to Senior Engineer
- If database performance degraded: Contact DBA or database vendor

---

### RedisDisconnected

**Symptoms**:
- Redis connection status = 0
- Session authentication failures
- Cache misses at 100%

**Investigation**:
1. Check Redis process:
   ```bash
   docker ps | grep redis
   docker logs redis --since 5m
   ```

2. Check Redis connectivity:
   ```bash
   docker exec redis redis-cli ping
   # Expected: PONG
   ```

3. Check Redis memory usage:
   ```bash
   docker exec redis redis-cli info memory
   ```

**Remediation**:
1. **Redis crashed**: Restart Redis
   ```bash
   docker-compose restart redis
   ```

2. **Redis out of memory**: Increase memory limit or enable eviction policy
   ```bash
   # Update docker-compose.yml
   redis:
     command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
   docker-compose restart redis
   ```

3. **Network issue**: Check network connectivity, firewall rules

**Escalation**:
- If Redis cannot be restarted: Escalate to Senior Engineer
- If data loss suspected: Escalate to Engineering Manager

---

## Business Health Alerts

### SignalIngestionStopped

**Symptoms**:
- No signals ingested for 10+ minutes
- Signal ingestion rate = 0
- Users not receiving trade notifications

**Investigation**:
1. Check signal generation service status:
   ```bash
   # Check if signal service is running
   docker ps | grep signal-generator

   # Check signal service logs
   docker logs signal-generator --since 10m
   ```

2. Check if signals are being created in database:
   ```sql
   -- Connect to database
   docker exec -it postgres psql -U postgres -d trading_signals

   -- Check recent signals
   SELECT COUNT(*), MAX(created_at)
   FROM signals
   WHERE created_at > NOW() - INTERVAL '10 minutes';
   ```

3. Check external signal source (if applicable):
   ```bash
   # Check logs for external API calls
   docker logs backend | grep "signal_source" | tail -n 50
   ```

4. Check approval queue:
   ```bash
   # Check if signals are stuck in approval
   curl http://localhost:8000/api/v1/approvals?status=pending
   ```

**Remediation**:
- **Signal service crashed**: Restart signal generation service
  ```bash
  docker-compose restart signal-generator
  ```

- **Database connectivity issue**: Check DB connection, restart backend
  ```bash
  docker-compose restart backend
  ```

- **External API down**: Check vendor status page, enable fallback signal source

- **Approval queue blocked**: Clear stuck approvals, check approval service

**Escalation**:
- If signal ingestion not restored within 15 minutes: Escalate to Senior Engineer
- Critical for revenue: Escalate to Engineering Manager

---

### PaymentWebhookFailures

**Symptoms**:
- Webhook replay attack rate > 0.1/sec
- Invalid webhook signatures
- Payment processing failures

**Investigation**:
1. Check webhook logs:
   ```bash
   # Check recent webhook events
   docker logs backend | grep "webhook" | tail -n 100

   # Check specific replay attacks
   docker logs backend | grep "replay_attack" | tail -n 50
   ```

2. Check Stripe webhook dashboard:
   - Go to Stripe Dashboard → Developers → Webhooks
   - Check recent webhook deliveries
   - Look for failed deliveries or signature mismatches

3. Check idempotency cache:
   ```bash
   # Check Redis for idempotency keys
   docker exec redis redis-cli KEYS "idempotent:*" | wc -l
   ```

4. Check webhook signature verification:
   ```bash
   # Check for invalid signatures
   docker logs backend | grep "invalid_signature" | tail -n 50
   ```

**Remediation**:
1. **Replay attacks**: Verify idempotency keys are working
   - Check Redis is running and connected
   - Verify TTL on idempotency keys (should be 24 hours)
   ```bash
   docker exec redis redis-cli TTL "idempotent:checkout_session_12345"
   ```

2. **Invalid signatures**: Verify webhook secret is correct
   ```bash
   # Check webhook secret in environment
   docker exec backend printenv | grep STRIPE_WEBHOOK_SECRET

   # Compare with Stripe dashboard webhook secret
   # Update if mismatch:
   # 1. Copy secret from Stripe Dashboard
   # 2. Update backend/.env
   # 3. Restart backend
   docker-compose restart backend
   ```

3. **Webhook delivery failures**: Check webhook endpoint accessibility
   ```bash
   # Test webhook endpoint locally
   curl -X POST http://localhost:8000/api/v1/billing/webhook \
     -H "Content-Type: application/json" \
     -d '{"type":"test"}'
   ```

**Escalation**:
- If payment processing remains broken: Escalate immediately to Engineering Manager (revenue impact)
- If security issue suspected (real attacks): Escalate to Security Team

---

### EAPollErrors

**Symptoms**:
- EA error rate > 0.5 errors/sec
- EA poll/ack endpoints returning errors
- MT5 EAs not receiving signals

**Investigation**:
1. Check EA error types:
   ```bash
   # Query error breakdown
   curl -s "http://localhost:9090/api/v1/query?query=sum(rate(ea_errors_total[5m])) by (endpoint, error_type)"

   # Check logs for specific errors
   docker logs backend | grep "ea_errors" | tail -n 50
   ```

2. Check device registration status:
   ```bash
   # Query device registry
   curl http://localhost:8000/api/v1/devices?status=active
   ```

3. Check HMAC validation failures:
   ```bash
   # Check for signature errors
   docker logs backend | grep "HMAC" | grep "invalid" | tail -n 50
   ```

4. Check nonce cache (replay protection):
   ```bash
   # Check Redis for nonce keys
   docker exec redis redis-cli KEYS "nonce:*" | wc -l

   # Check nonce TTL
   docker exec redis redis-cli TTL "nonce:device123_456789"
   ```

**Remediation**:
- **auth_failed errors**: User needs to re-register device in Mini App
  - Guide user to revoke and re-register device
  - Check device registry for stale devices

- **invalid_signature errors**: Check shared secret synchronization
  ```bash
  # Verify device secrets in database match client
  docker exec -it postgres psql -U postgres -d trading_signals
  SELECT device_id, created_at FROM devices WHERE user_id = 'USER_ID';
  ```

- **nonce replay errors**: Verify Redis nonce cache working
  - Check Redis connectivity
  - Verify nonce TTL is appropriate (default: 5 minutes)

- **timeout errors**: EA may be polling too frequently, check rate limiting
  ```bash
  # Check rate limit rejections
  curl -s "http://localhost:9090/api/v1/query?query=rate(ratelimit_block_total{route=\"/ea/poll\"}[5m])"
  ```

**Escalation**:
- If EA errors affect >10% of users: Escalate to Senior Engineer
- If systematic issue (all EAs failing): Escalate immediately to Engineering Manager

---

### HighApprovalRejectionRate

**Symptoms**:
- > 70% of signals being rejected by users
- Low approval rate indicates signal quality issues

**Investigation**:
1. Check rejection rate by signal source:
   ```bash
   # Query approvals by source
   curl -s "http://localhost:9090/api/v1/query?query=sum(rate(approvals_total[5m])) by (result)"
   ```

2. Check recent signals:
   ```sql
   -- Connect to database
   docker exec -it postgres psql -U postgres -d trading_signals

   -- Check recent signals and approval rate
   SELECT s.instrument, s.side,
          COUNT(*) as total,
          SUM(CASE WHEN a.decision = 1 THEN 1 ELSE 0 END) as approved,
          SUM(CASE WHEN a.decision = 0 THEN 1 ELSE 0 END) as rejected
   FROM signals s
   LEFT JOIN approvals a ON s.id = a.signal_id
   WHERE s.created_at > NOW() - INTERVAL '1 hour'
   GROUP BY s.instrument, s.side
   ORDER BY rejected DESC;
   ```

3. Check signal quality metrics (if available):
   - Win rate of recently approved signals
   - Volatility/risk levels
   - Market conditions (trending vs ranging)

**Remediation**:
- **Poor signal quality**: Review signal generation algorithm
  - Adjust entry criteria (RSI, moving averages, etc.)
  - Filter low-quality signals before presenting to users
  - Consult trading strategy team

- **User education**: Some users may be overly conservative
  - Send educational content about signal interpretation
  - Provide signal performance statistics

- **Market conditions**: High rejection normal during volatile/uncertain markets
  - Monitor market volatility indices (VIX, etc.)
  - Adjust signal generation for current market regime

**Escalation**:
- If rejection rate persists > 80% for > 1 hour: Escalate to Product/Trading Team
- If signal quality systematically poor: Escalate to Engineering Manager + Trading Team

---

## Infrastructure Alerts

### HighRateLimitRejections

**Symptoms**:
- Rate limit rejections > 10/sec on specific route
- Users receiving 429 Too Many Requests errors

**Investigation**:
1. Check which endpoints are being rate limited:
   ```bash
   curl -s "http://localhost:9090/api/v1/query?query=topk(5, sum(rate(ratelimit_block_total[5m])) by (route))"
   ```

2. Check if legitimate traffic or abuse:
   ```bash
   # Check backend logs for rate limit events
   docker logs backend | grep "rate_limit" | tail -n 100

   # Check source IPs (if logged)
   docker logs backend | grep "rate_limit" | grep -oP 'ip=\K[^ ]+' | sort | uniq -c | sort -rn
   ```

3. Check current rate limit configuration:
   ```bash
   # Check rate limit settings
   docker exec backend printenv | grep RATE_LIMIT
   ```

**Remediation**:
- **Legitimate traffic spike**: Increase rate limits temporarily
  ```bash
  # Update backend/.env
  RATE_LIMIT_PER_MINUTE=120
  docker-compose restart backend
  ```

- **Bot/scraper abuse**: Block abusive IPs
  ```bash
  # Add IP to firewall blacklist
  ufw deny from 192.168.1.100
  ```

- **DDoS attack**: Enable DDoS protection (Cloudflare, AWS Shield)

**Escalation**:
- If DDoS suspected: Escalate to Infrastructure/Security Team immediately

---

## Post-Incident Actions

After resolving any **Critical** alert:

1. **Write incident report** (within 24 hours):
   - Timeline of events
   - Root cause analysis
   - Remediation steps taken
   - Preventive measures (how to avoid in future)

2. **Update runbook** (if new procedure discovered):
   - Add new investigation steps
   - Document new remediation commands
   - Update escalation paths if needed

3. **Post-mortem meeting** (for critical incidents):
   - Review timeline with team
   - Identify process improvements
   - Assign follow-up tasks (code fixes, monitoring improvements)

4. **Update monitoring** (if alert was noisy or missed real issue):
   - Adjust alert thresholds
   - Add new metrics if gaps discovered
   - Improve alert descriptions

---

## Useful Commands Reference

### Prometheus Queries
```bash
# Query API (replace localhost with Prometheus host)
PROM_URL="http://localhost:9090"

# Current metric value
curl -s "$PROM_URL/api/v1/query?query=redis_connected"

# Metric over time range
curl -s "$PROM_URL/api/v1/query_range?query=rate(http_requests_total[5m])&start=$(date -u -d '1 hour ago' +%s)&end=$(date -u +%s)&step=60s"

# Top N values
curl -s "$PROM_URL/api/v1/query?query=topk(5, sum(rate(errors_total[5m])) by (endpoint))"
```

### Docker Commands
```bash
# Check service status
docker ps
docker-compose ps

# View logs
docker logs <container> --since 10m
docker logs <container> -f  # follow

# Restart service
docker-compose restart <service>

# Execute command in container
docker exec -it <container> /bin/bash

# Check resource usage
docker stats
```

### Database Commands
```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U postgres -d trading_signals

# Common queries
SELECT COUNT(*) FROM signals WHERE created_at > NOW() - INTERVAL '1 hour';
SELECT * FROM approvals ORDER BY created_at DESC LIMIT 10;
SELECT pg_size_pretty(pg_database_size('trading_signals'));
```

### Redis Commands
```bash
# Connect to Redis
docker exec -it redis redis-cli

# Check connectivity
PING

# Check memory
INFO memory

# List keys (use with caution in production)
KEYS *

# Get key TTL
TTL key_name

# Delete key
DEL key_name
```

---

## Contact Information

- **On-Call Engineer**: PagerDuty rotation (see schedule)
- **Senior Engineers**: @senior-engineers in Slack
- **Engineering Manager**: @engineering-manager in Slack
- **CTO**: @cto in Slack (critical incidents only)
- **24/7 Hotline**: +1-555-ONCALL-1

**Slack Channels**:
- `#oncall-alerts`: All alerts (automated)
- `#incident-response`: Active incidents (humans only)
- `#engineering`: General engineering discussions
- `#devops`: Infrastructure and deployment issues

---

**Last Updated**: 2025-01-31
**Document Owner**: DevOps Team
**Review Frequency**: Quarterly or after major incidents
