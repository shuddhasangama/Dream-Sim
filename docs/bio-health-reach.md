# Bio disclosures and REACH preferences

Bio owns optional consented health/accessibility categories and a note (500 characters).
REACH owns private partner openness. Its health endpoint uses the same REACH lock
as the existing controls and returns freshly computed mutual counts.
Both users must satisfy each other's preferences. All disclosed categories must
be accepted; missing/withdrawn disclosure remains unknown, never condition-free.
Empty specific selections are rejected. No-filter ignores disclosure status.
Show all pauses health filtering without deleting preferences; restore filters restores it. Saving health preferences reactivates the chosen setting.

New endpoints: PUT /api/v1/profile/bio, POST /api/v1/profile/bio/withdraw,
POST /api/v1/reach/health. Bio saves preserve partner preferences; withdrawal
clears categories and note even while REACH is locked. Legacy personal writes
also respect the REACH lock. No schema migration is required.

Existing broad categories remain intact. New narrower categories are opt-in;
there is no automatic remapping of sensory, non-visible, trauma or cancer history.
Notes, photographs and BGV information are never parsed into matching categories.
Match disclosures appear in Bio, separate from Stats, on web and mobile.
Browser Bio is /bio; mobile Bio is accessible from Home and guided signup.

Deploy backend/static/templates to Railway together. Rebuild mobile through
Codemagic for the new app controls. Nothing here changes production until deployed.
Test both users: disclose with consent, set specific REACH preferences, check
counts, freeze at lock-in, reject preference changes, withdraw disclosure, and
confirm it is no longer exposed in match Bio. Existing pairs are not dissolved.
