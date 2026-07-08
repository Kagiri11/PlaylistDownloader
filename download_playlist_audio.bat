@echo off
setlocal

:: Strip trailing backslash from script directory
set "DIR=%~dp0"
set "DIR=%DIR:~0,-1%"

echo ==========================================
echo   YouTube Playlist Audio Downloader
echo ==========================================
echo.

:: --- Pre-flight: required tools must sit next to this script ---
if not exist "%DIR%\yt-dlp.exe" (
    echo ERROR: yt-dlp.exe was not found in this folder:
    echo   %DIR%
    echo Re-download it from https://github.com/yt-dlp/yt-dlp/releases
    pause
    exit /b 1
)
if not exist "%DIR%\ffmpeg.exe" (
    echo ERROR: ffmpeg.exe was not found in this folder:
    echo   %DIR%
    echo It is required to convert audio to MP3. Download it once from
    echo   https://github.com/BtbN/FFmpeg-Builds/releases
    echo and copy ffmpeg.exe here. See the README "Requirements" section.
    pause
    exit /b 1
)

:: Deno is optional: it helps yt-dlp solve YouTube's JS challenges.
:: Use it only when present so a fresh setup still works.
set "JSRT="
if exist "%DIR%\deno.exe" (
    set "JSRT=--js-runtimes "deno:%DIR%\deno.exe""
) else (
    echo NOTE: deno.exe not found - continuing without it. Downloads may be
    echo less reliable. See the README "Requirements" section to add it.
    echo.
)

:: If a URL was passed as argument use it, otherwise prompt.
:: Use %* (the whole argument tail) instead of %~1: cmd.exe treats '=' as a
:: token delimiter for %1, so an unquoted URL like ...list=ABC gets truncated
:: at the '='. %* keeps the full string intact. We then strip any surrounding
:: quotes so the value is clean whether the caller quoted it or not.
set "URL=%*"
if defined URL set "URL=%URL:"=%"
if not defined URL set /p "URL=Paste YouTube Playlist URL: "

if not defined URL (
    echo No URL provided. Exiting.
    pause
    exit /b 1
)

echo.
echo Downloading playlist as high quality MP3 audio...
echo URL: %URL%
echo.

"%DIR%\yt-dlp.exe" ^
    --yes-playlist ^
    --download-archive "%DIR%\downloaded_audio.txt" ^
    -f "bestaudio/best" ^
    --extract-audio ^
    --audio-format mp3 ^
    --audio-quality 0 ^
    --embed-thumbnail ^
    --add-metadata ^
    --ffmpeg-location "%DIR%" ^
    %JSRT% ^
    -o "%DIR%\%%(playlist_title)s\%%(playlist_index)s - %%(title)s.%%(ext)s" ^
    --progress ^
    --no-continue ^
    "%URL%"

if %ERRORLEVEL%==0 (
    echo.
    echo Playlist audio download complete! Files saved to: %DIR%
) else (
    echo.
    echo Something went wrong. See the messages above for the reason.
)
endlocal
pause
