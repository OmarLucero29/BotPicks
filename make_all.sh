#!/bin/bash
set -e

echo "🚀 BotPicks Runner"

python scripts/test_connections.py
python src/bot/main.py
