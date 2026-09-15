#!/usr/bin/env python3
"""Cross-platform entry point: detects the OS and runs the matching script.

Windows       -> download*.bat
Linux / macOS -> download*.sh

Usage:
    python downloader.py                     # pick a mode from a menu, then paste a URL
    python downloader.py audio               # pick the mode, paste a URL when asked
    python downloader.py playlist "<URL>"    # fully non-interactive
"""
import argparse
import platform
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent

# mode -> (script base name, menu description)
MODES = {
    "video": ("download", "Single video (best quality MP4)"),
    "playlist": ("download_playlist", "Whole playlist as MP4 videos"),
    "audio": ("download_playlist_audio", "Whole playlist as MP3 audio"),
}


def choose_mode():
    print("What do you want to download?")
    names = list(MODES)
    for i, name in enumerate(names, 1):
        print(f"  {i}. {MODES[name][1]}")
    while True:
        try:
            choice = input(f"Enter 1-{len(names)}: ").strip()
        except EOFError:
            sys.exit("No choice made. Exiting.")
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            return names[int(choice) - 1]
        if choice in MODES:
            return choice
        print("Invalid choice, try again.")


def build_command(system, script, url):
    if system == "Windows":
        # Run through cmd.exe ourselves so the URL stays quoted: an unquoted '&'
        # would split the command. /s strips only the outer pair of quotes.
        if url and '"' in url:
            sys.exit('URL must not contain double quotes (").')
        inner = f'"{script}"' + (f' "{url}"' if url else "")
        return f'cmd /d /s /c "{inner}"'
    # Invoke through bash so the scripts work even without the executable bit.
    return ["bash", str(script)] + ([url] if url else [])


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube videos/playlists on Windows, Linux or macOS."
    )
    parser.add_argument("mode", nargs="?", choices=MODES, help="what to download")
    parser.add_argument("url", nargs="?", help="YouTube URL (prompted for if omitted)")
    args = parser.parse_args()

    system = platform.system()
    if system == "Windows":
        ext = ".bat"
    elif system in ("Linux", "Darwin"):
        ext = ".sh"
    else:
        sys.exit(f"Unsupported operating system: {system}")

    print(f"Detected OS: {system} {platform.release()} -> using {ext} scripts\n", flush=True)

    mode = args.mode or choose_mode()
    script = DIR / (MODES[mode][0] + ext)
    if not script.is_file():
        sys.exit(f"ERROR: {script.name} was not found in {DIR}")

    result = subprocess.run(build_command(system, script, args.url), cwd=DIR)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
