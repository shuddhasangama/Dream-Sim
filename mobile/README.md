# DhaShu mobile (Capacitor + Vite)

## Which server does the app talk to?

One module decides: `src/apiConfig.js`. It is used by `vite.config.js`
(build time) and `src/main.js` (run time). There is no server address
anywhere else in the app.

| Mode | Command | Server | Badge |
|---|---|---|---|
| Browser preview (default) | `npm run dev` | none: in-browser mock data (`src/preview.js`), any phone, code `123456` | `PREVIEW` |
| Browser + local backend | `npm run dev:local` | local Flask at `http://127.0.0.1:5000`, through the Vite proxy | `LOCAL · backend 127.0.0.1:5000` |
| Android emulator dev build | `npm run sync:emulator`, then run from Android Studio | `http://10.0.2.2:5000` (your laptop as the emulator sees it) | `LOCAL · 10.0.2.2:5000` |
| Release (Play / App Store) | `npm run build` | `VITE_API_BASE_URL`, set in `../codemagic.yaml` | none |

All dev URLs open at http://127.0.0.1:5173.

### Browser + local backend

1. Start the backend on port 5000 with secure sign-in off (`AUTH_ENABLED` unset).
2. Run `npm run dev:local`.
3. Open http://127.0.0.1:5173/pool and pick a user.
4. You land back in the app, signed in.

The dev server forwards `/api`, `/pool`, `/login`, `/logout` and `/static` to
`127.0.0.1:5000`, so requests are same-origin. The backend's session cookie
works with no CORS change, and no tokens are created or stored. Sign out uses
the backend's `/logout`.

### Android emulator

`npm run sync:emulator` builds with `--mode emulator`, which uses
`http://10.0.2.2:5000`, and syncs it into `android/`. Then open Android
Studio (`npm run android`) and run the **debug** variant.

- Plain http is allowed only in debug builds, and only to `10.0.2.2`,
  `localhost` and `127.0.0.1`. See
  `android/app/src/debug/res/xml/network_security_config.xml`.
- Release builds keep `usesCleartextTraffic="false"` and are https-only.
- An emulator build can only point at those three hosts. It can never point
  at a real server.
- **Signing in:** the emulator build's sign-in screen shows **Pick a local
  user**. It lists the seeded users and signs you in as the one you tap.
  - This needs the backend running locally with `DHASHU_LOCAL_HARNESS=1`
    (backend `local_harness.py`).
  - The backend issues the same access and refresh tokens as the real login.
  - The picker exists only in `emulator` builds. Release bundles contain no
    trace of it, which `tests/devLogin.test.js` checks.
  - The backend side works only with secure sign-in off, with no production
    settings present, and only for requests from this laptop. Otherwise it
    returns 404.

  Quick start, from the repo root:

  ```powershell
  .\dev-local.ps1 web    # backend with DHASHU_LOCAL_HARNESS=1 from .env.local
  ```

  Then, in `mobile\`, run `npm run sync:emulator` and
  `cd android; .\gradlew.bat installDebug` with Java 21. Open DhaShu in the
  emulator and pick a user.

### Release builds

`npm run build` (Vite `production` mode) **fails** unless `VITE_API_BASE_URL`
is an `https://` origin with a public host. These are refused:

- missing
- plain http
- `localhost`
- `10.0.2.2`
- private or link-local addresses
- any path, query or credentials

Codemagic sets the value in each workflow's `vars` in `codemagic.yaml`, so
store builds behave exactly as before. A local `npm run sync` fails for the
same reason unless you set the variable on purpose. Use `sync:emulator` for
local native work.

Settings and examples: `.env.example` (no secrets).

## Tests

`npm test` runs the unit tests (node:test). Playwright end-to-end specs are in `e2e/`.
