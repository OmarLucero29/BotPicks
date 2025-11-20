#!/bin/bash

while true; do
    if git status --porcelain | grep -q .; then
        git add -A
        git commit -m "autosync: $(date +'%Y-%m-%d %H:%M:%S')"
        git push origin main
    fi
    sleep 2
done
