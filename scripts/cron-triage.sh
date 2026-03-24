#!/bin/bash
# Gemini triage cron runner for all agents.
# Called by system crontab. Runs on Mac Mini host (not in container).
set -e

BOTY_AGENT_DIR="/Users/boty/nanoclaw/boty-agent"
SA_PATH="/Users/boty/nanoclaw/adp-service-account.json"
LOG_DIR="/Users/boty/nanoclaw/logs"

export GOOGLE_APPLICATION_CREDENTIALS="$SA_PATH"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

SCRIPT="$1"   # triage_gemini.py or chat_triage_gemini.py
AGENT="$2"    # boty or thais

if [ -z "$SCRIPT" ] || [ -z "$AGENT" ]; then
    echo "Usage: cron-triage.sh <script> <agent>"
    exit 1
fi

CONFIG="$BOTY_AGENT_DIR/agents/$AGENT/config.json"
LOGFILE="$LOG_DIR/gemini-$AGENT-$(basename $SCRIPT .py).log"

cd "$BOTY_AGENT_DIR/modules"
python3 "$SCRIPT" --config "$CONFIG" >> "$LOGFILE" 2>&1
