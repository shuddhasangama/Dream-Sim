# Verification progress UI — 5 November 2026

DigiLocker is first, with concise Aadhaar-required / PAN-optional copy and an explicit sharing consent. A received session becomes a summary rather than another creation form. Existing consent text, external OTP completion, cooldowns and paid-retrieval protection remain in force.

The checklist follows with source-specific outcomes, pending/processing indicators and separate employment-history, exact court and FIR results. Aadhaar DOB is identified as the source of verified age; a declared-age mismatch stays visible for resolution, rather than silently overwriting the profile. Name is hidden from the summary and available to the owner in collapsed document details. Existing match-stage name reveal rules remain unchanged.

Live face verification and avatar setup are collapsible sections within Verification. The existing hosted Signzy capture/return workflow is reused. Its captured selfie can be reviewed and consented for the existing selfie-only two-option OpenAI flow. Generation consent is separate from capture consent. An accepted avatar has no selection/generation buttons; queued/submitting generations expose no capture, consent or repeat-generation action. The one-run limit remains server-owned.

Status reads use the existing 15-second foreground loop during signup as well as the Verification screen. They never submit provider requests or repeat a generation. Earlier signup steps do not poll or rerender. Unsaved verification forms, selected consent and staged selfies pause automatic replacement. Expanded sections survive updates. Manual status reads preserve staged selfies. A single Check for updates action replaces per-section refresh controls when no active job is running. A provider-confirmed pending Court/FIR result can still expose its existing cooled-down Retrieve result action: GET status polling alone must not pretend to fetch new provider evidence. Existing server cooldowns and explicit result retrieval are preserved.

Avatar endpoint failure does not hide unrelated verification status. Signup status-read errors show a reconnect message. Other provider operations, overall account admission, and matching rules are unchanged. Native camera/Signzy/OpenAI flow still needs device acceptance testing with the consolidated release; screenshots use local synthetic fixtures, not live identity records or production outcomes.

Stats redesign remains at preview stage and is not included by these Verification changes. No deployment or additional native build was started.
