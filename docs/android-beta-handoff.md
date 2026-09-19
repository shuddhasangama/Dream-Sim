# Android beta handoff — 2026-09-19

## Ready now
- Workflow: `android-beta` / **DhaShu Android APK Beta** in root codemagic.yaml.
- Existing iOS workflow retained. Same package `com.dhashu.app` and Railway API.
- Node 22, Java 21, existing Gradle wrapper and SDK 36 project.
- Builds production web assets, syncs the existing Android project (including SessionVault), generates icons, produces `app-debug.apk`.
- Build number uses Codemagic PROJECT_BUILD_NUMBER. No provider credentials belong in the APK.
- Fixed client path validation for backend colon/pipe IDs, including encoded IDs, with regression coverage against traversal/external URLs.

## Run in Codemagic
1. Push this change to the branch selected for the build.
2. Dream-Sim > Start new build > select that branch and **DhaShu Android APK Beta**.
3. Start build. Download `app-debug.apk` under Artifacts once successful.
4. Transfer APK to Android phone, open it, allow installation from that source if prompted, and install.
5. Validate approved tester SMS login, correct profile, restart/session recovery, logout, and journey navigation.

This first beta is debug-signed for direct installation, not a Google Play release.
Different build machines can generate different debug signing keys: switching from the local APK to a Codemagic APK (or between fresh CI machines) may require uninstalling first. This removes local app/session data; server profiles remain on Railway. Stable release signing is the next step before ongoing distribution.

## Validation performed
- 29 mobile unit tests passed.
- Production Vite build and Capacitor Android sync passed.
- Android assets generated from existing mobile/assets artwork.
- Local Java 21 / Gradle 8.14.3 / SDK 36 `assembleDebug -PbuildNumber=23` passed.
- Android apksigner verification passed.
- Local APK: C:/Users/Dharesh/Downloads/DhaShu-Android-beta-23.apk.
- No device walkthrough or Codemagic cloud run performed yet.
- Current mobile sign-in UI is SMS-only; SendGrid backend setup does not itself add an email sign-in option to this UI.
- No Railway deployment/database changes or live OTP requests were made.
