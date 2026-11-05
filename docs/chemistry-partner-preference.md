# Chemistry additions — 5 November 2026

Every activity retains one own answer (good, improve, maybe, no) and gains an independent opt-in “Partner preference doesn’t matter” checkbox. This is not a fifth own-answer bucket. A person can enjoy marathon running without requiring their partner to participate. A partner's own “no” remains a no; Guru's existing respect-a-no rule is unchanged. Chemistry is not currently a hard matching eligibility filter.

Up to four custom activities can be added, answered, removed and saved. Names are 1–60 characters, distinct after case/Unicode/whitespace normalization, and cannot duplicate the standard list. Custom activities count toward the existing four-answered-activities minimum. All four own-answer buckets apply. Arts/Sports/Talents categories remain deferred.

The protected actor-scoped Chemistry API accepts `custom_activities` and `partner_any` alongside `activities`. Validation rejects excess/duplicate names, invalid buckets and partner flags without an own answer. User.skills_json stores these fields and the existing by_bucket index; no schema migration or vendor call is needed. Older requests remain supported. Independent GET readback confirms all three saved fields. Match Chemistry comparisons disclose which partner answers are immaterial; those flags do not count as shared interests or willingness to join an activity.

Signup draft handling clears positional input snapshots after Chemistry adds/removes rows, preventing values from being restored onto the wrong radio controls. The four-custom limit is enforced in both UI and backend, not only by hiding an Add button.

Validation: API roundtrips, independent account isolation, rejected writes preserving saved answers, normalized duplicate rejection and four-custom limit. Browser checks cover adding four, independent own/partner choices, save/reload, removal reopening a slot and 320px overflow. Existing signup/browser and mobile unit tests also run. Local only; held for consolidated signup deployment.

Stats remains a design preview pending the wider Stats integration. Chemistry code is implemented locally. Verification screenshots use local sample data and do not report live vendor configuration or successful checks.
