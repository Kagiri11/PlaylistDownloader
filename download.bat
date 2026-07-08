@echo off
setlocal

:: Strip trailing backslash from script directory
set "DIR=%~dp0"
set "DIR=%DIR:~0,-1%"

echo ==========================================
echo        YouTube Best Quality Downloader
echo ==========================================
echo.

:: If a URL was passed as argument use it, otherwise prompt.
:: Use %* (the whole argument tail) instead of %~1: cmd.exe treats '=' as a
:: token delimiter for %1, so an unquoted URL like ...watch?v=ABC gets truncated
:: at the '='. %* keeps the full string intact. We then strip any surrounding
:: quotes so the value is clean whether the caller quoted it or not.
set "URL=%*"
if defined URL set "URL=%URL:"=%"
if not defined URL set /p "URL=Paste YouTube URL: "

if not defined URL (
    echo No URL provided. Exiting.
    exit /b 1
)

echo.
echo Downloading best quality video...
echo URL: %URL%
echo.

"%DIR%\yt-dlp.exe" --no-playlist --download-archive "%DIR%\downloaded.txt" -f "bv*+ba/b" --merge-output-format mp4 --ffmpeg-location "%DIR%" --js-runtimes "deno:%DIR%\deno.exe" -o "%DIR%\%%(title)s.%%(ext)s" --progress "%URL%"

if %ERRORLEVEL%==0 (
    echo.
    echo Download complete! File saved to: %DIR%
) else (
    echo.
    echo Something went wrong. Check the URL and try again.
)
endlocal
