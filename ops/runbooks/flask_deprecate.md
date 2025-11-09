# Flask API Deprecation Runbook (PR-083)

## Overview

This runbook provides step-by-step instructions for decommissioning the legacy Flask API (`base_files/FlaskAPI.py`) and transitioning to the FastAPI Gateway.

**Timeline**: 90 days from deployment
**Target Date**: 2025-03-31
**Feature Flag**: `FLASK_COMPATIBILITY_MODE`

---

## Prerequisites

✅ FastAPI Gateway deployed with all 9 REST endpoints
✅ WebSocket replacement functional
✅ Compatibility shims tested (301 redirects)
✅ Telemetry configured (`legacy_calls_total` metric)
✅ Monitoring dashboards created
✅ Client notification sent (email/docs)

---

## Phase 1: Deploy with Compatibility Mode ON (Week 1)

### Goal
Deploy FastAPI Gateway alongside Flask, with 301 redirects from old routes to new routes.

### Steps

1. **Set Environment Variable**
   ```bash
   export FLASK_COMPATIBILITY_MODE=true
   ```

2. **Deploy FastAPI Gateway**
   ```bash
   # Build Docker image
   docker build -t trading-platform:gateway-v1 .

   # Deploy to production
   kubectl apply -f k8s/gateway-deployment.yaml

   # Verify pods running
   kubectl get pods -l app=gateway
   ```

3. **Verify 301 Redirects**
   ```bash
   # Test old route (should 301 → new route)
   curl -I -H "X-User-ID: 123456789" https://api.example.com/api/price

   # Expected:
   # HTTP/1.1 301 Moved Permanently
   # Location: /api/v1/market/price
   # X-Deprecation-Warning: This endpoint moved to /api/v1/market/price
   # X-Sunset: 2025-03-31
   ```

4. **Monitor Legacy Metric**
   ```promql
   # Prometheus query
   sum by (route) (increase(legacy_calls_total[1h]))
   ```

5. **Check Error Rates**
   ```promql
   # Should be < 1%
   sum(rate(errors_total{status="5xx"}[5m])) / sum(rate(http_requests_total[5m]))
   ```

### Success Criteria
- [ ] FastAPI Gateway deployed and healthy
- [ ] 301 redirects working for all 9 endpoints
- [ ] `legacy_calls_total` metric incrementing
- [ ] Error rate < 1%
- [ ] Latency < 200ms p95

---

## Phase 2: Client Notification (Week 2-4)

### Goal
Notify all API clients of deprecation timeline.

### Steps

1. **Send Email Notification**
   - **Subject**: "Action Required: API Migration by 2025-03-31"
   - **Recipients**: All registered users + external API clients
   - **Content**:
     - Old routes deprecated on 2025-03-31
     - New routes listed in migration guide
     - Link to `/api/v1/docs/migration.md`
     - Support contact: support@example.com

2. **Update API Documentation**
   ```markdown
   # Add deprecation banner to docs
   ⚠️ **DEPRECATED**: Legacy routes will be removed on 2025-03-31.
   See [migration guide](/api/v1/docs/migration) for new endpoints.
   ```

3. **Add Deprecation Headers to Responses**
   ```python
   # Already implemented in compat.py
   headers={
       "X-Deprecation-Warning": "This endpoint moved to /api/v1/market/price",
       "X-Sunset": "2025-03-31"
   }
   ```

4. **Monitor Client Compliance**
   ```promql
   # Track legacy calls by user
   sum by (user_id) (increase(legacy_calls_total[24h]))
   ```

5. **Contact High-Traffic Clients**
   - Identify clients with >1000 legacy calls/day
   - Reach out directly with migration assistance
   - Offer dedicated support during transition

### Success Criteria
- [ ] Notification email sent to all clients
- [ ] Deprecation banner visible in docs
- [ ] Migration guide published
- [ ] High-traffic clients contacted
- [ ] Legacy calls decreasing week-over-week

---

## Phase 3: Gradual Flag Off (Week 5-12)

### Goal
Transition from 301 redirects to 410 Gone responses via canary rollout.

### Steps

1. **Week 5: 10% Canary**
   ```bash
   # Set canary traffic to 10%
   kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE_CANARY=0.1

   # Monitor error rates
   sum(rate(errors_total{status="410"}[5m])) by (route)
   ```

2. **Week 6-7: 50% Canary**
   ```bash
   # Increase canary to 50%
   kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE_CANARY=0.5

   # Monitor client adoption
   sum(increase(legacy_calls_total[24h]))  # Should be < 50% of Week 1
   ```

3. **Week 8-12: 100% (Full Flag Off)**
   ```bash
   # Disable compatibility mode globally
   export FLASK_COMPATIBILITY_MODE=false
   kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE=false

   # All old routes now return 410 Gone
   curl -I -H "X-User-ID: 123456789" https://api.example.com/api/price

   # Expected:
   # HTTP/1.1 410 Gone
   # X-Migration-Guide: /api/v1/docs/migration
   ```

4. **Monitor Client Compliance**
   ```promql
   # Should trend toward zero
   sum(increase(legacy_calls_total[7d]))
   ```

5. **Handle Stragglers**
   - Email clients still using old routes
   - Offer dedicated support
   - Set final deadline: 30 days

### Rollback Procedure

If error rate > 5% or critical issues:

1. **Immediate Rollback**
   ```bash
   kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE=true
   kubectl rollout undo deployment/gateway
   ```

2. **Investigate**
   - Check logs: `kubectl logs -l app=gateway | grep ERROR`
   - Review metrics: `sum(rate(errors_total[5m])) by (route)`
   - Identify root cause

3. **Fix and Redeploy**
   - Patch FastAPI gateway
   - Test in staging
   - Redeploy to production

4. **Resume Deprecation**
   - Wait 1 week after fix
   - Restart canary rollout

### Success Criteria
- [ ] 10% canary successful (error rate < 1%)
- [ ] 50% canary successful
- [ ] 100% flag off successful
- [ ] Legacy calls < 100/day
- [ ] No critical client complaints

---

## Phase 4: Remove Flask Code (Week 13+)

### Goal
Permanently remove legacy Flask API after 30 days of zero legacy calls.

### Conditions for Removal

**All must be true**:
- [ ] `legacy_calls_total == 0` for 30 consecutive days
- [ ] No 410 errors in past 7 days
- [ ] All clients using new routes
- [ ] No support tickets related to old routes

### Steps

1. **Verify Zero Legacy Calls**
   ```promql
   # Must return 0
   sum(increase(legacy_calls_total[30d]))
   ```

2. **Remove Flask Code**
   ```bash
   # Delete legacy Flask API
   rm base_files/FlaskAPI.py

   # Remove compatibility shims
   git rm backend/app/gateway/compat.py

   # Remove feature flag from settings
   # Edit backend/app/core/settings.py: Remove flask_compatibility_mode
   ```

3. **Remove Legacy Metric**
   ```python
   # Edit backend/app/observability/metrics.py
   # Comment out or remove:
   # self.legacy_calls_total = Counter(...)
   ```

4. **Update Documentation**
   - Remove deprecation warnings
   - Archive migration guide
   - Update changelog

5. **Deploy Clean Version**
   ```bash
   git add .
   git commit -m "PR-083: Remove legacy Flask API (zero usage for 30 days)"
   git push origin main

   # Deploy
   kubectl apply -f k8s/gateway-deployment.yaml
   ```

### Success Criteria
- [ ] Flask code removed from repository
- [ ] Compatibility shims removed
- [ ] Legacy metric removed
- [ ] Docs updated
- [ ] Clean deployment successful
- [ ] No regressions

---

## Monitoring & Alerts

### Key Metrics

1. **Legacy Calls (should trend to zero)**
   ```promql
   sum by (route) (increase(legacy_calls_total[24h]))
   ```

2. **Error Rate (should be < 1%)**
   ```promql
   sum(rate(errors_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
   ```

3. **Latency (should be < 200ms p95)**
   ```promql
   histogram_quantile(0.95, sum(rate(request_duration_seconds_bucket[5m])) by (le))
   ```

4. **WebSocket Connections (should increase as clients migrate)**
   ```promql
   websocket_connections_active
   ```

### Alerts

1. **High Legacy Usage After Phase 3**
   ```yaml
   - alert: HighLegacyUsage
     expr: sum(increase(legacy_calls_total[1h])) > 1000
     for: 6h
     labels:
       severity: warning
     annotations:
       summary: "High legacy API usage detected"
       description: "{{ $value }} legacy calls in past hour. Check client compliance."
   ```

2. **High Error Rate**
   ```yaml
   - alert: GatewayErrorRate
     expr: sum(rate(errors_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
     for: 5m
     labels:
       severity: critical
     annotations:
       summary: "Gateway error rate > 5%"
       description: "Consider rollback. Check logs immediately."
   ```

3. **WebSocket Disconnects**
   ```yaml
   - alert: HighWebSocketDisconnects
     expr: rate(websocket_disconnects_total[5m]) > 10
     for: 10m
     labels:
       severity: warning
     annotations:
       summary: "High WebSocket disconnect rate"
       description: "{{ $value }} disconnects/sec. Investigate connection stability."
   ```

---

## Rollback Scenarios

### Scenario 1: High Error Rate (>5%)

**Symptoms**: Error rate spikes after flag off
**Action**: Immediate rollback

```bash
kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE=true
kubectl rollout status deployment/gateway
```

**Investigation**:
- Check FastAPI logs: `kubectl logs -l app=gateway --tail=100`
- Verify DB connection: `psql -h db -U user -c "SELECT 1"`
- Test endpoints manually: `curl -H "X-User-ID: 123" https://api.example.com/api/v1/market/price`

### Scenario 2: WebSocket Connection Failures

**Symptoms**: Clients cannot connect to `/ws/market`
**Action**: Enable compatibility mode, investigate WebSocket

```bash
kubectl set env deployment/gateway FLASK_COMPATIBILITY_MODE=true

# Check WebSocket logs
kubectl logs -l app=gateway | grep "WebSocket"

# Test WebSocket manually
wscat -c "ws://localhost:8000/ws/market?user_id=123"
```

### Scenario 3: Business Logic Regression

**Symptoms**: P&L calculations incorrect, metrics wrong
**Action**: Immediate rollback + hot fix

```bash
# Rollback
kubectl rollout undo deployment/gateway

# Verify Flask API still available
curl -H "X-User-ID: 123" https://legacy.example.com/api/metrics

# Fix FastAPI code (e.g., P&L formula)
# Test in staging
# Redeploy to production
```

---

## Communication Templates

### Initial Notification Email

**Subject**: Action Required: API Migration by 2025-03-31

**Body**:
```
Dear [Client],

We're upgrading our API infrastructure to improve performance and reliability.

ACTION REQUIRED:
- Old API endpoints will be deprecated on March 31, 2025
- Please migrate to new endpoints by this date

MIGRATION GUIDE:
https://api.example.com/docs/migration

NEW ENDPOINTS:
- OLD: /api/price → NEW: /api/v1/market/price
- OLD: /api/trades → NEW: /api/v1/trading/trades
- Full list in migration guide

SUPPORT:
Email: support@example.com
Docs: https://api.example.com/docs

Thank you,
Platform Team
```

### Reminder Email (Week 10)

**Subject**: Reminder: API Migration Deadline - 3 Weeks Remaining

**Body**:
```
Dear [Client],

This is a reminder that legacy API endpoints will be removed on March 31, 2025 (3 weeks).

YOUR STATUS:
We detected [X] calls to old endpoints in the past 7 days.

NEXT STEPS:
1. Review migration guide: https://api.example.com/docs/migration
2. Update your code to use new endpoints
3. Test your integration
4. Contact support if you need help: support@example.com

IMPORTANT:
After March 31, old endpoints will return 410 Gone errors.

Thank you,
Platform Team
```

### Final Warning Email (Week 12)

**Subject**: URGENT: API Migration Deadline - 1 Week Remaining

**Body**:
```
Dear [Client],

URGENT: Legacy API endpoints will be removed in 7 days (March 31, 2025).

YOUR STATUS:
We detected [X] calls to old endpoints in the past 24 hours.

IMMEDIATE ACTION REQUIRED:
1. Migrate to new endpoints NOW
2. Test your integration
3. Contact support if you need emergency assistance: support@example.com

AFTER MARCH 31:
Old endpoints will return 410 Gone errors. Your integration will break.

Migration guide: https://api.example.com/docs/migration

Thank you,
Platform Team
```

---

## Success Metrics

### Technical Metrics
- [ ] Legacy calls: 0 for 30 consecutive days
- [ ] Error rate: < 1% throughout migration
- [ ] Latency: p95 < 200ms (2-3x faster than Flask)
- [ ] WebSocket connections: > 90% of previous SocketIO connections

### Business Metrics
- [ ] Zero production incidents related to migration
- [ ] Zero client churn due to API changes
- [ ] Support tickets related to migration < 10 total
- [ ] Client satisfaction score: ≥ 4.5/5.0

### Process Metrics
- [ ] Completed on schedule (90 days)
- [ ] Rollback not required
- [ ] Documentation complete and accurate
- [ ] Team learned from post-mortem (if applicable)

---

## Post-Mortem (After Phase 4)

### Questions to Answer

1. **What went well?**
   - FastAPI performance improvements
   - Client communication effectiveness
   - Monitoring/telemetry visibility

2. **What could be improved?**
   - Migration timeline (too long/short?)
   - Feature flag rollout (canary %?)
   - Client notification strategy

3. **What did we learn?**
   - Technical lessons (async/await, WebSocket)
   - Process lessons (deprecation, communication)
   - Tooling lessons (monitoring, alerts)

4. **Action items for next migration**
   - Update runbook template
   - Improve automation (scripts, alerts)
   - Document edge cases encountered

---

## Appendix: Useful Commands

### Check Legacy Calls by Route
```bash
kubectl exec -it prometheus-0 -- promtool query instant \
  'sum by (route) (increase(legacy_calls_total[24h]))'
```

### Tail Gateway Logs
```bash
kubectl logs -f -l app=gateway | grep "legacy"
```

### Test All Legacy Routes
```bash
#!/bin/bash
USER_ID="123456789"
BASE_URL="https://api.example.com"

routes=(
  "/api/price"
  "/api/trades"
  "/api/images"
  "/api/positions"
  "/api/metrics"
  "/api/indicators"
  "/api/historical"
)

for route in "${routes[@]}"; do
  echo "Testing $route..."
  curl -I -H "X-User-ID: $USER_ID" "$BASE_URL$route"
  echo "---"
done
```

### Export Legacy Call Data
```bash
# Export to CSV for analysis
kubectl exec -it prometheus-0 -- promtool query range \
  --start=$(date -d '30 days ago' +%s) \
  --end=$(date +%s) \
  --step=1h \
  'sum by (route) (increase(legacy_calls_total[1h]))' > legacy_calls.csv
```

---

**Runbook Owner**: Platform Team
**Last Updated**: 2025-01-02
**Version**: 1.0
**PR**: PR-083 (FlaskAPI Decommission)
