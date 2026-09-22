#!/usr/bin/env bash
# Safe preview: writes a CSV report in logs/ and moves NOTHING.
cd "$(dirname "$0")" || exit 1
python3 sort_music.py "$@"
echo
echo "Done. Open the newest logs/report_*.csv"
