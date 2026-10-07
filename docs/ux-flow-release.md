# Clear next steps and simpler dating screens

## What changed

| Requested items | Result |
| --- | --- |
| 1–2, 5–7 | One “Save answer” label; unnumbered topic/answer/reflection sections; chosen-by-you/partner/both labels; adjacent answers. Each person explicitly chooses whether to share an answer. Existing answers remain private. A shared answer appears after both have answered. |
| 3–4, 8 | A next-step summary identifies your outstanding action or the partner wait. The same agreement screen supports later stage checkpoints. Optional after-date conversations also show adjacent answers. |
| 9 | Date preferences are collected after mutual Like, before selecting the shared time: diet, budget and cuisine. Greeting boundaries follow date selection. Contact sharing and home invitations remain separate, optional consent flows. |
| 10 | Current Vision choices are read-only after signup. Add detail and Declare a change remain the editing routes, with existing time/disclosure rules. Signup still offers the templates and custom choices. |
| 11, 17 | Compact Fri/Sat/Sun × meal grid. The pre-match availability form has been removed from the rehearsal banner. Slots become available after pairing. |
| 12–14, 23 | Short Home and Week next actions, no misleading schedule time on Home's action. Decision explanations use bullets with bold keywords. Guru does not repeat the opening answer when a topic is selected. |
| 15–16 | No Rank event; Like/Pass labels. Completion ticks use saved decisions, availability/alignment, signatures and Debrief decisions. A date isn't marked completed merely because its time passed or a no-show was reported. |
| 18–20 | Removed the date selections/dress-note form. Agreements show adjacent Visions and their template labels. Signed playbooks can be reopened; the API uses the frozen terms recorded for the signature. |
| 21 | Short face-photo instructions with full storage/BGV disclosure in an expandable section. Capture-only beta approval remains explicitly labelled as testing, not authenticated identity. |
| 22 | Home uses the saved date's actual Debrief opening time, even before a DateOutcome exists. Polling checks progress every 15 seconds while visible and on app resume; unsaved forms are preserved. |
| 24–25 | Guru supplies first/repeat-date preparation, the user's own previous Debrief and four Chemistry activity groupings. It uses rule-based guidance, not a new AI provider. Phone, WhatsApp, LinkedIn, Instagram, Facebook and Snapchat remain opt-in contact requests with the existing agreement gates. |
| 26–27 | Repeat dates hide new-match/RC schedule entries. Home offers Confirm Date when planning is available, despite a previous date's historical milestones. |

An unperformed activity does not receive a green tick just because Monday or Tuesday has passed. Partner absence continues to preserve the other person's progress.

## Deployment sequence

This release changes the bundled mobile UI: **Railway plus new Android and iOS builds are required**. Railway alone will not replace screens in already-installed native apps.

1. In Windows PowerShell, from the repository root, review and commit:

   ```powershell
   cd C:\DreamContractLocalBKP\ChatGPT\dhashu-phase2
   git diff --check
   git status --short
   git add -u
   git add dating_guidance.py mobile/src/screens/slotPicker.js docs/ux-flow-release.md
   git diff --cached --stat
   git commit -m "Simplify dating UX and clarify shared journey progression"
   git push origin master
   ```

   `git add -u` stages tracked edits. Review them before committing. Leave the unrelated untracked root package files, root node_modules and Android .idea folder out of this commit.

2. In Railway, wait for the **Dream-Sim** service deployment of that commit to succeed. If automatic deploy is disabled, deploy the latest commit manually. **No new environment variables, profile resets or week changes are needed.** Keep the existing simulation, tester-entry and identity-capture settings.

   Database initialization adds `GateAsk.also_asked_by` and `GateResponse.share_with_partner` (default private), and widens the contact-channel constraint. Existing requests and answers are retained. No manual data-clearing script is needed.

3. In Codemagic, build the same commit on `master` using:
   - `android-play` → publish the new bundle to your Google Play testing track.
   - `ios-testflight` → distribute the new build to the TestFlight group.

   Both workflows already build and sync the mobile bundle. A separate local `cap sync` is not needed for those cloud builds. Use a new version code/build number as required by each store.

4. Install the update on each tester's phone, then refresh progress. Existing saved journeys should remain intact.

## Device acceptance check

- Before mutual Like: no availability picker. After both Likes: select and save slots in the grid.
- Confirm a shared slot, sign, capture the face photo, then revisit the signed playbook.
- At the saved date's Debrief opening: Home shows Debrief within a refresh/poll. Save feedback on each account separately.
- Choose another date on both accounts: Home offers planning; Week hides Match 1/2/3.
- Relationship conversation: choose a common topic; confirm “Chosen by both”; answer separately. With sharing off, only a private-answer status appears for the partner; with explicit sharing on and both answered, responses appear adjacent.
- Check the user's own previous Debrief and Chemistry prompts in Guru. Declining a social request must never reveal the handle.

Local tests use isolated SQLite and browser fixtures. Railway PostgreSQL, store distribution and physical iPhone/Android camera behaviour still require this deployment smoke test; no production data was changed during implementation.

## Validation completed

- Backend: 1,461 passed, 30 skipped; 765 subtests passed.
- Mobile unit tests: 91 passed.
- Browser flow tests: 43 passed. The final conversation/banner edits also passed a focused 8-test rerun.
- Production mobile web bundle built successfully; Git whitespace check passed.
- Visually inspected the adjacent-answer and compact-calendar layouts. Browser coverage includes 320, 375, 414 and 430 pixel widths and enlarged text/layout interaction.
