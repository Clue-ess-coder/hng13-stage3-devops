#!/usr/bin/env bash

echo "🧪 Blue/Green Deployment Alert Testing Script"
echo "=============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Verify services are running
echo -e "${YELLOW}Test 1: Checking service status...${NC}"
docker compose ps
echo ""

# Test 2: Baseline health check
echo -e "${YELLOW}Test 2: Baseline health check...${NC}"
RESPONSE=$(curl -s -I http://localhost/)
echo "$RESPONSE" | grep -E "X-App-Pool|X-Release-Id"
echo ""

# Test 3: Simulate failover
echo -e "${YELLOW}Test 3: Simulating failover (stopping blue container)...${NC}"
echo "This should trigger a Slack failover alert!"
docker stop blue
sleep 2

echo "Generating traffic to trigger failover detection..."
for i in {1..10}; do
    curl -s http://localhost/ > /dev/null
    echo -n "."
    sleep 1
done
echo ""

echo "Checking alert watcher logs for failover detection..."
docker compose logs alert_watcher | tail -20
echo ""

echo -e "${GREEN}✓ Check your Slack channel for failover alert!${NC}"
echo ""

# Restart blue for next test
echo "Restarting blue container..."
docker start blue
sleep 5
echo ""

# Test 4: Simulate high error rate
echo -e "${YELLOW}Test 4: Simulating high error rate...${NC}"
echo "Pausing blue container briefly to cause 502 errors..."

for i in {1..100}; do
    if [ $i -eq 20 ]; then
        docker pause blue &
    fi
    if [ $i -eq 40 ]; then
        docker unpause blue &
    fi
    curl -s http://localhost/ > /dev/null 2>&1
done

echo ""
echo "Checking alert watcher logs for error rate detection..."
docker compose logs alert_watcher | tail -20
echo ""

echo -e "${GREEN}✓ Check your Slack channel for error rate alert!${NC}"
echo ""

# Test 5: View structured logs
echo -e "${YELLOW}Test 5: Sample of structured Nginx logs...${NC}"
docker compose exec nginx tail -5 /var/log/nginx/access.log
echo ""

echo "=============================================="
echo -e "${GREEN}Testing complete!${NC}"
echo ""
echo "Summary:"
echo "- Verified services running"
echo "- Tested failover mechanism"
echo "- Tested error rate detection"
echo "- Viewed structured logs"
echo ""
echo "Next steps:"
echo "1. Check your Slack channel for alerts"
echo "2. Take screenshots of the alerts"
echo "3. Include screenshots in your submission"
echo ""