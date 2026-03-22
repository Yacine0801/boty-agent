#!/bin/bash
REPO_URL="https://github.com/Yacine0801/boty-agent.git"
TARGET_DIR="/home/node/agents/boty"
echo "[container_init] $(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ -d "$TARGET_DIR/.git" ]; then
  cd "$TARGET_DIR" && git pull --ff-only
else
  mkdir -p "$(dirname $TARGET_DIR)" && git clone "$REPO_URL" "$TARGET_DIR"
fi
ls "$TARGET_DIR/modules/"
