# Debrief and Guru deployment

## What changed

- Home already makes Date Debrief the primary action when feedback opens. Existing regression coverage checks this; no timer reset is needed.
- At least two distinct green flags; zero, one or two red flags. Custom labels are limited to 16 characters on both client and server. The green payload has a defensive 20-item ceiling. Existing longer preset labels remain valid.
- Guru private conversation: last 50 exchanges, current-stage topics, saved private memories (opt-in; up to 10 notes, 240 characters each), editing and deletion.
- Relationship topics: air/resolve differences, mediate, expenses and romance. Dating topics remain stage-specific.
- Shared conversation: invite → other partner joins → independently share perspectives → propose next step → both confirm the SAME revision. An edit clears confirmations. Pause requires both to resume. Leave removes shared content for both.
- Shared discussion does NOT perform payment, date confirmation, relationship progression or contact-sharing consent. Existing app actions still govern those.
- Shared mediation is structured and asynchronous, not a live counsellor or AI-generated judgement. It presents each person's own perspective alongside the other's. Private history/memory never enters this shared space.
- Optional OpenAI narration is implemented for PRIVATE chat only. It is off by default and additionally needs each user's explicit opt-in. Without it, Guru uses guided prompts. A provider failure falls back to guided prompts and labels the reply accordingly.

## 1. Review and push source from Windows PowerShell

Run from `C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2`:

```powershell
git status --short
git diff --stat
python -m pytest test_guru.py test_guru_navigator.py test_guru_provider.py test_guru_dating.py test_date_cycle_api.py test_api_only_journey.py test_async_rehearsal.py test_schema_postgres.py -q
Push-Location mobile
npm.cmd test
npm.cmd run build
Pop-Location
git add drift-check.sql docs/openapi-phase4.json api.py app.py db.py schema.sql schema_postgres.sql guru_dating.py date_cycle_service.py guru_navigator.py guru_provider.py templates/week.html mobile/src/screens/debrief.js mobile/src/screens/guru.js mobile/src/screens/guruNavigator.js mobile/src/style.css mobile/src/preview.js mobile/tests/stage3.test.js mobile/e2e/guru-navigator.spec.js test_guru_dating.py test_date_cycle_api.py test_guru_navigator.py test_guru_provider.py docs/guru-navigator-release.md
git diff --cached --stat
git commit -m "Add private Guru guidance, shared conversations and short Debrief flags"
git push origin master
```

This explicit file list excludes existing untracked root npm files and Android IDE settings. Review any additional changes before staging them.

## 2. Configure Railway's Dream-Sim service

Generate a dedicated encryption key ONCE on your own computer:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy its output into Railway Variables; keep a secure backup. Do not commit it or replace it on each deployment. Losing/changing it makes previous Guru content unreadable. It is separate from the identity capture key.

| Variable | Value |
|---|---|
| `DHASHU_GURU_ENABLED` | `1` |
| `DHASHU_GURU_ENCRYPTION_KEY` | Generated key above |
| `DHASHU_GURU_AI_ENABLED` | `0` initially |

Deploy the pushed commit and variable changes. App database initialization creates `GuruPrivate` and `GuruDiscussion` in both supported database types. No manual SQL, profile reset, fixed-pair changes or simulation-clock changes are required.

Private/shared content is encrypted at application level before database storage. Access is checked on every request. Reassigning a tester profile's phone/email prevents access to previous Guru history and shared conversations. Releasing a pair/exiting a relationship blocks access to its shared discussions.

## 3. Build BOTH mobile apps in Codemagic

These include native app JavaScript/UI changes, so a Railway deployment alone will not show the new controls on installed phones.

1. Build `android-play` from the pushed `master` commit; upload its AAB to Play internal testing as usual.
2. Build `ios-testflight` from the same commit; distribute the resulting TestFlight build as usual.
3. Testers install the update. Existing workflows already build and sync platform assets; no manual Android/iOS project editing is needed.

Old builds retain existing behavior. Guru disabled/unconfigured does not remove the existing short guidance cards.

## 4. Optional live AI (after guided-flow testing)

Add to Railway, then redeploy:

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | Your server-side OpenAI project key |
| `DHASHU_GURU_MODEL` | A Responses-compatible model enabled for that project |
| `DHASHU_GURU_AI_ENABLED` | `1` |

Keep keys out of Codemagic/frontend variables. In Guru, users must then enable **Optional AI responses → Allow OpenAI-assisted replies**. Their current message, last 10 exchanges, explicitly saved memories and current stage/Home status can be sent. No automatic partner-private feedback, health profile, ethnicity, face image, signature or contact details are fetched for this purpose. Users can still type sensitive details themselves; explain the provider disclosure in your app privacy notice before enabling this feature.

The adapter has no tool access and cannot mutate the journey. Status questions use the current deterministic Home status directly. Requests have a 12-second timeout and no automatic provider retry; private messages are limited to 10/minute and 100/day per account. Set project spending limits separately. No live provider request was made during implementation; test the selected model with synthetic data before enabling it for testers.

The API uses `store: false`; this does **not** mean zero provider retention. OpenAI's documented abuse-monitoring retention still applies unless your organization has appropriate approved controls: [data controls](https://developers.openai.com/api/docs/guides/your-data). Request shape follows the [Responses guide](https://developers.openai.com/api/docs/guides/migrate-to-responses).

## Acceptance test with two existing tester accounts

1. Confirm Home offers Debrief once the simulated date finishes for both participants.
2. One green flag cannot save; three can. Add a custom flag of 16 characters. A third red cannot be selected.
3. Open Guru on phone A; send a private thought, reload, and verify history. Phone B must not see it.
4. Enable memory, add/edit/delete a note; switch memory off and confirm memories are removed. Deleting history is separate.
5. Invite B into an available shared topic. Until B joins, A cannot share a perspective.
6. Both share, possibly hours apart. Review both perspectives, propose a next step; A's confirmation alone leaves it pending.
7. Edit the proposal on B. Previous confirmations clear. Both confirm the latest proposal to show agreed.
8. Pause on either phone. Both must resume. Leaving removes shared content; private notes remain separate.
9. With a provider configured, explicitly enable AI for one user; verify AI replies, then disable it and verify guided replies.

Refresh conversations or reopen Guru to fetch partner updates; push notifications and background delivery are not part of this change.

## Privacy and operational limits

- Private deletion affects live app storage; database backups follow your configured Railway retention and access controls. Shared content may already have been read/screenshotted by the other person. No claim of end-to-end encryption is made.
- Retain the encryption key separately from database backups and control operator access. Existing operator/database backups are not automatically purged by an in-app delete.
- Per-pair conversation creation is capped at 100; one open discussion at a time. History is bounded; user-saved memories remain until edited/deleted/disabled. Closed discussion metadata remains but its shared text is removed.
- Rule-based safety language is a fallback, not a comprehensive risk detector. Optional AI still needs quality/safety evaluation with synthetic cases before broad rollout.
- Turn `DHASHU_GURU_AI_ENABLED=0` to stop model requests. Turn `DHASHU_GURU_ENABLED=0` to hide all new Guru conversation controls while retaining existing guidance. Keep the encryption key and tables for later re-enablement.

## Verification performed

- Full backend regression run: 1,494 passed and 30 skipped; two generated/schema-documentation checks initially failed. After updating drift-check.sql and OpenAPI, all 19 affected checks passed.
- Final Guru/privacy/provider tests: 32 passed; provider requests were mocked.
- Mobile unit tests: 94 passed; production web build passed.
- Browser regression: 22 of 23 passed initially; the local-preview missing Guru endpoint was fixed and the failed test passed on rerun. Both new Debrief/Guru browser tests also passed after the final UI changes.
- No Railway database, App Store/TestFlight build, Google Play release or live AI provider was changed or called. Live PostgreSQL/provider and physical-device acceptance remain deployment checks.
