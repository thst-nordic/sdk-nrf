@echo off

rem ARGUMENTS
set PLATFORM=%1
set DRYRUN=%2
if "%PLATFORM%" == "" (
    set PLATFORM=nrf9160_pca10090ns
)

echo.
echo.
echo #########  PLATFORM = %PLATFORM%
if not "%DRYRUN%" == "" (
    set DRYRUN=--dry-run
    echo #########  THIS IS A DRY RUN ######
)
echo.
echo.



rem SETUP WORKSPACE
cd C:\jenkins
west init -l nrf/
west update
set WORKSPACE=C:\jenkins




rem COMPILE APPS & SAMPLES
python zephyr\scripts\sanitycheck %DRYRUN% --platform %PLATFORM% -t ci_build --build-only --board-root %WORKSPACE%\nrf\boards --testcase-root %WORKSPACE%\nrf\applications --testcase-root %WORKSPACE%\nrf\samples --disable-unrecognized-section-test --ninja --disable-size-report --inline-logs
call :errorcheck
echo #########  SUCCESS  #########
exit /B 0
goto :eof










:errorcheck
if %ERRORLEVEL% neq 0 (
    echo.
    echo #######################################
    echo There was an error compiling ... exiting
    echo #######################################
    call :halt 1
) else (
    echo.Next..
)
goto :eof


:__SetErrorLevel
exit /b %time:~-2%
goto :eof

:__ErrorExit
rem Creates a syntax error, stops immediately
()
goto :eof

:: Sets the errorlevel and stops the batch immediately
:halt
call :__SetErrorLevel %1
call :__ErrorExit 2> nul
goto :eof

