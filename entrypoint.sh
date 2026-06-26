#!/usr/bin/env bash
set -euo pipefail

SERVER="${SERVER:-http://10.170.100.83:80}"
JUDGE_ID="${JUDGE_ID:-PTIT3}"
JUDGE_KEY="${JUDGE_KEY:-PTIT3}"
LOG_FILE="${LOG_FILE:-/app/judge.log}"
LOG_SIZE="${LOG_SIZE:-20M}"
LOG_ROTATE="${LOG_ROTATE:-3}"
LOGROTATE_INTERVAL="${LOGROTATE_INTERVAL:-60}"
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
GITHUB_SYNC_FOLDER="${GITHUB_SYNC_FOLDER:-/app/.local/pregrade}"
APP_USER="${APP_USER:-grader}"
APP_GROUP="${APP_GROUP:-grader}"

cd /app

mkdir -p /app/tmp/labs /app/tmp/locks "$GITHUB_SYNC_FOLDER" "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chown -R "$APP_USER:$APP_GROUP" /app/tmp /app/.local "$LOG_FILE"

cat >/etc/logrotate.d/grader1-judge <<EOF
$LOG_FILE {
    su $APP_USER $APP_GROUP
    size $LOG_SIZE
    rotate $LOG_ROTATE
    missingok
    notifempty
    compress
    copytruncate
}
EOF

run_logrotate_loop() {
    while true; do
        logrotate /etc/logrotate.d/grader1-judge >/dev/null 2>&1 || true
        sleep "$LOGROTATE_INTERVAL"
    done
}

run_logrotate_loop &
LOGROTATE_PID="$!"

GITHUB_SYNC_PID=""
export SERVER JUDGE_ID JUDGE_KEY LOG_FILE GITHUB_REPO GITHUB_TOKEN GITHUB_SYNC_FOLDER

if [ -n "$GITHUB_REPO" ]; then
    runuser -u "$APP_USER" -- bash -c '
        cd /app
        if [ -n "$GITHUB_TOKEN" ]; then
            nohup python3 github_folder_sync.py "$GITHUB_SYNC_FOLDER" "$GITHUB_REPO" --token "$GITHUB_TOKEN" >/dev/null 2>&1 &
        else
            nohup python3 github_folder_sync.py "$GITHUB_SYNC_FOLDER" "$GITHUB_REPO" >/dev/null 2>&1 &
        fi
        echo $! > /app/tmp/github_folder_sync.pid
    '
    GITHUB_SYNC_PID="$(cat /app/tmp/github_folder_sync.pid)"
fi

runuser -u "$APP_USER" -- bash -c '
    cd /app
    nohup python3 main.py --server "$SERVER" --id "$JUDGE_ID" --key "$JUDGE_KEY" > "$LOG_FILE" 2>&1 &
    echo $! > /app/tmp/judge.pid
'

JUDGE_PID="$(cat /app/tmp/judge.pid)"

cleanup() {
    kill "$JUDGE_PID" >/dev/null 2>&1 || true
    if [ -n "$GITHUB_SYNC_PID" ]; then
        kill "$GITHUB_SYNC_PID" >/dev/null 2>&1 || true
    fi
    kill "$LOGROTATE_PID" >/dev/null 2>&1 || true
}
trap cleanup TERM INT

while kill -0 "$JUDGE_PID" >/dev/null 2>&1; do
    sleep 2
done

cleanup
wait "$LOGROTATE_PID" >/dev/null 2>&1 || true
