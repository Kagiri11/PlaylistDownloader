# PlaylistDownloader

Simple one-click Windows batch scripts for downloading YouTube videos and playlists using [yt-dlp](https://github.com/yt-dlp/yt-dlp). No installation, no Python, no command-line knowledge required — just double-click and paste a URL.

## What's included

| File | What it does |
|---|---|
| `download.bat` | Downloads a **single video** in the best available quality as MP4 |
| `download_playlist.bat` | Downloads a **whole playlist** as MP4 videos, organized into a folder named after the playlist |
| `download_playlist_audio.bat` | Downloads a **whole playlist as high-quality MP3 audio** with embedded cover art and metadata — great for music playlists |
| `yt-dlp.exe` | The downloader engine (bundled so you don't have to find it yourself) |
| `MusicSorter/` | Sorts downloaded tracks into genre folders and renames them `Artist (ft Featured) - Title` (Linux, Python) — see [MusicSorter/README.md](MusicSorter/README.md) |

## Requirements

The scripts expect two extra programs to sit **in the same folder** as the scripts. They are too large to include in this repository, so download them once:

1. **FFmpeg** (required — converts/merges audio and video)
   - Download the latest `ffmpeg-master-latest-win64-gpl.zip` from [BtbN's FFmpeg builds](https://github.com/BtbN/FFmpeg-Builds/releases)
   - Open the zip, go into the `bin` folder, and copy `ffmpeg.exe` (optionally also `ffprobe.exe`) into this folder

2. **Deno** (recommended — lets yt-dlp solve YouTube's JavaScript challenges, which keeps downloads working reliably)
   - Download `deno-x86_64-pc-windows-msvc.zip` from [Deno releases](https://github.com/denoland/deno/releases)
   - Extract `deno.exe` into this folder

When you're done, the folder should look like:

```
PlaylistDownloader\
├── download.bat
├── download_playlist.bat
├── download_playlist_audio.bat
├── yt-dlp.exe
├── ffmpeg.exe        <- you add this
└── deno.exe          <- you add this
```

## How to use

### Easiest way (double-click)

1. Double-click the script you want (e.g. `download_playlist_audio.bat`)
2. Paste the YouTube URL when asked and press **Enter**
3. Wait — files appear in this folder (playlists get their own subfolder named after the playlist)

### From a terminal

You can also pass the URL as an argument, quoted or unquoted, from **cmd** or **PowerShell**:

```bat
download_playlist_audio.bat https://www.youtube.com/playlist?list=XXXXXXXXXX
```

```powershell
& .\download_playlist_audio.bat "https://www.youtube.com/playlist?list=XXXXXXXXXX"
```

> Note: if the URL contains an `&` (e.g. `watch?v=...&list=...`), you must quote it — otherwise the shell treats everything after `&` as a separate command.

## One command for Windows, Linux and macOS

If Python 3 is installed, `downloader.py` detects your operating system and runs the matching script: the `.bat` files on Windows, the `.sh` files on Linux and macOS. Each OS still needs the tools listed in its own Requirements section.

```bash
python downloader.py                                   # menu: video / playlist / audio
python downloader.py audio "https://www.youtube.com/playlist?list=XXXXXXXXXX"
```

Modes: `video` (single video), `playlist` (playlist as MP4), `audio` (playlist as MP3). Leave out the URL to be prompted for one. On Linux, use `python3` if `python` isn't available.

## Linux

The `.sh` scripts do the same thing as the `.bat` files: `download.sh`, `download_playlist.sh` and `download_playlist_audio.sh`.

### Requirements

Each script looks for its tools **next to the script first**, then on your `PATH`.

1. **yt-dlp** (required) — `pipx install yt-dlp`, or download the `yt-dlp` Linux binary from [yt-dlp releases](https://github.com/yt-dlp/yt-dlp/releases) into this folder and `chmod +x yt-dlp`. Distro packages are often out of date, which breaks YouTube downloads.
2. **FFmpeg** (required) — `sudo apt install ffmpeg` (or your distro's equivalent)
3. **Deno** (recommended) — `curl -fsSL https://deno.land/install.sh | sh`, or put the `deno` binary in this folder. Needs a recent yt-dlp that supports `--js-runtimes`; older versions skip it with a note.

### How to use

```bash
chmod +x *.sh        # once
./download_playlist_audio.sh "https://www.youtube.com/playlist?list=XXXXXXXXXX"
```

Run without a URL to be prompted for one. Always quote URLs — `&` and `?` are special characters in the shell.

On Linux, downloads are saved in your **Music folder** (`~/Music`) instead of the script folder, with the same file and playlist-folder names as on Windows. The download records (`downloaded.txt`, `downloaded_audio.txt`) stay next to the scripts. To update yt-dlp, run `pipx upgrade yt-dlp`, or `./yt-dlp -U` for the standalone binary.

## Where do my files go?

- **Single videos** → saved directly in this folder as `Title.mp4`
- **Playlists (video)** → `<Playlist Name>\Title.mp4`
- **Playlists (audio)** → `<Playlist Name>\Song - Artist ft Featured Artist.mp3`, e.g. `Essence - Wizkid ft Tems.mp3`, with album art embedded

### How audio files are named

Song and artist names come from YouTube Music's track info when a video has it. Otherwise they are read from the video title, which works for the usual `Artist - Song (Official Video) ft. Other Artist` style. Extras like `(Official Video)`, `(Audio)` or `[Lyrics]` are removed, while things like `(Remix)` are kept. The same cleaned names are written into the MP3's title and artist tags. At most two featured artists are kept, because YouTube Music sometimes lists songwriters as artists. If YouTube Music repeats the main artist in the featured list, the repeat is dropped.

Titles that don't follow `Artist - Song` fall back to the cleaned title (with no artist). If an uploader writes `Song - Artist`, the two end up swapped.

## Sorting the downloads (MusicSorter)

Downloading is only half the job; `MusicSorter/` takes it from there. It picks
up everything in `~/Music` (playlist subfolders included), identifies each track
against Spotify / Last.fm / MusicBrainz, renames it to
`Artist (ft Featured) - Title` — with a `[Extended]` tag for extended cuts —
and files it into the right genre folder. Duplicates you already own go to
`Ignored`, anything it isn't sure about goes to `_Review`.

```
cd MusicSorter
cp config.example.ini config.ini     # set your paths + free API keys
./run_dryrun.sh                      # preview: writes logs/report_*.csv, moves nothing
./run_sort.sh                        # do it for real
```

Full details in [MusicSorter/README.md](MusicSorter/README.md).

## Skipping already-downloaded tracks

The scripts keep a record of everything downloaded (`downloaded.txt` for video, `downloaded_audio.txt` for audio). If you run the same playlist again, only **new** items are fetched — handy for playlists you keep adding songs to.

**Gotcha:** if you *move or delete* a downloaded file and want it again, the script will still skip it because it's in the record. Fix: open the record file in Notepad and delete the line containing that video's ID (or delete the whole record file to re-download everything).

## Troubleshooting

| Problem | Fix |
|---|---|
| `'ffmpeg' not found` or audio conversion fails | Make sure `ffmpeg.exe` is in the same folder as the scripts |
| Downloads suddenly stop working / "Sign in to confirm" errors | YouTube changed something. Update the engine: open a terminal in this folder and run `yt-dlp.exe -U`. Also make sure `deno.exe` is present |
| A playlist item is skipped but you don't have the file | It's in the download record — see the section above |
| `ffmpeg.exe was not found` message | The scripts check for FFmpeg before starting — follow the on-screen link, or see **Requirements** above |
| URL with `&` behaves strangely | Quote the URL: `download.bat "https://...watch?v=abc&t=30"` |

## Updating yt-dlp

YouTube changes frequently; the bundled `yt-dlp.exe` will eventually go stale. To update it, open a terminal in this folder and run:

```
yt-dlp.exe -U
```

## Credits & license

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the engine doing all the real work (released into the public domain under the [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE))
- [FFmpeg](https://ffmpeg.org/) — audio/video processing
- [Deno](https://deno.com/) — JavaScript runtime used for YouTube challenge solving

The batch scripts in this repository are free to use, copy, and modify.

**Please respect copyright.** Only download content you have the right to download (your own uploads, Creative Commons content, etc.) and follow YouTube's Terms of Service in your jurisdiction.
