# Avatar capture correction — 4 November 2026

The old private-identity capture was removed at the tester's request. The app avatar and Face Match stores were already not started, with no uploaded avatar selfie/options/selection; their paid allowances were not reset or consumed. The DigiLocker Aadhaar portrait remains available for comparison.

Client correction:

- `.profile-portrait` set display:block, overriding the hidden attribute and showing an empty preview before capture. The hidden preview now has an explicit scoped display:none rule.
- Camera selection now runs inside the shell's busy action. App-resume polling/navigation cannot redraw the screen while the native picker is open.
- The returned photo is staged in screen memory and rendered after the busy redraw, rather than attached to a potentially disconnected DOM element. Unsaved staged selfies suppress background clock refresh until submitted or navigation discards them. Photos are not written to a local persistent cache.
- Added a Photos picker for a recent selfie, using the existing Capacitor Camera plugin. Permission/cancellation/invalid-photo messages are specific and keep retry controls usable. No image is uploaded until explicit generation consent/submission.

Regression coverage simulates the same full redraw during the async picker, checks hidden preview, verifies no upload without consent, tests Photos source, cancellation and denied permission. Real iPhone permission/camera acceptance remains a device check; the fallback allows continued testing if native capture is unavailable. No backend configuration, new plugin or paid-generation rule changes are required.


Follow-up correction: live POST /profile/avatar/selfie returned PostgreSQL ProgrammingError because db.insert_row committed inside an explicit auth_sessions.transaction. Transaction scopes now defer legacy helper commits on both database engines. Real PostgreSQL regression exercises capture/queue/generate/accept, rollback, FaceMatchJob and FaceImageLease insertion; no vendor calls are made. This fix is deployed to API and worker independently of the app update.

The next client revision removes Photos selection; generation is revealed only after capture and consent. Consent details and face verification are collapsed. Status refresh preserves staged capture/consent, reports completion or failure inline, and avatar status is independent of non-auth face-status errors. Submission failures preserve the selfie when the server confirms an unreserved draft; uncertain results are reconciled by reading server state without mutation replay.
