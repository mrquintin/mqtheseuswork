#!/bin/bash
# ============================================================
# Auto-sync Theseus to GitHub
# Run manually: ./sync.sh
# Or schedule with cron: crontab -e → */30 * * * * ~/Desktop/Theseus/sync.sh
# (syncs every 30 minutes)
# ============================================================

cd ~/Desktop/Theseus

# Check if there are changes
if [ -z "$(git status --porcelain)" ]; then
    echo "No changes to sync."
    exit 0
fi

# Stage, commit, push
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
git add -A
git commit -m "Auto-sync: ${TIMESTAMP}"
git push origin main

echo "✓ Synced to GitHub at ${TIMESTAMP}"
