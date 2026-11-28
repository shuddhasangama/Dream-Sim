<#
  LOCAL ONLY launcher for DhaShu Dream-Sim. Contains no secrets: every value comes from .env.local
  (copy .env.local.example, replace each CHANGE_ME, keep .env.local git-ignored; see docs/LOCAL_SETUP.md).
  The app reads no env file, so this script loads .env.local into the current process and runs one part.

  Usage (from the repo root, Windows PowerShell):
    .\dev-local.ps1 check      # show which DB the app would connect to
    .\dev-local.ps1 init       # apply schema_postgres.sql + admin schema to dhashu_local
    .\dev-local.ps1 seed       # insert 100 synthetic users (seed 42) into dhashu_local
    .\dev-local.ps1 migrate    # Alembic DRY RUN: print the SQL for dhashu_local (-Apply to run it)
    .\dev-local.ps1 test       # pytest with DATABASE_URL removed; Postgres tests -> dhashu_test
    .\dev-local.ps1 web        # backend      http://127.0.0.1:5000
    .\dev-local.ps1 worker     # bgv_worker.py (idle: web never queues checks)
    .\dev-local.ps1 admin      # admin dash   http://127.0.0.1:5001
    .\dev-local.ps1 admin-create -Email you@example.local   # interactive: password + authenticator code
    .\dev-local.ps1 admin-reset  -Email you@example.local   # interactive: new password + authenticator
    .\dev-local.ps1 mobile     # Vite preview http://127.0.0.1:5173 (in-browser mock data)
    .\dev-local.ps1 mobile-test
#>
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet('check', 'init', 'seed', 'test', 'web', 'worker', 'admin', 'admin-create', 'admin-reset', 'migrate', 'mobile', 'mobile-test')]
  [string]$Part,
  [string]$Email = 'owner@local.test',
  [switch]$Apply,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Rest = @()
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Root '.env.local'
if (-not (Test-Path $EnvFile)) { throw '.env.local is missing. Copy .env.local.example to .env.local (see docs/LOCAL_SETUP.md).' }
# .env.local holds local passwords/keys: refuse to run unless git ignores it.
& git check-ignore -q -- .env.local
if ($LASTEXITCODE -ne 0) { throw '.env.local is not git-ignored. Run: Add-Content .git\info\exclude ".env.local"' }

$Worker = @{}
$Placeholders = @()
foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
  if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
  $name, $value = $line -split '=', 2
  $name = $name.Trim()
  if ($value -match 'CHANGE_ME') { $Placeholders += $name }
  if ($name.StartsWith('WORKER__')) { $Worker[$name.Substring(8)] = $value; continue }
  Set-Item -Path "Env:$name" -Value $value
}
if ($Placeholders.Count) { throw ('Replace CHANGE_ME in .env.local for: ' + ($Placeholders -join ', ')) }
# Hard guards: never production providers, never PG14 on 5432.
# sec-login: real sign-in is ON unless AUTH_ENABLED is explicitly off, and off is accepted only
# together with DHASHU_LOCAL_HARNESS=1 (local_harness.py). Local runs never use real OTP sign-in.
$env:AUTH_ENABLED = '0'
if ($env:DHASHU_LOCAL_HARNESS -ne '1') { throw 'Set DHASHU_LOCAL_HARNESS=1 in .env.local (local sign-in needs the local harness).' }
if ($env:PAYMENTS_ENABLED -and -not $env:DHASHU_PAYMENT_BYPASS) {
  Write-Warning 'PAYMENTS_ENABLED is retired (sec-pay). Add DHASHU_PAYMENT_BYPASS=1 to .env.local to keep paid steps unlocked locally.'
}
if ($env:DATABASE_URL -notmatch '@(localhost|127\.0\.0\.1):5433/dhashu_local$') { throw 'DATABASE_URL must be localhost:5433/dhashu_local' }
if ($env:SIGNZY_ENV -ne 'preproduction' -or $env:SIGNZY_PRODUCTION_ENABLED -ne '0') { throw 'Signzy must stay preproduction/disabled' }

switch ($Part) {
  'check' {
    & $Py -c "import db; c=db.get_connection(); i=c.info; print('host=%s port=%s dbname=%s server=%s' % (i.host, i.port, i.dbname, c.execute('show server_version').fetchone()['server_version'])); c.close()"
  }
  'init' {
    & $Py -c "import db; c=db.get_connection(); i=c.info; assert (i.host in ('localhost','127.0.0.1','::1') and int(i.port)==5433 and i.dbname=='dhashu_local'), 'wrong database'; print('Initialising', i.host, i.port, i.dbname); c.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Database check failed; nothing initialised.' }
    & $Py -m admin_dashboard.manage init
  }
  'seed' { & $Py generate_users.py --count 100 --seed 42 --write-db }
  'migrate' {
    # Local dhashu_local only (DATABASE_URL guard above). Dry run prints SQL and changes nothing.
    if ($Apply) { & $Py -m alembic upgrade head; & $Py -m alembic current }
    else { & $Py -m alembic upgrade head --sql; Write-Host 'DRY RUN only. Re-run with -Apply to migrate dhashu_local.' }
  }
  'test' {
    $dsn = Join-Path $Root '.venv\dhashu-test-dsn.txt'
    Set-Content -Path $dsn -Value $env:TEST_DATABASE_URL -Encoding ascii -NoNewline
    $env:AUTH_TEST_POSTGRES_DSN_FILE = $dsn
    $env:ADMIN_TEST_POSTGRES_URL = $env:TEST_DATABASE_URL
    $env:TEST_AVATAR_POSTGRES_URL = $env:TEST_DATABASE_URL
    # Tests must never see the app database, nor the dev switches above.
    foreach ($n in 'DATABASE_URL', 'TEST_DATABASE_URL', 'ADMIN_REPORT_DATABASE_URL', 'ADMIN_REPORT_DB_PASSWORD', 'SECRET_KEY', 'ADMIN_TOTP_ENCRYPTION_KEY', 'ADMIN_PUBLIC_ORIGIN', 'ADMIN_ALLOW_HTTP',
      'DEMO_MODE', 'DHASHU_SIMULATED_CLOCK', 'DHASHU_RESTAURANT_MODE', 'DHASHU_IDENTITY_VERIFICATION_MODE', 'PAYMENTS_ENABLED', 'DHASHU_PAYMENT_BYPASS', 'AUTH_ENABLED',
      'DHASHU_BILLING_MODE', 'VERIFICATION_DELIVERY', 'SIGNZY_ENV', 'SIGNZY_PRODUCTION_ENABLED', 'DHASHU_GURU_AI_ENABLED', 'DHASHU_LOCAL_HARNESS') {
      Remove-Item "Env:$n" -ErrorAction SilentlyContinue
    }
    & $Py -m pytest -q -p no:cacheprovider @Rest
  }
  'web' {
    # Schema once at startup (perf-init): requests run no DDL.
    & $Py -c "import db; c=db.get_connection(); db.init_db(c); c.close(); print('Schema ready.')"
    if ($LASTEXITCODE -ne 0) { throw 'Schema initialisation failed.' }
    $env:DHASHU_FLASK_DEBUG = '1'; & $Py app.py   # debugger/reloader: local only, loopback-bound
  }
  'worker' {
    foreach ($k in $Worker.Keys) { Set-Item -Path "Env:$k" -Value $Worker[$k] }
    & $Py -u bgv_worker.py
  }
  'admin' {
    & $Py -c "from admin_dashboard.wsgi import app; app.run(host='127.0.0.1', port=5001)"
  }
  'admin-create' { & $Py -m admin_dashboard.manage create --email $Email --role owner --apply }
  'admin-reset' { & $Py -m admin_dashboard.manage reset --email $Email --apply }
  'mobile' { Set-Location (Join-Path $Root 'mobile'); npm run dev -- --port 5173 --strictPort }
  'mobile-test' { Set-Location (Join-Path $Root 'mobile'); npm test }
}
