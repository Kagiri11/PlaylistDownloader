#!/usr/bin/env bash
set -u

# Directory this script lives in (download records go here)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Downloaded files are saved in your Music folder
OUT="$HOME/Music"

echo "=========================================="
echo "       YouTube Best Quality Downloader"
echo "=========================================="
echo

# Prefer a copy of the tool next to this script, otherwise use the one on PATH.
find_tool() {
    if [ -x "$DIR/$1" ]; then
        echo "$DIR/$1"
    else
        command -v "$1"
    fi
}

# --- Pre-flight: required tools ---
YTDLP="$(find_tool yt-dlp)"
if [ -z "$YTDLP" ]; then
    echo "ERROR: yt-dlp was not found next to this script or on your PATH."
    echo "Install it (e.g. 'pipx install yt-dlp') or download the Linux binary from"
    echo "  https://github.com/yt-dlp/yt-dlp/releases"
    echo "and save it as '$DIR/yt-dlp' (then chmod +x it)."
    exit 1
fi
FFMPEG="$(find_tool ffmpeg)"
if [ -z "$FFMPEG" ]; then
    echo "ERROR: ffmpeg was not found next to this script or on your PATH."
    echo "It is required to merge video and audio into MP4. Install it with your"
    echo "package manager, e.g. 'sudo apt install ffmpeg'."
    exit 1
fi

ARGS=(--ffmpeg-location "$FFMPEG")

# Deno is optional: it helps yt-dlp solve YouTube's JS challenges.
# Use it only when present (and supported by this yt-dlp) so a fresh setup still works.
DENO="$(find_tool deno)"
if [ -z "$DENO" ]; then
    echo "NOTE: deno not found - continuing without it. Downloads may be"
    echo "less reliable. See the README \"Requirements\" section to add it."
    echo
elif "$YTDLP" --help | grep -q -- --js-runtimes; then
    ARGS+=(--js-runtimes "deno:$DENO")
else
    echo "NOTE: deno found, but this yt-dlp is too old to use it. Update yt-dlp."
    echo
fi

# If a URL was passed as argument use it, otherwise prompt.
URL="$*"
if [ -z "$URL" ]; then
    read -r -p "Paste YouTube URL: " URL
fi

if [ -z "$URL" ]; then
    echo "No URL provided. Exiting."
    exit 1
fi

echo
echo "Downloading best quality video..."
echo "URL: $URL"
echo

mkdir -p "$OUT"

"$YTDLP" \
    --no-playlist \
    --download-archive "$DIR/downloaded.txt" \
    -f "bv*+ba/b" \
    --merge-output-format mp4 \
    "${ARGS[@]}" \
    -o "$OUT/%(title)s.%(ext)s" \
    --progress \
    "$URL"
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
    echo "Download complete! File saved to: $OUT"
else
    echo "Something went wrong. See the messages above for the reason."
fi
exit "$STATUS"
