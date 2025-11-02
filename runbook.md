# HNG Stage 3 Blue/Green Deployment Runbook

## Alert Types and Operator Actions

### FAILOVER DETECTED

This means traffic has automatically switched from one pool (blue or green) to the other due to induced chaos or upstream errors.

Here's what that looks like:

```md
FAILOVER DETECTED
Pool switched: blue → green
Time: 2025-11-02 07:30:15

Details:
- Pool: green
- Release: v1.0.1
- Upstream: 172.18.0.3:3000
- Upstream Status: 500
- Request Time: 0.012s
- Upstream Response Time: 0.002s
```

#### Operator Actions

1. First, check the failed pool container logs

   ```bash
   > docker logs app_blue       # or app_green
   
   🟢 blue server pool responding to: /chaos/start
   🧪 Simulation mode set to 'error'
   🟢 blue server pool responding to: /version
   💥 Simulated error for: /version
   🟢 blue server pool responding to: /version
   💥 Simulated error for: /version
   ```

2. Then verify backup pool works as expected

   ```bash
   > curl http://localhost:8080/version  # should redirect traffic to green

   > docker logs app_green               # tail logs to confirm

   🟢 green server pool responding to: /version
   ```

3. Review Nginx logs to ensure traffic is being routed to backup pool

   ```bash
   > docker exec nginx tail -5 /var/log/nginx/custom_access.log
  
   172.18.0.1 - - [02/Nov/2025:10:09:30 +0000] "GET /version HTTP/1.1" 200 57 "-" "curl/8.5.0" pool=blue release=v1.0.0 upstream_status=200 upstream=172.18.0.2:3000 request_time=0.001 upstream_response_time=0.001
   172.18.0.1 - - [02/Nov/2025:10:11:41 +0000] "GET /version HTTP/1.1" 200 57 "-" "curl/8.5.0" pool=green release=v1.0.1 upstream_status=500, 200 upstream=172.18.0.2:3000, 172.18.0.3:3000 request_time=0.003 upstream_response_time=0.001, 0.002
   ```

4. Tail alert_watcher logs for context

   ```bash
   docker logs -f alert_watcher
   ```

5. If primary pool needs fixes
   - Leave traffic on backup pool
   - Fix/redeploy the failed container
   - Test directly before switching back

   ```bash
   curl http://localhost:8081/version        # if chaos on app_blue
   curl http://localhost:8082/version        # if chaos on app_green
   ````

#### Alert Cooldown

A failover event triggers an alert with a 300s (5 mins) cooldown.

### HIGH ERROR RATE

This means the percentage of 5xx errors from upstream containers exceeds the set threshold with respect to the maximum number of requests in the sliding window.

**Sample:**

```txt
HIGH ERROR RATE DETECTED
Error Rate: 6.50%
Threshold: 2.00%           # for default 2% threshold
Errors: 8/123 requests
Current Pool: green
Time: 2025-11-02 08:36:52

Details:
- Pool: green
- Release: v1.0.1
- Upstream: 172.18.0.3:3000
- Upstream Status: 500
- Request Time: 0.045s
- Upstream Response Time: 0.043s
```

**Operator Actions:**

1. Tail logs in real-time

   ```bash
   > docker logs -f alert_watcher

   [INFO] Error rate: 3.03% (5/165) ✗
   [ALERT] HIGH ERROR RATE DETECTED
   Error Rate: 3.03%
   Threshold: 2.00%
   Errors: 5/165 requests
   Current Pool: green
         Time: 2025-11-02 12:27:19
         Pool: green, Release: v1.0.1
         Upstream: 172.18.0.2:3000, Status: 500
   [INFO] Slack alert sent successfully
   [WARN] High error rate: 3.03% (threshold: 2.00%)
   ```

2. Check Nginx logs for upstream errors

   ```bash
   > docker exec nginx tail -5 /var/log/nginx/custom_access.log
   
   172.18.0.1 - - [02/Nov/2025:11:27:19 +0000] "GET /version HTTP/1.1" 200 57 "-" "curl/8.5.0" pool=green release=v1.0.1 upstream_status=500, 200 upstream=172.18.0.2:3000, 172.18.0.3:3000 request_time=0.003 upstream_response_time=0.002, 0.002
   ```

3. Perform a manual pool toggle

   ```bash
   # set ACTIVE_POOL=green

   # restart nginx
   docker compose restart nginx
   ```

4. Clear the error rate by sending 200+ successful requests to push errors out of the window

     ```bash
     for i in {1..200}; do curl http://localhost:8080/version > /dev/null; sleep 0.1; done
     ```

>Old errors don't disappear immediately. They stay in the window until pushed out by 200+ new requests.

After sending an alert, high error rate alerts won't be sent for another 300s (5 minutes).

### RECOVERY

   ```bash
   # stop chaos
   curl -X POST http://localhost:8081/chaos/stop
   # This will trigger another failover alert

   curl http://localhost:8080/version
   # returns primary pool in nginx logs
   ```

## Maintenance Mode (Suppressing Alerts)

During planned toggles, operators can use one of these methods to suppress alerts:

### Option 1 - Stop Watcher

```bash
# before maintenance
docker compose stop alert_watcher

# perform changes...

# after maintenance
docker compose restart alert_watcher
```

### Option 2 - Disable Slack Webhook

When testing changes with active monitoring

```bash
# comment out webhook URL
# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/custom-hook


# restart alert_watcher
docker compose restart alert_watcher

# tail logs
docker logs -f alert_watcher 

# uncomment webhook and restart alert_watcher after maintenance
```

### Option 3 - Increase Cooldown

For very short maintenance sessions

```bash
# edit cooldown in .env:
ALERT_COOLDOWN_SEC=3600

# restart watcher
docker compose restart alert_watcher

# ...........
# maintenance
# ...........

# reset cooldown to required
ALERT_COOLDOWN_SEC=300

## restart alert_watcher
docker compose restart alert_watcher
```

The first failover or high error rate event after restart will trigger an alert still. This is because the cooldown starts ONLY after an alert.

### Recommended Workflow

```bash
# stop watcher
docker compose stop alert_watcher

# Change active pool in .env

# restart nginx
docker compose restart nginx

# verify new pool receives traffic
curl http://localhost:8080/version        # Should show pool=green in nginx logs

# generate traffic to clear any error windows
for i in {1..200}; do curl -s http://localhost:8080/version > /dev/null; done

# restart alert_watcher
docker compose restart alert_watcher

# tail logs for issues
docker logs -f alert_watcher
```
