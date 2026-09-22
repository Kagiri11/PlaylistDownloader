#!/usr/bin/env bash
# For real: moves intake -> To Sort, then sorts + renames.
cd "$(dirname "$0")" || exit 1
python3 sort_music.py --apply "$@"
