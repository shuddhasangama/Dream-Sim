@echo off
REM ── Run a .sql file against the DEPLOYED database ────────────────────
REM   run-sql.cmd find-test-pair.sql
REM
REM Railway's Console tab is a SHELL, not a query editor — pasting SQL
REM there hands it to bash. This talks to Postgres properly, over the
REM public connection string, from your own machine.
REM
REM Set DB_URL once per terminal, from the Postgres service's Variables
REM tab. Use DATABASE_PUBLIC_URL: the plain DATABASE_URL there is the
REM internal address and only resolves inside Railway.
REM
REM   set DB_URL=postgresql://postgres:...@...proxy.rlwy.net:12345/railway
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: run-sql.cmd ^<file.sql^>
  echo Example: run-sql.cmd find-test-pair.sql
  exit /b 2
)

if "%DB_URL%"=="" (
  echo.
  echo DB_URL is not set. From the Railway Postgres service, open the
  echo Variables tab, copy DATABASE_PUBLIC_URL, then run:
  echo.
  echo     set DB_URL=^<paste it here^>
  echo     run-sql.cmd %~1
  echo.
  exit /b 2
)

REM run-sql.py reads DATABASE_URL; DB_URL is kept separate so this never
REM leaks into a pytest run in the same terminal — the suite silently
REM switches to PostgreSQL when DATABASE_URL is set, and fails, because
REM every test assumes SQLite.
set "DATABASE_URL=%DB_URL%"
python run-sql.py "%~1"
set "DATABASE_URL="
