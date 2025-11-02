#!/usr/bin/env python3

import os
import re
import time
import requests
from collections import deque
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

LOG_FILE = os.getenv("LOG_FILE", "/var/log/nginx/custom_access.log")
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "200"))
ERROR_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "2.0")) / 100.0
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN_SEC", "300"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# State tracking
request_window = deque(maxlen=WINDOW_SIZE)
current_pool = None
last_failover_alert = 0
last_error_alert = 0
file_position = 0
last_parsed_data = {}
is_startup = True  # Flag to prevent alerts during initial log processing


def get_current_time():
    """Get current time in UTC+1 timezone"""
    return (datetime.utcnow() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')


def parse_log_line(line):
    """Extract all relevant fields from log line"""
    try:
        pool_match = re.search(r'pool=(\w+)', line)
        release_match = re.search(r'release=([\w\.\-]+)', line)
        status_match = re.search(r'upstream_status=(\d+)', line)
        upstream_match = re.search(r'upstream=([\d\.:]+)', line)
        request_time_match = re.search(r'request_time=([\d\.]+)', line)
        upstream_time_match = re.search(r'upstream_response_time=([\d\.]+)', line)
        
        if pool_match and status_match:
            return {
                'pool': pool_match.group(1),
                'release': release_match.group(1) if release_match else 'unknown',
                'upstream_status': int(status_match.group(1)),
                'upstream': upstream_match.group(1) if upstream_match else 'unknown',
                'request_time': request_time_match.group(1) if request_time_match else '0',
                'upstream_response_time': upstream_time_match.group(1) if upstream_time_match else '0'
            }
    except Exception as e:
        print(f"[DEBUG] Parse error: {e}")
    
    return None


def send_slack_alert(message, parsed_data=None):
    timestamp = get_current_time()
    
    # Build detailed message
    alert_text = f"{message}\nTime: {timestamp}"
    
    if parsed_data:
        alert_text += f"\n\nDetails:"
        alert_text += f"\n- Pool: {parsed_data.get('pool', 'unknown')}"
        alert_text += f"\n- Release: {parsed_data.get('release', 'unknown')}"
        alert_text += f"\n- Upstream: {parsed_data.get('upstream', 'unknown')}"
        alert_text += f"\n- Upstream Status: {parsed_data.get('upstream_status', 'unknown')}"
        alert_text += f"\n- Request Time: {parsed_data.get('request_time', '0')}s"
        alert_text += f"\n- Upstream Response Time: {parsed_data.get('upstream_response_time', '0')}s"
    
    print(f"[ALERT] {message}")
    if parsed_data:
        print(f"        Time: {timestamp}")
        print(f"        Pool: {parsed_data.get('pool')}, Release: {parsed_data.get('release')}")
        print(f"        Upstream: {parsed_data.get('upstream')}, Status: {parsed_data.get('upstream_status')}")
    
    if not SLACK_WEBHOOK_URL:
        print("[WARN] SLACK_WEBHOOK_URL not set, skipping Slack notification")
        return
    
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={"text": alert_text},
            timeout=10
        )
        if response.status_code == 200:
            print("[INFO] Slack alert sent successfully")
        else:
            print(f"[ERROR] Slack failed: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to send Slack alert: {e}")


def check_failover(parsed_data):
    global current_pool, last_failover_alert, last_parsed_data, is_startup
    
    pool = parsed_data['pool']
    current_time = time.time()
    
    if current_pool is None:
        current_pool = pool
        print(f"[INFO] Initial pool detected: {pool}")
        print(f"[INFO] Release: {parsed_data['release']}, Upstream: {parsed_data['upstream']}")
        last_parsed_data = parsed_data
        return
    
    if pool != current_pool:
        time_since_last = current_time - last_failover_alert
        
        # Skip alerting during startup (processing historical logs)
        if is_startup:
            print(f"[INFO] Historical failover detected: {current_pool} → {pool} (startup, no alert)")
            current_pool = pool
            last_parsed_data = parsed_data
            return
        
        if time_since_last > ALERT_COOLDOWN:
            message = f"FAILOVER DETECTED\nPool switched: {current_pool} → {pool}"
            send_slack_alert(message, parsed_data)
            last_failover_alert = current_time
            print(f"[WARN] Failover: {current_pool} → {pool}")
        else:
            remaining = int(ALERT_COOLDOWN - time_since_last)
            print(f"[INFO] Failover detected: {current_pool} → {pool} (COOLDOWN ACTIVE, {remaining}s remaining)")
        
        current_pool = pool
        last_parsed_data = parsed_data


def check_error_rate():
    """Calculate error rate and alert if threshold exceeded"""
    global last_error_alert, last_parsed_data, is_startup
    
    if len(request_window) < min(50, WINDOW_SIZE):
        return  # Need minimum sample size
    
    total = len(request_window)
    errors = sum(request_window)
    error_rate = errors / total
    current_time = time.time()
    time_since_last = current_time - last_error_alert
    
    # Always show current error rate
    status_indicator = "✓" if error_rate <= ERROR_THRESHOLD else "✗"
    print(f"[INFO] Error rate: {error_rate*100:.2f}% ({errors}/{total}) {status_indicator}")
    
    if error_rate > ERROR_THRESHOLD:
        # Skip alerting during startup
        if is_startup:
            print(f"[INFO] Historical high error rate: {error_rate*100:.2f}% (startup, no alert)")
            return
        
        if time_since_last > ALERT_COOLDOWN:
            message = (
                f"HIGH ERROR RATE DETECTED\n"
                f"Error Rate: {error_rate*100:.2f}%\n"
                f"Threshold: {ERROR_THRESHOLD*100:.2f}%\n"
                f"Errors: {errors}/{total} requests\n"
                f"Current Pool: {current_pool}"
            )
            send_slack_alert(message, last_parsed_data)
            last_error_alert = current_time
            print(f"[WARN] High error rate: {error_rate*100:.2f}% (threshold: {ERROR_THRESHOLD*100:.2f}%)")
        else:
            remaining = int(ALERT_COOLDOWN - time_since_last)
            print(f"[WARN] Error rate {error_rate*100:.2f}% ABOVE THRESHOLD (COOLDOWN ACTIVE, {remaining}s remaining)")
    else:
        # Reset cooldown when error rate drops below threshold
        if last_error_alert > 0 and time_since_last > ALERT_COOLDOWN:
            if errors == 0 and total >= WINDOW_SIZE:
                print(f"[INFO] Error rate recovered to {error_rate*100:.2f}% (cooldown cleared)")


def process_new_lines(file_path):
    """Read and process new lines from log file"""
    global file_position
    
    try:
        with open(file_path, 'r') as f:
            f.seek(file_position)
            
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parsed_data = parse_log_line(line)
                
                if parsed_data:
                    # Display parsed fields
                    print(f"[LOG] pool={parsed_data['pool']} "
                          f"release={parsed_data['release']} "
                          f"upstream_status={parsed_data['upstream_status']} "
                          f"upstream={parsed_data['upstream']}")
                    
                    # Check for failover
                    check_failover(parsed_data)
                    
                    # Track 5xx errors in sliding window
                    is_error = 500 <= parsed_data['upstream_status'] < 600
                    request_window.append(is_error)
                    
                    # Check error rate after each request
                    check_error_rate()
            
            file_position = f.tell()
    
    except FileNotFoundError:
        print(f"[WARN] Log file not found: {file_path}")
    except Exception as e:
        print(f"[ERROR] Failed to read log: {e}")


class LogHandler(FileSystemEventHandler):
    """Watchdog event handler for log file changes"""
    
    def on_modified(self, event):
        if LOG_FILE in event.src_path:
            process_new_lines(LOG_FILE)


def main():
    global is_startup
    
    print("=" * 60)
    print("Nginx Log Watcher - Starting")
    print("=" * 60)
    print(f"Log file: {LOG_FILE}")
    print(f"Window size: {WINDOW_SIZE} requests")
    print(f"Error threshold: {ERROR_THRESHOLD*100:.2f}%")
    print(f"Alert cooldown: {ALERT_COOLDOWN}s ({ALERT_COOLDOWN//60} minutes)")
    print(f"Slack webhook: {'configured' if SLACK_WEBHOOK_URL else 'NOT SET'}")
    print(f"Current time: {get_current_time()}")
    print("=" * 60)
    
    # Wait for log file to exist
    while not os.path.exists(LOG_FILE):
        print(f"[INFO] Waiting for log file: {LOG_FILE}")
        time.sleep(2)
    
    print(f"[INFO] Log file found, processing existing logs...")
    
    # Process existing lines first (startup mode - no alerts)
    is_startup = True
    process_new_lines(LOG_FILE)
    
    print(f"[INFO] Processed {len(request_window)} existing requests")
    if len(request_window) > 0:
        errors = sum(request_window)
        error_rate = errors / len(request_window)
        print(f"[INFO] Initial error rate: {error_rate*100:.2f}% ({errors}/{len(request_window)})")
    print(f"[INFO] Current pool: {current_pool}")
    
    # Now switch to live monitoring mode (alerts enabled)
    is_startup = False
    print("=" * 60)
    print("[INFO] Startup complete. Now monitoring for NEW events...")
    print("=" * 60)
    
    # Start watching for changes
    event_handler = LogHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(LOG_FILE), recursive=False)
    observer.start()
    
    print("[INFO] Watching for log changes...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
        observer.stop()
    
    observer.join()


if __name__ == "__main__":
    main()
