#!/usr/bin/env python3
import os
import re
import time
import requests
from collections import deque
from datetime import datetime

# Configuration from environment variables
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
ERROR_RATE_THRESHOLD = float(os.getenv('ERROR_RATE_THRESHOLD', '2.0'))
WINDOW_SIZE = int(os.getenv('WINDOW_SIZE', '200'))
ALERT_COOLDOWN_SEC = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))
LOG_FILE = os.getenv('LOG_FILE', '/var/log/nginx/access.log')

# State tracking
last_pool = None
request_window = deque(maxlen=WINDOW_SIZE)
last_failover_alert = 0
last_error_alert = 0

def send_slack_alert(message, alert_type):
    """Send alert to Slack with color coding"""
    if not SLACK_WEBHOOK_URL:
        print(f"[WARNING] No SLACK_WEBHOOK_URL configured. Alert: {message}")
        return
    
    color = "#ff0000" if alert_type == "error" else "#ffa500" if alert_type == "failover" else "#00ff00"
    
    payload = {
        "attachments": [{
            "color": color,
            "title": f"🚨 Alert: {alert_type.upper()}",
            "text": message,
            "footer": "Blue/Green Deployment Monitor",
            "ts": int(time.time())
        }]
    }
    
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"[SLACK] Alert sent: {alert_type}")
        else:
            print(f"[ERROR] Slack webhook failed: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to send Slack alert: {e}")

def parse_log_line(line):
    """Parse Nginx log line to extract pool, upstream_status, and other fields"""
    # Extract pool
    pool_match = re.search(r'pool=(\w+)', line)
    pool = pool_match.group(1) if pool_match else None
    
    # Extract upstream_status
    status_match = re.search(r'upstream_status=(\d+)', line)
    upstream_status = int(status_match.group(1)) if status_match else None
    
    # Extract release
    release_match = re.search(r'release=([\w\-]+)', line)
    release = release_match.group(1) if release_match else None
    
    # Extract upstream address
    upstream_match = re.search(r'upstream=([\d\.:]+)', line)
    upstream = upstream_match.group(1) if upstream_match else None
    
    return {
        'pool': pool,
        'upstream_status': upstream_status,
        'release': release,
        'upstream': upstream,
        'line': line
    }

def check_failover(current_pool):
    """Detect and alert on pool failover"""
    global last_pool, last_failover_alert
    
    if last_pool and last_pool != current_pool:
        current_time = time.time()
        if current_time - last_failover_alert > ALERT_COOLDOWN_SEC:
            message = f"⚠️ **Failover Detected**: {last_pool.upper()} → {current_pool.upper()}\n"
            message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"Previous pool ({last_pool}) is likely unhealthy. Check container status."
            
            send_slack_alert(message, "failover")
            last_failover_alert = current_time
            print(f"[ALERT] Failover: {last_pool} → {current_pool}")
    
    last_pool = current_pool

def check_error_rate():
    """Check if error rate exceeds threshold"""
    global last_error_alert
    
    if len(request_window) < 50:  # Need minimum samples
        return
    
    error_count = sum(1 for status in request_window if status and status >= 500)
    error_rate = (error_count / len(request_window)) * 100
    
    if error_rate > ERROR_RATE_THRESHOLD:
        current_time = time.time()
        if current_time - last_error_alert > ALERT_COOLDOWN_SEC:
            message = f"🔥 **High Error Rate Detected**: {error_rate:.2f}%\n"
            message += f"Threshold: {ERROR_RATE_THRESHOLD}%\n"
            message += f"Window: {len(request_window)} requests\n"
            message += f"5xx errors: {error_count}\n"
            message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += "Action: Check upstream application logs and consider toggling pools."
            
            send_slack_alert(message, "error")
            last_error_alert = current_time
            print(f"[ALERT] High error rate: {error_rate:.2f}% ({error_count}/{len(request_window)})")

def tail_log_file():
    """Tail log file and process new lines"""
    print(f"[STARTUP] Monitoring {LOG_FILE}")
    print(f"[CONFIG] Error threshold: {ERROR_RATE_THRESHOLD}%, Window: {WINDOW_SIZE}, Cooldown: {ALERT_COOLDOWN_SEC}s")
    
    # Wait for log file to exist
    while not os.path.exists(LOG_FILE):
        print(f"[WAITING] Log file not found: {LOG_FILE}")
        time.sleep(2)
    
    with open(LOG_FILE, 'r') as f:
        # Go to end of file
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            
            # Skip health check requests
            if '/health' in line:
                continue
            
            parsed = parse_log_line(line)
            
            if parsed['pool']:
                check_failover(parsed['pool'])
            
            if parsed['upstream_status']:
                request_window.append(parsed['upstream_status'])
                check_error_rate()

if __name__ == '__main__':
    try:
        tail_log_file()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Watcher stopped")
    except Exception as e:
        print(f"[ERROR] Watcher crashed: {e}")
        raise