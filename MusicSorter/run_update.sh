#!/usr/bin/env bash
# Expands the per-folder artist rosters (related / similar artists).
cd "$(dirname "$0")" || exit 1
python3 sort_music.py --update-rosters "$@"
