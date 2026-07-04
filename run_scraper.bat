@echo off
REM ---------------------------------------------------------------
REM Moneycontrol IT Scraper - one-click runner
REM Runs a full scrape and opens the exports folder when done.
REM Any arguments are passed through, e.g.:
REM   run_scraper.bat --dry-run
REM   run_scraper.bat --symbols TCS,INFY --csv
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo ============================================
echo  Moneycontrol IT Scraper
echo ============================================
echo.

python -X utf8 main.py %*
set EXITCODE=%ERRORLEVEL%

echo.
if %EXITCODE% NEQ 0 (
    echo Run FAILED with exit code %EXITCODE%. Check the latest file in the logs folder.
) else (
    echo Run completed successfully. Opening exports folder...
    if exist exports start "" explorer "%~dp0exports"
)

echo.
pause
exit /b %EXITCODE%
