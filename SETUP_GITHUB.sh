#!/bin/bash
# ============================================================
# Run this script ONCE to push Theseus to GitHub
# ============================================================
#
# PREREQUISITES:
#   1. Create a new repository on github.com:
#      - Go to https://github.com/new
#      - Name it "Theseus" (or whatever you prefer)
#      - Choose Public or Private
#      - Do NOT initialize with README (we already have content)
#      - Click "Create repository"
#
#   2. If you haven't authenticated git with GitHub:
#      - Install GitHub CLI: brew install gh
#      - Authenticate: gh auth login
#      - OR use a Personal Access Token
#
#   3. Replace YOUR_USERNAME below with your GitHub username
#
# ============================================================

GITHUB_USERNAME="YOUR_USERNAME"  # <-- CHANGE THIS
REPO_NAME="Theseus"

cd ~/Desktop/Theseus

# Add the remote
git remote add origin "https://github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"

# Push
git push -u origin main

echo ""
echo "✓ Theseus is now live at: https://github.com/${GITHUB_USERNAME}/${REPO_NAME}"
echo ""
echo "To auto-sync after changes, you can run:"
echo "  cd ~/Desktop/Theseus && git add -A && git commit -m 'Update' && git push"
