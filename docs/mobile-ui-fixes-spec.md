# Mobile UI Fixes — Phase 5, Step 3 Review

Fixes from on-device review of the DhaShu iOS/Android build. All changes are in
`mobile/src/` — shared JavaScript, so **one fix covers both platforms**. No
platform-specific work required.

Read alongside `docs/mobile-journey-build-spec.md`. The authoritative visual
reference is the existing **web templates** (`templates/*.html`) and the mockups —
the mobile screens must match those, adapted for a phone, not reinvented.

---

## 0. Global layout

**Navigation bars scroll away and expose raw horizontal scrollbars.**

- Make the top nav (Dashboard · Vision · Chemistry · Stats · Reach · Week) **sticky**
  so it stays visible while the page scrolls
- Same for the stage tabs (Dating · Relationship · Engaged · Married)
- **Hide the scrollbar chrome** on both — keep them swipeable, but remove the visible
  `◀ ▬▬▬ ▶` bar. Use `scrollbar-width: none` / `::-webkit-scrollbar { display: none }`
- Consider shortening labels on narrow screens so fewer items need scrolling at all

---

## 1. Dashboard

1. **Missing parameters.** The mobile dashboard shows far less than the web version.
   Compare against the web dashboard template and bring across every field it
   displays. Do not decide unilaterally what to omit.
2. **Remove "Refresh Dashboard".** Screens should refresh on navigation and on
   pull-to-refresh, not via a button. Delete it.

---

## 2. REACH

3. **Label it "REACH · Reality Check"** wherever the feature is named — nav item,
   screen heading, and any call-to-action button.

4. **Age and Distance are duplicated and inconsistent.** Each currently shows both a
   range slider *and* a separate ANY checkbox. Rebuild to match the original design:
   - Show **the user's own value as a fixed reference point on the line**
     (e.g. "YOU: 38 YRS" marked on the age track)
   - A **single range control** to widen or narrow around it
   - The delta indicator ("+1 ON ANY") stays

5. **All other filters are inconsistent.** Diet, Wants kids, Does not want kids
   currently render as a label plus a checkbox — unlike the sliders above them.
   Bring every filter into one consistent pattern matching the web design.
   One visual language for all filters, not two.

6. **"Add missing stats" is absent.** The web version prompts the user to complete
   stats that are limiting their reciprocity. Restore it.

7. **Grammar bug:** the summary reads "**1 people**". Singularise correctly —
   "1 person" / "2 people".

---

## 3. Week

8. **The calendar is the feature — it must not be lost.** The current render is a
   cramped horizontally-scrolling grid with truncated labels ("AON", "ends", "Rank").
   Rebuild it as a proper weekly calendar, using the existing Week mockup and the
   web template as the reference.
9. **Abbreviate deliberately, not accidentally.** Short day headers (M T W T F S S)
   and short slot labels are fine — truncated mid-word is not. Nothing should be cut
   off or require horizontal scrolling to read.
10. Keep the colour-coded legend (Matches · Reality Check · Calendar · Agreement ·
    Dates · After) and the "What each one means" expander.

---

## 4. Chemistry and Stats

11. These screens need proper UI work to match the web version, **including the
    legend**. Compare each against its web template and close the gap — same
    grouping, same legend treatment, same spacing conventions.

---

## 5. Guru

12. **Inconsistent with the design of record.** Rebuild per `agent-4-guru` and
    `docs/relationship-stage-spec.md`:
    - Coral "G" avatar in a bordered panel — the established Guru voice component
    - Reflects and structures only; **never nudges escalation**, never suggests
      progressing a stage, inviting home, or sharing contacts
    - In the Dating stage Guru's role is limited (pre-date courtesies, post-date
      feedback capture, pass-reason capture) — the four pillars belong to
      Relationship onward

---

## 6. Sign-in

**Already built and working** — phone number → SMS code → session, verified on
device. No work needed. Do not rebuild it.

---

## Constraints (unchanged)

- Match the **web templates** as the visual source of truth; adapt for phone, don't reinvent
- No hardcoded constants — enums, slots and options come from the API
- No appearance or skin-tone fields anywhere
- Keep all 27 unit tests and 5 e2e tests passing; add tests for any new behaviour
- Close resources opened in tests
