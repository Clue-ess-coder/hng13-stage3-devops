# HNG DevOps Stage 3 - Observability and Alerts for Blue/Green Deployment

This repo implements automated monitoring and alerting over Slack for a Blue/Green deployment setup.

**Prepared by:** Abdul-Hameed Adedimeji  
**Slack ID:** @AJ

## Prerequisites

- Docker & Docker Compose
- Slack workspace with incoming webhook configured
- Stage 2 setup

## File Structure

```tree
.
├── docker-compose.yml          # container orchestration
├── nginx.conf.template         # Nginx config
├── watcher.py                  # Python log watcher
├── requirements.txt            # Python dependencies
├── .env                        # Environment configuration (ignored)
├── .env.example               # Example environment file
├── runbook.md                 # Operator response guide
└── README.md                  # You're HERE
```

## Quick Start

### 1. Clone Repository

```bash
git clone <repo-url>
cd <repo>
```

### 2. Configure Environment

Rename `.env.example` to `.env` and update with your values

```bash
mv .env.example .env
```

The following variables are required:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
BLUE_IMAGE=yimikaade/wonderful:devops-stage-two
GREEN_IMAGE=yimikaade/wonderful:devops-stage-two
ACTIVE_POOL=blue
```

To get a Slack webhook:

1. Visit <https://api.slack.com/apps>
2. Create a new app -> From scratch -> Fill form
3. Go to Incoming Webhooks -> Activate Incoming Webhooks, toggle ON
4. Add webhook to chosen channel
5. Copy webhook URL to `.env`

### 3. Start Services

```bash
# start containers
docker compose up -d
```

### 4. Verify Setup

```bash
# confirm all containers are running
docker ps -a

# view container logs
docker logs nginx
docker logs -f alert_watcher

# or nginx access log
docker exec nginx cat /var/log/nginx/custom_access.log
docker exec alert_watcher cat /var/log/nginx/custom_access.log

# test endpoint for active pool
curl http://localhost:8080/version
```

## Testing Alerts

The images have built-in chaos endpoints for testing:

- `/chaos/start?mode=error` - Simulates 5xx errors
- `/chaos/start?mode=timeout` - Simulates timeouts
- `/chaos/stop` - Stops chaos mode
- `/version` - Returns pool and release info

### Failover Event

```bash
# start chaos on blue pool
curl -X POST http://localhost:8081/chaos/start?mode=error

# generate traffic to trigger failover
for i in {1..5}; do curl http://localhost:8080/version; sleep 0.5; done

# check Slack for failover alert
```

An alert showing failover from blue to green pops up in Slack (ref: <>)

### High Error Rate

```bash
# chaos mode needs to be enabled for a 5xx error
curl -X POST http://localhost:8081/chaos/start?mode=error

# generate traffic to trigger error rate alert
for i in {1..100}; do curl http://localhost:8080/version 2>/dev/null; done

# check Slack for error rate alert
```

An alert showing error rate above threshold appears in the specified Slack channel.

### Recovery

```bash
# stop chaos on active pool
curl -X POST http://localhost:8081/chaos/stop

# triggers a failover alert in Slack
```

### Manual Pool Toggle

```bash
# change active pool in .env
# ACTIVE_POOL=green

# restart nginx
docker compose restart nginx

# generate traffic
for i in {1..10}; do curl http://localhost:8080/version; done

# tail nginx logs to confirm pool change
docker exec nginx tail -5 /var/log/nginx/custom_access.log
```

### Nginx Log Format

Logs are written to `custom_access.log` (avoiding the default `stdout` symlinked `access.log`):

```nginx.conf.template
server {
    listen 80;

    access_log /var/log/nginx/custom_access.log detailed;
    error_log /var/log/nginx/custom_error.log warn;

    // rest of code
}
```

## Monitoring

### How to View (Live) Logs

```bash
# follow alert watcher output
docker logs -f alert_watcher

# tail nginx (custom) access log file
docker exec nginx tail -f /var/log/nginx/custom_access.log

# tail nginx error logs
docker exec nginx tail -f /var/log/nginx/custom_error.log

# follow app logs
docker logs -f app_blue
docker logs -f app_green
```

### Manual Slack Alert Test

```bash
# test webhook directly from command line
# replace "$SLACK_WEBHOOK_URL" with actual URL

curl -X POST -H 'Content-Type: application/json' \
  -d '{"text":"Test alert from runbook"}' \
  $SLACK_WEBHOOK_URL
```

## Screenshots

Screenshots references to:

1. **Slack Alert - Failover Event:** FAILOVER.png
2. **Slack Alert - High Error Rate:** HIGH_ERROR_RATE.png
3. **Container Logs:** FAILOVER_LOGS.png

## Cleanup

```bash
# stops and removes all containers
docker compose down

# optionally remove mounted volume
docker compose down -v
```
