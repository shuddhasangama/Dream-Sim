# Visual app release — 23 November 2026

Prepared in `C:\DreamContractLocalBKP\ChatGPT\dhashu-discovery-release` on `codex/combined-discovery-release`. These changes are local, not committed or deployed yet.

## What this release contains

| Screen | Implemented |
|---|---|
| Shared appearance | Warm white #FCFBF9, charcoal #25211F, terracotta #9E4F35 and soft clay #F3DFD5; locally bundled DM Sans and Newsreader with font licences; consistent controls and focus states |
| Signup progress | Charcoal header, connected numbered steps, completed-step checkmarks; sticky opaque brand header with safe-area spacing |
| Vision | Icon-and-label plan rows, visible selected marker, explicit pillar controls, mandatory Emotional and optional Physical; Cohabitate sub-details remain hidden |
| Stats | Clay section heading; Age/Gender/City basics; one Save and continue action, advancing only after server confirmation |
| Date preferences | Collapsed immediately after Basics; selected neighbourhood chips; expandable diet/budget/cuisine; Set up later collapses without clearing answers |
| Chemistry | Terracotta heading; one expanded clay activity panel at the top; labelled answers and selected checkmarks; collapsed answers retained; independent partner preference; existing 28-activity catalogue |
| REACH | Charcoal status/count header; different copy for incomplete setup, unfinished verification and zero matches; secondary preference disclosures; existing field validation retained |

The later product decisions override the PDF examples: no Name/DOB entry, 28 curated activities rather than 12, explicit pillars and Emotional required. Date preferences remain within Stats, after Basics, rather than a separate route. Verification, payment and matching rules are unchanged. No user reset or new Railway variable is required for these visuals.

## Validation

- 140 mobile tests passed.
- Production Vite build passed.
- Browser acceptance passed: select Vision, save age-only Stats and advance, defer date preferences without losing selections, choose and save independent Chemistry answers.
- Chemistry checked at 320/390/430px; five representative screens rendered without horizontal overflow at 390px and visually inspected.
- Browser tests use synthetic data and mocked APIs. Real-device iOS/Android checks remain after installing the new builds. No live OTP, payment or verification calls were made.

Preview screenshots are in `data/visual-review/` (local, excluded from Git): vision.png, stats.png, date-preferences.png, chemistry.png. REACH preview is `data/preview-reach.png`.

## Deploy — local PowerShell

```powershell
cd C:\DreamContractLocalBKP\ChatGPT\dhashu-discovery-release
git status --short
git diff --check
git add mobile/index.html mobile/src/main.js mobile/src/brand-review.css mobile/src/signup.js mobile/src/signupStats.js mobile/src/signupVision.js mobile/src/screens/chemistry.js mobile/src/screens/reach.js mobile/public/fonts/dmsans-variable.ttf mobile/public/fonts/dmsans-OFL.txt mobile/public/fonts/newsreader-variable.ttf mobile/public/fonts/newsreader-OFL.txt mobile/e2e/visual-review.mjs docs/visual-app-release.md
git commit -m "Apply Brand Meadows visual design to mobile signup and REACH"
git fetch origin
git merge origin/master
git push origin HEAD:master
git rev-parse --short HEAD
```

If a merge reports conflicts, resolve them before pushing. Never force-push. The new commit will differ from the previous 451efb5c.

## Build and install

1. Start the existing Android and iOS Codemagic workflows on master. Confirm both use the NEW commit from the command above.
2. Let the builds publish to the existing testing tracks/TestFlight. Install those new build numbers on your phone.
3. Railway may automatically redeploy after the push. This release needs no migration, new service, secret or variable changes.
4. Do not change DHASHU_DAILY_DISCOVERY merely to activate the visuals: the styling works with either value. Do not delete users.
5. In the updated app check the charcoal step header, terracotta Vision button, clay selected plan and Stats heading. Check typing/keyboard scrolling, date preference folding, Chemistry saving and REACH on both platforms.
6. Keep public-store release separate from testing-track delivery. If a visual regression appears, revert this release commit and rebuild the app; no database rollback is needed.
