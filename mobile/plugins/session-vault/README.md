# session-vault

Local Capacitor plugin (not published — referenced from `mobile/package.json`
as `"session-vault": "file:./plugins/session-vault"`) that provides the iOS
implementation of the `SessionVault` plugin.

## Why this exists as a package, not loose files

Copying `SessionVaultPlugin.swift`/`.m` into `ios/App/App/` after `cap add ios`
never worked: nothing in the generated Xcode project referenced those files, so
they sat there uncompiled and `registerPlugin('SessionVault')` found nothing at
runtime. A real local Capacitor plugin package fixes this — `npm install`
links it into `node_modules/session-vault`, and `npx cap sync ios` picks it up
automatically (via `package.json`'s `capacitor` field and this package's
`Package.swift`, Capacitor 8's SPM integration) and adds it as a proper build
dependency of the app target. No manual copy step needed.

## Layout

- `package.json` — declares this as a Capacitor plugin (`capacitor.ios.src`).
- `Package.swift` — the SPM manifest `cap sync ios` resolves.
- `ios/Sources/SessionVaultPlugin/` — the actual implementation:
  `SessionVaultPlugin.swift` (Keychain-backed logic) and `SessionVaultPlugin.m`
  (`CAP_PLUGIN` registration — the plugin name string must stay exactly
  `"SessionVault"`).
- `index.js` / `index.d.ts` — a thin JS/TS shim so this behaves like a normal
  plugin package if something ever imports it directly. Not currently used:
  `src/main.js` already calls `registerPlugin('SessionVault')` straight from
  `@capacitor/core`, which still works unchanged once the native side is
  properly linked.

## Android

Deliberately **not** part of this package. `android/app/src/main/java/com/
dhashu/app/SessionVault.java` stays exactly where it is, registered directly
in `MainActivity.java` (`registerPlugin(SessionVault.class)`) — untouched by
this restructuring, and unaffected since this package's `capacitor` field
declares no `android.src`.

## Contract

Mirrors the Android implementation exactly in observable behaviour:

| Method  | Call                 | Resolves                                | Rejects with |
|---------|----------------------|-------------------------------------------|--------------|
| `write` | `{ value: string }`  | *(nothing)*                                | `"Invalid credential."` if not 32-128 chars; `"Secure storage unavailable."` on any storage failure |
| `read`  | *(nothing)*          | `{ value: string \| null }`                | `"Stored session is unavailable. Sign in again."` if the entry can't be read back (also clears it) |
| `clear` | *(nothing)*          | *(nothing)*                                | `"Could not clear secure storage."` if the delete itself fails |
