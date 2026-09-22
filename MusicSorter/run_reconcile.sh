#!/usr/bin/env bash
# Shows which already-sorted songs sit in the wrong folder per the rosters.
# Writes logs/reconcile_*.csv and moves NOTHING. To apply:
#   python3 sort_music.py --reconcile --apply
cd "$(dirname "$0")" || exit 1
python3 sort_music.py --reconcile "$@"
