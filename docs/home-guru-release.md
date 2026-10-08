# Home and Guru stage guidance

Home now uses saved match, availability, agreement and Debrief state. Guru shows two or three relevant topics with short, clickable explanations. Vision/Stats/Chemistry scores are removed; Vision shows its saved template name. Private Debrief answers are not shared.

In asynchronous testing, both completed agreements move the pair straight to their simulated date. Each partner selects Finish simulated date before Debrief opens. Existing agreements and progress are preserved; real-time dating is unchanged.

## Deploy

From PowerShell in the repository root:

```powershell
git add app.py async_rehearsal.py guru.py journey_api.py mobile/src/screens/guru.js mobile/src/screens/home.js mobile/e2e/foundation.spec.js mobile/tests/guruStages.test.js test_async_rehearsal.py test_guru.py test_segment_efg_routes.py test_guidance_topics.py docs/home-guru-release.md
git diff --cached --stat
git commit -m "Simplify Home status and stage-specific Guru guidance"
git push origin master
```

1. Wait for Railway to finish deploying this commit. No new variables, migrations or user resets.
2. Build this same commit in Codemagic using android-play and ios-testflight.
3. Distribute the Android bundle through Play internal testing and the iOS build through TestFlight. Testers must update the installed app to see the new UI.

## Acceptance checks

- No match: waiting status; an available match: its slot number and Like/Pass guidance.
- Saved availability with partner pending: waiting status, not another Confirm Date task.
- Shared slots: confirm a time. Own agreement complete: waiting for partner.
- Both agreements complete: simulated date opens without an extra date-readiness click.
- Finish simulated date on both phones: Debrief opens; own submitted Debrief waits for partner.
- Repeat date: planning/previous-date topics, not new-match prompts.
- Guru navigation respects existing consent and stage eligibility. A home invitation or social request remains an independent consent flow.
