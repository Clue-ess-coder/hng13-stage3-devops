# Blue/Green Deployment Runbook

## Overview
This runbook provides operational guidance for responding to alerts from the Blue/Green deployment monitoring system.

---

## Alert Types

### 🔄 Failover Detected

**What it means:**  
The active pool has automatically switched from one deployment (Blue/Green) to another due to health check failures or upstream errors.

**Example Alert:**
```
⚠️ Failover Detected: BLUE → GREEN
Time: 2025-10-30 14:23:15
Previous pool (blue) is likely unhealthy. Check container status.
```

**Operator Actions:**

1. **Check Container Status**
   ```bash
   docker ps -a
   docker logs blue
   docker logs green
   ```

2. **Verify Health of Failed Pool**
   ```bash
   # Check if container is running
   docker inspect blue --format='{{.State.Status}}'
   
   # Check health endpoint directly
   curl http://localhost:8000/health
   ```

3. **Investigate Root Cause**
   - Review application logs for errors
   - Check resource utilization (CPU, memory)
   - Verify network connectivity
   - Look for recent deployments or changes

4. **Recovery Steps**
   - If the failed pool is healthy, toggle back:
     ```bash
     # Update .env
     ACTIVE_POOL=blue
     
     # Restart nginx to pick up change
     docker compose restart nginx
     ```
   - If unhealthy, leave on green and fix blue offline

5. **Post-Incident**
   - Document the incident
   - Update monitoring if needed
   - Review deployment process

---

### 🔥 High Error Rate Detected

**What it means:**  
The upstream application is returning HTTP 5xx errors above the configured threshold (default: 2% over last 200 requests).

**Example Alert:**
```
🔥 High Error Rate Detected: 5.23%
Threshold: 2.0%
Window: 200 requests
5xx errors: 10
Time: 2025-10-30 14:25:42
Action: Check upstream application logs and consider toggling pools.
```

**Operator Actions:**

1. **Immediate Assessment**
   ```bash
   # Check which pool is active
   docker compose exec nginx cat /etc/nginx/conf.d/default.conf | grep proxy_pass
   
   # View recent errors in Nginx logs
   docker compose exec nginx tail -n 50 /var/log/nginx/access.log | grep " 5"
   ```

2. **Check Application Health**
   ```bash
   # View application logs
   docker logs blue --tail=100
   docker logs green --tail=100
   
   # Check health endpoints
   curl http://localhost/health
   ```

3. **Determine Scope**
   - Is this affecting all requests or specific endpoints?
   - Is it transient or sustained?
   - Check external dependencies (databases, APIs)

4. **Mitigation Options**
   
   **Option A: Toggle to alternate pool**
   ```bash
   # If blue is active and erroring, switch to green
   # Update .env
   ACTIVE_POOL=green
   
   # Restart nginx
   docker compose restart nginx
   ```
   
   **Option B: Restart failing container**
   ```bash
   docker compose restart blue
   ```
   
   **Option C: Scale down traffic**
   - Implement rate limiting
   - Enable maintenance mode

5. **Monitor Recovery**
   ```bash
   # Watch logs in real-time
   docker compose logs -f alert_watcher
   
   # Check error rate manually
   docker compose exec nginx tail -f /var/log/nginx/access.log
   ```

---

## Maintenance Mode

### Suppressing Alerts During Planned Changes

When performing planned pool toggles or maintenance, you may want to temporarily disable alerts:

**Option 1: Stop the watcher**
```bash
docker compose stop alert_watcher
# Perform maintenance
docker compose start alert_watcher
```

**Option 2: Set a maintenance flag (future enhancement)**
```bash
# Add to .env
MAINTENANCE_MODE=true

# This will suppress failover alerts but keep error-rate monitoring
```

---

## Common Scenarios

### Scenario 1: Planned Blue → Green Deployment

1. Verify green is healthy
2. Stop alert_watcher to avoid false alerts
3. Update `.env`: `ACTIVE_POOL=green`
4. Restart nginx: `docker compose restart nginx`
5. Monitor for 5 minutes
6. Restart alert_watcher: `docker compose start alert_watcher`

### Scenario 2: Emergency Rollback

1. If green is failing, quickly revert to blue:
   ```bash
   # Update .env
   ACTIVE_POOL=blue
   docker compose restart nginx
   ```
2. Monitor alert_watcher logs for recovery confirmation

### Scenario 3: Both Pools Unhealthy

1. Check if issue is upstream (database, external API)
2. Review recent changes across all infrastructure
3. Consider emergency maintenance page
4. Restart all services:
   ```bash
   docker compose restart
   ```

---

## Alert Configuration

Adjust alert sensitivity in `.env`:

```bash
# Increase threshold if too sensitive
ERROR_RATE_THRESHOLD=5.0

# Increase window for more stable detection
WINDOW_SIZE=500

# Reduce alert frequency
ALERT_COOLDOWN_SEC=600
```

After changing values:
```bash
docker compose restart alert_watcher
```

---

## Viewing Logs

**Nginx Access Logs (structured):**
```bash
docker compose exec nginx tail -f /var/log/nginx/access.log
```

**Alert Watcher Logs:**
```bash
docker compose logs -f alert_watcher
```

**All Services:**
```bash
docker compose logs -f
```

---

## Escalation Path

1. **Level 1:** Check runbook, attempt standard remediation
2. **Level 2:** Contact on-call DevOps engineer
3. **Level 3:** Escalate to platform team lead
4. **Level 4:** Initiate major incident protocol

---

## Health Check Commands

```bash
# Quick health check
curl http://localhost/health

# Detailed status
docker compose ps
docker stats --no-stream

# End-to-end test
curl -i http://localhost/

# Check which pool is serving
curl -i http://localhost/ | grep -i "x-app-pool"
```

---

## Contact Information

- **Slack Channel:** #devops-alerts
- **On-Call:** [PagerDuty/Opsgenie rotation]
- **Documentation:** https://github.com/your-org/blue-green-deploy

---

## Revision History

| Date       | Version | Changes         |
| ---------- | ------- | --------------- |
| 2025-10-30 | 1.0     | Initial runbook |