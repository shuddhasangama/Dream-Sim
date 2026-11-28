# Local setup on Windows (DhaShu Dream-Sim)

Run the Flask backend, BGV worker, admin dashboard and mobile app **entirely on your own machine**. This setup:
- never connects to production or staging;
- calls no live provider (Twilio, MSG91, Razorpay live, Signzy production, OpenAI);
- never deploys.

Commands are PowerShell, run from the repo root unless a step says otherwise.

## 1. Prerequisites

| Tool | Version / notes |
|---|---|
| Python | **3.12**, invoked as `py -3.12`. If plain `python` resolves to `C:\Windows\System32\python.exe` on your machine, don't use it. After step 2, always use `.venv\Scripts\python.exe`. |
| PostgreSQL | **16 on port 5433** (user `postgres`). If you also have another PostgreSQL (for example 14 on 5432), leave it alone; everything here uses 5433. |
| Node / npm | Node 22+ and npm 10+ (tested with Node 26 / npm 11). |
| Java | **Temurin JDK 21**, with `JAVA_HOME` set in your **User** environment. Don't use Android Studio's bundled Java 25: the project's Gradle 8.14.3 doesn't support it. |
| Android SDK | Only for the emulator: `ANDROID_HOME` set, API 36 platform, and an emulator such as Pixel_7. |
| Gradle | Use the wrapper (`gradlew.bat`). **Don't upgrade Gradle.** If an IDE or VS Code extension rewrites `mobile/android/gradle/wrapper/gradle-wrapper.properties`, restore it with `git restore`. |

## 2. Python environment

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt pytest
```
Don't add pytest (or anything else that's local-only) to `requirements.txt`.

## 3. Databases (PostgreSQL 16, port 5433)

Create two databases. The app uses `dhashu_local`; the Postgres-backed tests use `dhashu_test`, so they never touch your app data.

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -p 5433 -U postgres -c "CREATE DATABASE dhashu_local;" -c "CREATE DATABASE dhashu_test;"
```

## 4. Local settings: `.env.local`

```powershell
Copy-Item .env.local.example .env.local
Add-Content .git\info\exclude ".env.local"     # keep it out of git (once per clone)
git check-ignore -v .env.local                  # must print a match
```

Edit `.env.local` and replace **every** `CHANGE_ME`:
- **Postgres password:** your own local password, in `DATABASE_URL` and `TEST_DATABASE_URL`.
- **`SECRET_KEY`:** generate it with `.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"`.
- **`ADMIN_TOTP_ENCRYPTION_KEY` and `WORKER__SIGNZY_RECEIPT_ENCRYPTION_KEY`:** run `.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` once for each, so they get two **different** keys.

`dev-local.ps1` refuses to run while any `CHANGE_ME` remains, if `.env.local` isn't git-ignored, or if `DATABASE_URL` isn't `localhost:5433/dhashu_local`.

**Never** put production, staging or real provider credentials in `.env.local`, and never commit it or paste it anywhere.

## 5. Initialise and seed

```powershell
.\dev-local.ps1 check     # prints host/port/dbname: must be localhost 5433 dhashu_local
.\dev-local.ps1 init      # app schema + admin schema (idempotent)
.\dev-local.ps1 seed      # 100 synthetic users (u_0001 ...), fake data only
```

## 6. Start everything (one PowerShell window each)

| Part | Command | URL |
|---|---|---|
| Backend | `.\dev-local.ps1 web` | http://127.0.0.1:5000/pool |
| BGV worker | `.\dev-local.ps1 worker` | (no port; idles, no provider calls) |
| Admin dashboard | `.\dev-local.ps1 admin` | http://127.0.0.1:5001 |
| Mobile preview | `.\dev-local.ps1 mobile` | http://127.0.0.1:5173 |
| Mobile + local backend | `cd mobile; npm run dev:local` | http://127.0.0.1:5173/pool |

Run only one Vite server on 5173 at a time. Run `cd mobile; npm install` once before the first mobile start.

### How to log in

- **Backend (web):** open `/pool` and click any synthetic user. There's no SMS, because `dev-local.ps1` sets `AUTH_ENABLED=0` (sec-login: real sign-in is on whenever `AUTH_ENABLED` is unset, and `0` is accepted only with `DHASHU_LOCAL_HARNESS=1`).
- **Mobile preview (`npm run dev`):** in-browser mock data. Use any phone number and code `123456`.
- **Mobile + local backend (`npm run dev:local`):** open http://127.0.0.1:5173/pool and pick a user; you land in the app.
- **Admin dashboard:** create an administrator once (step 7). Then sign in with email + password + the 6-digit code from your authenticator.

## 7. Create a local admin (password + authenticator)

```powershell
.\dev-local.ps1 admin-create -Email you@local.test
```

1. Type a password of at least 14 characters twice; the input is hidden.
2. The command prints a **setup key**. Add it to your authenticator app as a time-based account with 6 digits and a 30-second period.
3. Enter the current code when prompted.
4. Sign in at http://127.0.0.1:5001 with the **next** code.

**Optional QR code:**

```powershell
.venv\Scripts\python.exe -m pip install qrcode   # .venv only, never requirements.txt
```

Then, in a **second** window, while `admin-create` waits for the code, run the command below. It asks for the email and the setup key, the key input is hidden, and it draws a QR code in the terminal:

```powershell
.venv\Scripts\python.exe -c "import getpass,qrcode,urllib.parse as u; e=input('Admin email: ').strip(); k=getpass.getpass('Setup key (hidden): ').strip().replace(' ',''); q=qrcode.QRCode(); q.add_data('otpauth://totp/DhaShu%20Admin:'+u.quote(e)+'?secret='+k+'&issuer=DhaShu%20Admin&digits=6&period=30'); q.print_ascii(invert=True)"
```

The setup key is private. Don't screenshot it, paste it into chat, or commit it.

If you lose the password or authenticator: `.\dev-local.ps1 admin-reset -Email you@local.test`. It replaces both, revokes that admin's sessions, and shows a new setup key.

## 8. Tests

```powershell
.\dev-local.ps1 test          # full Python suite (about 15-20 min)
.\dev-local.ps1 mobile-test   # mobile unit tests (node:test)
```

- **What the Python run does:** `dev-local.ps1 test` removes `DATABASE_URL` and the local switches from the test process, so tests never touch `dhashu_local`. Postgres tests go to `dhashu_test`.
- **Known failures:** master currently has **21 known failing Python tests** (test/code drift, unrelated to the local setup). A change is fine when the failure list stays exactly those 21.
- **Not part of this flow:** Playwright e2e (`mobile/e2e`) needs a separate browser download.

## 9. Android emulator (debug build, local backend)

1. Start the backend: `.\dev-local.ps1 web`. With `DHASHU_LOCAL_HARNESS=1` in `.env.local`, the log shows `LOCAL HARNESS ACTIVE`.
2. Start your emulator (for example Pixel_7), then build and install the debug app:
   ```powershell
   cd mobile
   npm run sync:emulator                     # vite build --mode emulator (http://10.0.2.2:5000) + cap sync
   cd android
   $env:JAVA_HOME = [Environment]::GetEnvironmentVariable('JAVA_HOME','User')
   .\gradlew.bat --no-daemon installDebug
   ```
3. Open **DhaShu** on the emulator. The sign-in screen shows **Pick a local user**; tap one to reach the home screen. A `LOCAL · 10.0.2.2:5000` badge marks the dev build.

Notes:
- **Local only.** Plain http works only in **debug** builds and only to `10.0.2.2`, `localhost` and `127.0.0.1`. Release builds are https-only, and their bundle contains no picker code.
- **When the picker returns 404.** The local harness (`local_harness.py`) works only when `DHASHU_LOCAL_HARNESS=1` is set, `AUTH_ENABLED=0`, no production setting is present, and the request comes from this machine. Otherwise every `/api/v1/dev/*` call is 404, and the backend refuses to start if the flag is combined with a production setting. It lists and signs in only seeded users (`u_*`, `test_*`).
- **Line endings.** `npx cap sync` may rewrite line endings in `mobile/android/app/capacitor.build.gradle` and `mobile/android/capacitor.settings.gradle`. If `git diff` shows no content change, run `git restore` on both.
- **Black screenshots.** If `adb screencap` returns black (host-GPU emulator), use `adb emu screenrecord screenshot <folder>`.
- **Password screens.** The Settings → password screens return 503 against the local backend, because local sign-in is off. This is expected.

## 10. Never

- Never deploy or run `railway` commands from a local setup.
- Never use production or staging URLs, variables or databases.
- Never build or upload release/store builds, or trigger Codemagic, from a laptop. A plain `npm run build` deliberately fails without a release `VITE_API_BASE_URL`.
- Never commit `.env.local`, `.venv/`, `dev-reports/` or IDE folders. Add them to `.git/info/exclude`.
