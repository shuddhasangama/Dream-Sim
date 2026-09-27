// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a) — Week's day
// strip: a real calendar date derived from week+weekday alone (clock.py's
// own WEEK_ONE_MONDAY epoch, 2026-01-05, a Monday), and every moment
// flattened per day regardless of whether it carries a `means`.
import test from 'node:test';
import assert from 'node:assert/strict';
import { dateOfMonth, momentsByDay, confirmedDateMoment, withRealDateOnly } from '../src/screens/week.js';

test('dateOfMonth: week 1 is the epoch week itself (Mon 5 Jan 2026 … Sun 11 Jan)', () => {
  assert.equal(dateOfMonth(1, 'Mon'), 5);
  assert.equal(dateOfMonth(1, 'Wed'), 7);
  assert.equal(dateOfMonth(1, 'Sun'), 11);
});
test('dateOfMonth advances a full week per week number, crossing a month boundary correctly', () => {
  assert.equal(dateOfMonth(4, 'Mon'), 26); // 5 + 3*7 = 26 Jan
  assert.equal(dateOfMonth(5, 'Mon'), 2);  // 5 + 4*7 = 33rd day => 2 Feb
});
test('dateOfMonth is null for an unrecognized day or a missing week', () => {
  assert.equal(dateOfMonth(1, 'Someday'), null);
  assert.equal(dateOfMonth(undefined, 'Mon'), null);
});

test('momentsByDay keeps every moment (not only ones with a means), sorted by hour', () => {
  const grid = {
    days: [{ day: 'Mon' }, { day: 'Tue' }],
    rows: [
      { days: [{ day: 'Mon', moments: [{ day: 'Mon', hour: 18, key: 'z', label: 'Z' }] }, { day: 'Tue', moments: [] }] },
      { days: [{ day: 'Mon', moments: [{ day: 'Mon', hour: 12, key: 'a', label: 'A', means: 'explains A' }] }, { day: 'Tue', moments: [] }] },
    ],
  };
  const byDay = momentsByDay(grid);
  assert.deepEqual(byDay.Mon.map((m) => m.key), ['a', 'z']); // hour 12 before hour 18
  assert.deepEqual(byDay.Tue, []);
});

// A design-review finding: week_map's Fri/Sat/Sun meal-slot moments are a
// fixed, always-present template ("a confirmed slot can fall anywhere
// across the weekend"), never real bookings — showing all of them as
// full-width event cards could read as three actual dates. Only the one
// that matches this couple's own confirmed plan (day + hour) survives.
test('confirmedDateMoment derives day+hour from date_plan.datetime alone', () => {
  assert.deepEqual(confirmedDateMoment({ datetime: '2026-01-10T19:30:00' }), { day: 'Sat', hour: 19 });
  assert.equal(confirmedDateMoment(null), null);
  assert.equal(confirmedDateMoment({ status: 'pending_signatures' }), null); // no datetime yet
});

test('withRealDateOnly drops every generic weekend slot except the one that actually matches the plan', () => {
  const byDay = {
    Sat: [
      { key: 'date_sat_m', day: 'Sat', hour: 9, tone: 'date', label: 'Bkfst' },
      { key: 'date_sat_e', day: 'Sat', hour: 19, tone: 'date', label: 'Dinner' },
      { key: 'rc_ends', day: 'Sat', hour: 11, tone: 'reality', label: 'RC Closes' },
    ],
  };
  const out = withRealDateOnly(byDay, { datetime: '2026-01-10T19:00:00' });
  assert.deepEqual(out.Sat.map((m) => m.key), ['date_sat_e', 'rc_ends']); // the non-matching Bkfst slot is gone
  assert.equal(out.Sat[0].personal, true);
  assert.ok(out.Sat[0].means);
});
test('withRealDateOnly drops every generic slot when there is no confirmed plan yet', () => {
  const byDay = { Fri: [{ key: 'date_fri', day: 'Fri', hour: 21, tone: 'date', label: 'Dinner' }] };
  assert.deepEqual(withRealDateOnly(byDay, null).Fri, []);
});
