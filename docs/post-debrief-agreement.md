# Post-debrief next-step agreement

Mixed Relationship / Another date choices now wait for explicit acceptance by the person who requested Relationship. The other person already requested another date; either may end the pairing. Discuss with Guru records discussion intent only. Original decisions remain unchanged. Acceptance completes the old date and opens fresh planning; it does not confirm a booking or charge a payment. Both Relationship still opens the stage gate.

Home, Week and Guru show the actor-specific pending step. Async simulation stays at the date Debrief checkpoint, with no timeout resolution for mixed choices. Shared Guru discussions use the existing opt-in invitation flow; even a mutually confirmed conversation does not replace the explicit date decision.

Sharing flags is optional, unchecked by default. Only explicitly shared green/red flags enter partner guidance; private notes/pass reasons remain private. Existing feedback has no sharing consent and stays private.

## Deploy

Commit the tracked changes plus the new test files and this document, then push master. Wait for Railway to deploy that commit. Build the Android Play Bundle and iOS TestFlight workflows in Codemagic from the same commit and install both updates. Codemagic already builds the web assets and syncs each native platform. No schema migration or new environment variable is required. Existing shared Guru conversations require DHASHU_GURU_ENABLED=1 and the existing DHASHU_GURU_ENCRYPTION_KEY; do not rotate it. Basic choice guidance works without enabling the conversation service.

Do not change the simulation start week. Already-resolved historical mixed outcomes are not rewound: reset the synthetic pair through the reviewed reset procedure if you need to rerun that scenario. Old installed apps do not display the new decision controls, so update both testers before testing mixed outcomes.

## Acceptance checks

- Both Another date: fresh planning, old date completed.
- Both Relationship: gate opens; no immediate stage change.
- Mixed in either order: no receipt, new plan, payment or week advance.
- Discussion, logout and delayed response: choices remain saved.
- Relationship requester accepts: exactly one cycle advance; duplicate requests do not count twice.
- Either ends: pair releases; old original choices retained.
- Unrelated users cannot read/respond; private feedback is not shared by default.
- Shared Guru confirmation alone does not create a date.
