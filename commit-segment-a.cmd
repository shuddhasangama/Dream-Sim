@echo off
REM ── Segment A: create the branch, run the tests, commit ──────────────
REM Double-click this, or run it from a terminal in the repo root.
REM It stops before pushing so you can review the diff first.

cd /d "%~dp0"

echo.
echo === Creating branch segment-a-front-door ===
git rev-parse --verify segment-a-front-door >nul 2>&1
if errorlevel 1 (
  git checkout -b segment-a-front-door
) else (
  git checkout segment-a-front-door
)
if errorlevel 1 goto :fail

echo.
echo === Running the test suite ===
REM smoke_test.py is excluded because it is already broken on master:
REM it imports load_users from generate_users, which does not exist.
python -m pytest -q --ignore=smoke_test.py
if errorlevel 1 (
  echo.
  echo Tests failed. Nothing has been committed.
  goto :fail
)

echo.
echo === Staging ===
git add onboarding.py test_onboarding.py app.py db.py generate_users.py test_generate_users.py schema.sql schema_postgres.sql static\style.css templates\_wizard.html templates\signup.html templates\onboard_vision.html templates\onboard_stats.html templates\onboard_chemistry.html templates\onboard_done.html commit-segment-a.cmd
git status --short

echo.
echo === Committing ===
git commit -F commit-message.txt
if errorlevel 1 goto :fail

echo.
echo Committed on branch segment-a-front-door.
echo.
echo Review it:   git show --stat
echo Push it:     git push -u origin segment-a-front-door
echo Undo it all: git checkout master ^&^& git branch -D segment-a-front-door
echo.
pause
exit /b 0

:fail
echo.
echo Stopped. Nothing was committed.
pause
exit /b 1
