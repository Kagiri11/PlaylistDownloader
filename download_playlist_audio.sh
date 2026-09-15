#!/usr/bin/env bash
set -u

# Directory this script lives in (download records go here)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Downloaded files are saved in your Music folder
OUT="$HOME/Music"

echo "=========================================="
echo "  YouTube Playlist Audio Downloader"
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
    echo "It is required to convert audio to MP3. Install it with your"
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
    read -r -p "Paste YouTube Playlist URL: " URL
fi

if [ -z "$URL" ]; then
    echo "No URL provided. Exiting."
    exit 1
fi

echo
echo "Downloading playlist as high quality MP3 audio..."
echo "URL: $URL"
echo

# Name files "Song - Artist ft Featured". Fields: song, main (artist), feat.
# Uses YouTube Music's track/artist data when present, otherwise parses the
# video title ("Artist ft. X - Song (Official Video)"), dropping junk like
# "(Official Video)" or "[Lyrics]". Brackets after a feat, e.g. "(Remix)", go in
# extra and stay with the song. At most 2 featured artists are kept, because
# YouTube Music sometimes lists songwriters as artists. It can also repeat the
# main artist in that list, so repeats are dropped from feat (ignoring case).
# The @@@ separator joins
# several fields into one string so a rule only matches when earlier rules
# found nothing.
NAMING=(
    --parse-metadata '%(track|)s@@@%(artists.0|)s@@@%(artists.1\:3|)l:(?i)^(?P<song>.+)@@@(?P<main>.+)@@@(?:(?P=main)(?:, |$))*(?P<feat>.+?)?(?:, (?P=main))*$'
    --parse-metadata '%(song|)s@@@%(title)s:^@@@(?P<main>.+?)\s+[-\u2013\u2014]\s+(?P<song>.+)$'
    --parse-metadata '%(song|)s@@@%(title)s:^@@@(?P<song>.+)$'
    --parse-metadata '%(feat|)s@@@%(main|)s:(?i)^@@@(?P<main>.+?)\s+(?:ft\.?|feat\.?|featuring)\s+(?P<feat>.+)$'
    --replace-in-metadata song '(?i)\s*[(\[][^)\]]*\b(?:official|lyrics?|audio|video|visuali[sz]er|hd|hq|4k|mv)\b[^)\]]*[)\]]' ''
    --parse-metadata '%(feat|)s@@@%(song)s:(?i)^@@@(?P<song>.+?)\s*[(\[]?\s*\b(?:ft\.?|feat\.?|featuring)\s+(?P<feat>[^()\[\]]+?)\s*[)\]]?\s*(?P<extra>[(\[].*)?$'
    --replace-in-metadata song '(?i)\s*[(\[]\s*(?:ft\.?|feat\.?|featuring)\s[^)\]]*[)\]]' ''
    # Write the cleaned names into the MP3 tags too
    --parse-metadata '%(song)s%(extra& {}|)s:(?P<meta_title>.+)'
    --parse-metadata '%(main|)s%(feat& ft {}|)s:(?P<meta_artist>.+)'
)

mkdir -p "$OUT"

"$YTDLP" \
    --yes-playlist \
    --download-archive "$DIR/downloaded_audio.txt" \
    -f "bestaudio/best" \
    --extract-audio \
    --audio-format mp3 \
    --audio-quality 0 \
    --embed-thumbnail \
    --add-metadata \
    "${ARGS[@]}" \
    "${NAMING[@]}" \
    -o "$OUT/%(playlist_title)s/%(song,title)s%(extra& {}|)s%(main& - {}|)s%(feat& ft {}|)s.%(ext)s" \
    --progress \
    --no-continue \
    "$URL"
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
    echo "Playlist audio download complete! Files saved to: $OUT"
else
    echo "Something went wrong. See the messages above for the reason."
fi
exit "$STATUS"
