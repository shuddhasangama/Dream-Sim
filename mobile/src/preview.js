// Local browser development only; imported into a separate module for
// testing. Mutable preview state below exists so widen/ignore/prepare/match
// actions actually change what a later GET returns, the same way the real
// API's per-user state does — not just fixed fixtures.
export function previewTransport() {
  let active = false;

  let reach = {
    counts: { mutual_open: 1, fits_user_filters: 6, no_realistic_matches: false },
    counting_unverified: false,
    deltas: [],
    // Every lever/dealbreaker matching.py's IGNORABLE covers, so "More
    // filters" (road-fixes-clock-spec.md §5) has the full set to prove out
    // against — reach.js discovers this list from the response, it never
    // hardcodes it, so what's here is what shows up.
    sliders: [
      // round3-fixes-spec.md §4.1: track 21-80, self_value 38 — the
      // spec's own test fixture, so the marker's on-track position is
      // directly checkable in preview/e2e.
      { key: 'age', label: 'Age', unit: 'yrs', min: 21, max: 80, step: 1, current: [27, 42], suggested: [32, 44], self_value: 38, ignored: false, delta_if_ignored: 2, basic: true, sensitive: false },
      { key: 'distance_km', label: 'Distance', unit: 'km', min: 0, max: 1600, step: 10, current: [0, 40], suggested: null, self_value: null, ignored: false, delta_if_ignored: 4, basic: true, sensitive: false },
      { key: 'height_cm', label: 'Height', unit: 'cm', min: 140, max: 210, step: 1, current: [160, 185], suggested: [158, 182], self_value: 169, ignored: false, delta_if_ignored: 1, basic: false, sensitive: false },
      { key: 'weight_kg', label: 'Weight', unit: 'kg', min: 40, max: 150, step: 1, current: [55, 80], suggested: [58, 78], self_value: 66, ignored: false, delta_if_ignored: 1, basic: false, sensitive: false },
      { key: 'waist_in', label: 'Waist', unit: 'in', min: 20, max: 55, step: 1, current: [26, 36], suggested: [27, 34], self_value: 31, ignored: false, delta_if_ignored: 0, basic: false, sensitive: false },
    ],
    filters: [
      { name: 'veg_only', label: 'Diet', on_label: 'Vegetarian only', kind: 'dealbreaker', basic: true, control: 'choice', ignored: false, value: true, delta_if_ignored: 3, sensitive: false, blurb: '', opposite: null },
      // round3-fixes-spec.md §4.3: education as a real REACH filter.
      { name: 'education', label: 'Education', on_label: 'As set', kind: 'lever', basic: true, control: 'choice', ignored: false, value: ["Bachelor's", "Master's", 'Doctorate'], delta_if_ignored: 1, sensitive: false, blurb: '', opposite: null },
      // round3-fixes-spec.md §4.2: two answers to one question — see
      // matching.py's _OPPOSITES and its `opposite` field on each row.
      { name: 'wants_kids', label: 'Wants kids', on_label: 'Only people who do', kind: 'dealbreaker', basic: true, control: 'choice', ignored: true, value: true, delta_if_ignored: 1, sensitive: false, blurb: '', opposite: 'no_kids_wanted' },
      { name: 'no_kids_wanted', label: 'Does not want kids', on_label: "Only people who don't", kind: 'dealbreaker', basic: true, control: 'choice', ignored: true, value: false, delta_if_ignored: 0, sensitive: false, blurb: '', opposite: 'wants_kids' },
      { name: 'nationality', label: 'Nationality', on_label: 'IN, NRI', kind: 'lever', basic: false, control: 'choice', ignored: false, value: ['IN', 'NRI'], delta_if_ignored: 1, sensitive: true, blurb: '', opposite: null },
      { name: 'religion', label: 'Religion', on_label: 'As set', kind: 'lever', basic: false, control: 'choice', ignored: false, value: 'Hindu', delta_if_ignored: 1, sensitive: true, blurb: '', opposite: null },
      { name: 'non_smoker', label: 'Non-smoker', on_label: 'Never or quitting', kind: 'dealbreaker', basic: false, control: 'choice', ignored: true, value: false, delta_if_ignored: 0, sensitive: false, blurb: '', opposite: null },
      { name: 'non_drinker', label: 'Non-drinker', on_label: 'Rarely or never', kind: 'dealbreaker', basic: false, control: 'choice', ignored: true, value: false, delta_if_ignored: 0, sensitive: false, blurb: '', opposite: null },
    ],
  };
  function reachIgnoredSummary() {
    const switched = [...reach.sliders.filter((s) => s.ignored), ...reach.filters.filter((f) => f.ignored)];
    const all = [...reach.sliders, ...reach.filters];
    return { ignored_count: switched.length, all_ignored: all.length > 0 && all.every((f) => f.ignored) };
  }
  // round3-fixes-spec.md §4.3: every real lever is already unlocked in
  // this fixture (a slider or filter entry exists for all seven), so
  // there is nothing to list here — matches the real API always
  // including the key, empty or not.
  function reachState() { return { ...reach, locked_levers: [], ...reachIgnoredSummary() }; }

  // "The week" grid, mirroring week_map.py's own algorithm (BANDS/MOMENTS)
  // against a fixed clock — a faithful preview fixture, not a second copy
  // of production logic (the real grid always comes from the server).
  const WM_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const WM_BANDS = [['morn', 'MORN', 0, 12], ['aft', 'AFT', 12, 17], ['eve', 'EVE', 17, 21], ['night', 'NIGHT', 21, 24]];
  const WM_MOMENTS = [
    { key: 'match_1', at: ['Mon', 12], label: 'Match 1', tone: 'match', kind: 'Matches', means: 'Match 1 is revealed. You have until Tuesday midday.' },
    { key: 'rc_ends', at: ['Mon', 11], label: 'RC Closes', tone: 'reality', kind: 'Reality Check', means: "Last week's Reality Check closes, just before the new week opens." },
    { key: 'rank', at: ['Tue', 11], label: 'Rank', tone: 'muted', kind: 'Matches', means: 'Keenness from Match 1 is counted before Match 2 is drawn.' },
    { key: 'match_2', at: ['Tue', 12], label: 'Match 2', tone: 'match', kind: 'Matches', means: "Match 1's window closes and Match 2 is revealed." },
    { key: 'match_3', at: ['Wed', 12], label: 'Match 3', tone: 'match', kind: 'Matches', means: "Match 2's window closes and Match 3 is revealed — the last of the week." },
    { key: 'slots', at: ['Wed', 18], label: 'Slots', tone: 'calendar', kind: 'Calendar', means: 'Match 3 closes and the calendar opens. Offer the weekend slots that suit you.' },
    { key: 'calendar_closes', at: ['Thu', 12], label: 'Publish', tone: 'publish', kind: 'Calendar', means: 'The calendar closes and the overlap is published to you both.' },
    { key: 'sign', at: ['Thu', 18], label: 'Sign', tone: 'publish', kind: 'Agreement', means: 'The date agreement opens. It needs both signatures; one on its own confirms nothing.' },
    { key: 'date_fri', at: ['Fri', 21], label: 'Dinner', tone: 'date', kind: 'Dates' },
    { key: 'date_sat_e', at: ['Sat', 19], label: 'Dinner', tone: 'date', kind: 'Dates' },
    { key: 'date_sun_a', at: ['Sun', 13], label: 'Lunch', tone: 'date', kind: 'Dates' },
    { key: 'debrief', at: ['Sat', 21], label: 'Debrief', tone: 'debrief', kind: 'After', means: 'The debrief opens an hour after a date, not before it.' },
    { key: 'feedback', at: ['Sun', 21], label: 'RC Opens', tone: 'reality', kind: 'Reality Check', means: 'Feedback closes the week, and next week’s Reality Check is drawn from it.' },
  ];
  // round3-fixes-spec.md §5.2/§5.3: mirrors dateplan.debrief_opens_hour()
  // so the preview's own "replace in place" personalization is computed
  // the same way the real server does, not a second set of numbers.
  const WM_MEAL_SLOT_TIMES = { breakfast: [9, 0], lunch: [13, 0], coffee: [17, 0], dinner: [19, 30] };
  function debriefOpensHour(mealSlot) {
    const [hour, minute] = WM_MEAL_SLOT_TIMES[mealSlot] || [21, 0];
    return Math.min(23, Math.ceil((hour * 60 + minute + 60) / 60));
  }
  function personalDebriefMoment(plan) {
    if (!plan?.datetime) return null;
    const [datePart] = plan.datetime.split('T');
    const dayIndex = (new Date(datePart + 'T00:00:00Z').getUTCDay() + 6) % 7; // Mon=0
    return { key: 'debrief', at: [WM_DAYS[dayIndex], debriefOpensHour(plan.meal)], label: 'Debrief',
      tone: 'debrief', kind: 'After', means: "Opens an hour after your actual date — this date's real time, not a fixed slot." };
  }
  function poolReturnMoment(released) {
    if (!released) return null;
    const feedback = WM_MOMENTS.find((m) => m.key === 'feedback');
    return { ...feedback, means: "You're back in the pool — Reality Check for the coming week applies to you." };
  }
  function weekMapGrid(now, { personalDebrief = null, personalPoolReturn = null } = {}) {
    const today = now?.day ?? null;
    const bandFor = (hour) => (WM_BANDS.find(([, , s, e]) => hour >= s && hour < e) || WM_BANDS[WM_BANDS.length - 1])[0];
    let moments = WM_MOMENTS;
    if (personalDebrief) moments = moments.filter((m) => m.key !== 'debrief').concat({ ...personalDebrief, personal: true });
    if (personalPoolReturn) moments = moments.filter((m) => m.key !== 'feedback').concat({ ...personalPoolReturn, personal: true });
    const cells = {};
    for (const m of moments) {
      const [day, hour] = m.at;
      const band = bandFor(hour);
      const past = now ? (WM_DAYS.indexOf(day) < WM_DAYS.indexOf(now.day) || (day === now.day && hour < now.hour)) : false;
      (cells[band + '|' + day] ??= []).push({ ...m, hour, day, past, time: String(hour).padStart(2, '0') + ':00' });
    }
    return {
      days: WM_DAYS.map((d) => ({ day: d, is_today: d === today })),
      rows: WM_BANDS.map(([key, label]) => ({ key, label, days: WM_DAYS.map((d) => ({ day: d, is_today: d === today, moments: cells[key + '|' + d] || [] })) })),
      midday_after: 'morn', midday_label: 'MIDDAY (12:00)',
    };
  }
  function weekMapLegend() {
    const seen = new Map();
    for (const m of WM_MOMENTS) if (!seen.has(m.kind)) seen.set(m.kind, { kind: m.kind, tone: m.tone });
    return [...seen.values()];
  }

  // Mirrors clock.py's own checkpoint-based phase() against the same
  // §1 timeline WM_MOMENTS already encodes, so stepping the preview clock
  // moves the phase the same way the real server would.
  function weekPhase(c) {
    const key = (day, hour) => WM_DAYS.indexOf(day) * 24 + hour;
    const k = key(c.day, c.hour);
    if (k < key('Mon', 12)) return 'before_week_start';
    if (k < key('Tue', 12)) return 'match_1_open';
    if (k < key('Wed', 12)) return 'match_2_open';
    if (k < key('Wed', 18)) return 'match_3_open';
    if (k < key('Thu', 12)) return 'calendar_open';
    if (k < key('Thu', 18)) return 'calendar_closed';
    if (k < key('Sun', 21)) return 'dates_live';
    return 'feedback_open';
  }

  // "Replace in place", the same personalization the real server applies
  // — only wired for personalDebrief here, since this preview fixture
  // has no release-tracking state to drive personalPoolReturn from.
  // Reads the FULLER `plan` object (declared further down, holds `meal`
  // and the ceremony's own status writes), not the compact `week.date_plan`
  // summary — the two are separate mock objects and only `plan` has both
  // the meal slot and the real post-ceremony 'confirmed' status.
  function personalizedGrid(now) {
    const personalDebrief = plan?.status === 'confirmed' ? personalDebriefMoment(plan) : null;
    return weekMapGrid(now, { personalDebrief });
  }

  function advanceClock(hours) {
    const c = week.clock;
    const weekLen = 24 * 7;
    let total = WM_DAYS.indexOf(c.day) * 24 + c.hour + hours;
    const weekDelta = Math.floor(total / weekLen);
    total = ((total % weekLen) + weekLen) % weekLen;
    week.clock = { mode: 'simulation', week: c.week + weekDelta, day: WM_DAYS[Math.floor(total / 24)], hour: total % 24 };
    week.phase = weekPhase(week.clock);
    week.schedule = { grid: personalizedGrid(week.clock), legend: weekMapLegend() };
  }

  let week = {
    clock: { mode: 'simulation', week: 1, day: 'Mon', hour: 12 },
    phase: 'match_1_open', mode: 'dating', prepared: true,
    prepare_request: { method: 'POST', path: '/api/v1/week/prepare', body: {} },
    schedule: { grid: weekMapGrid({ day: 'Mon', hour: 12 }), legend: weekMapLegend() },
    lock_in: null, date_plan: null,
    matches: [
      { id: 'match-1', week: 1, slot: 1, revealed_at: 'Mon:12', window_closes_at: 'Tue:12', action: 'none', status: 'open',
        candidate: { display_name: 'Priya Sharma', city: 'Bangalore', bgv_status: 'verified', visions: [{ key: 'Intimacy', stance: ['Emotional'] }], stats: { age: 29, height_cm: 162, profession: 'Design', income_band: '₹₹', education: "Master's", diet: 'Vegetarian', nationality: 'IN' } },
        their_interest: false, allowed_actions: ['interest', 'pass'] },
      { id: 'match-2', week: 1, slot: 2, revealed_at: 'Tue:12', window_closes_at: 'Wed:12', action: 'none', status: 'not_yet_revealed',
        candidate: null, their_interest: false, allowed_actions: [] },
    ],
  };

  let calendar = null; // built once locked in, see ensureLockedInState()
  let plan = null;
  let agreement = null;
  let debrief = null;

  // road-fixes-clock-spec.md §1: advance into Relationship stage once both
  // partners' post-date decision is 'relationship' — mirrors how a real
  // mutual gate resolves, simplified to fire on this one preview user's
  // own decision (there's no second simulated party in this fixture).
  let userJourneyState = 'dating';
  let couple = null;
  let road = null;
  function ensureCouple() {
    if (couple) return;
    couple = { id: 'couple-preview', stage: 'relationship', stage_week_index: 0, start_date: '2026-01-12' };
    road = {
      couple_id: couple.id, week_start: '2026-01-12',
      my_routine: [],
      my_obligations: [],
      partner_shared_obligations: [
        { type: 'travel', travel_mode: 'partner_solo', starts_at: '2026-01-20', ends_at: '2026-01-22', title: "Sister's wedding" },
      ],
      // Simplified derived availability (the real algorithm is routine
      // minus dated obligations, computed server-side) — a fixed evenings-
      // free baseline is enough to prove out sharing/overlap in preview.
      my_availability: { Mon: [], Tue: [], Wed: [], Thu: [], Fri: [{ day: 'Fri', start: '19:00', end: '22:00' }], Sat: [{ day: 'Sat', start: '10:00', end: '22:00' }], Sun: [{ day: 'Sun', start: '10:00', end: '20:00' }] },
      my_shared_slots: [],
      partner_shared_slots: [{ day: 'Sat', start: '10:00', end: '22:00' }],
      overlap: [],
      availability_mode: 'simulation_week',
      obligation_rule: 'Dated obligations remove the entire inclusive day from availability.',
    };
  }
  function recomputeOverlap() {
    const key = (s) => s.day + '|' + s.start + '|' + s.end;
    const partnerKeys = new Set(road.partner_shared_slots.map(key));
    road.overlap = road.my_shared_slots.filter((s) => partnerKeys.has(key(s)));
  }

  // round3-fixes-spec.md §7: mirrors vision.py's PILLAR_OPTIONS/validate_pillars()/
  // rc_open() so the preview enforces the same rules the server does.
  let visionGoals = [{ key: 'Intimacy', stance: ['Emotional', 'Physical'] }, { key: 'Cohabitate', stance: ['Chores split'] }, { key: 'Travel together', stance: null }];
  const PILLAR_OPTIONS = { Intimacy: ['Emotional', 'Physical'], 'Travel together': [], Kids: ['Naturally', 'Surrogacy', 'Adoption'], Cohabitate: ['Chores split', 'Expenses sharing'] };
  const visionElementKeys = ['Intimacy', 'Kids', 'Cohabitate', 'Travel together'];
  const VISION_EXPLANATION = 'Travel together takes no detail now. Kids and Cohabitate do, because picking either without saying what you mean says almost nothing — and they are revisited together, at the Relationship stage, once it is a decision rather than a preference.';
  let visionEntries = [];
  let visionChanges = [];
  const visionRcOpen = () => { const c = week.clock; return (c.day === 'Sun' && c.hour >= 21) || (c.day === 'Mon' && c.hour < 11); };
  const visionRead = () => ({ goals: visionGoals, element_keys: visionElementKeys, pillar_options: PILLAR_OPTIONS, detail_explanation: VISION_EXPLANATION, rc_open: visionRcOpen(), entries: visionEntries, changes: visionChanges });
  function visionValidate(map) {
    if (!(map.Intimacy || []).length) return 'Intimacy is mandatory — pick Emotional, Physical, or both.';
    const others = [];
    for (const k of ['Kids', 'Cohabitate', 'Travel together']) {
      if (!(k in map)) continue;
      if (k !== 'Travel together' && !map[k].length) return `${k} needs at least one sub-selection — picking it alone says almost nothing.`;
      if (k === 'Kids' && map[k].includes('Naturally') && !map.Intimacy.includes('Physical')) return 'Having kids naturally needs Physical intimacy selected too. Add it, or choose surrogacy or adoption instead.';
      others.push(k);
    }
    return others.length ? null : 'Pick at least one more pillar alongside Intimacy — Travel together, Kids, or Cohabitate.';
  }
  const visionMap = () => Object.fromEntries(visionGoals.map((g) => [g.key, Array.isArray(g.stance) ? [...g.stance] : []]));
  const visionCommit = (map) => { visionGoals = visionElementKeys.filter((k) => k in map).map((k) => ({ key: k, stance: map[k].length ? [...map[k]].sort() : null })); };

  const chemistryBuckets = [['good', '★', 'Already good at it'], ['improve', '↑', 'Want to improve'], ['maybe', '?', 'Never considered, so maybe'], ['no', '✕', 'Not my cup of tea']];
  const chemistryActivities = ['Cooking', 'Hiking', 'Salsa', 'Tennis', 'Yoga', 'Photography', 'Board games', 'Live gigs', 'Cycling', 'Pottery', 'Stand-up', 'Scuba diving'];
  let chemistryPicks = { Cooking: 'good', Hiking: 'good', Salsa: 'improve', Tennis: 'improve', Yoga: 'no', Photography: 'maybe' };

  let statsData = { age: 30, height_cm: 169, weight_kg: 66, waist_in: 31, income_band: '₹₹₹ · 25L–50L', education: "Master's", nationality: 'IN', profession: 'Engineering',
    diet: 'Everything', religion: 'Hindu', smoking: 'Never', drinking: 'Socially', fitness_routine: 'Gym 3x/week', marital_history: 'Never married', ethnicity: ['South Asian'], languages: ['English', 'Hindi'], cuisine: ['North Indian', 'Italian'], budget: ['₹2,500–4,000'] };
  // round3-fixes-spec.md §3: all five start actually verified, matching
  // the "Verified" pill this fixture's user already shows — editing one
  // reopens it (see the PATCH handler below), same as the real API.
  let statsChecks = { age: 'verified', education: 'verified', nationality: 'verified', profession: 'verified', income_band: 'verified' };
  const statChanges = [];
  const STAT_OPTIONS = { education: ["Bachelor's", "Master's", 'PhD'], nationality: ['IN', 'NRI'], profession: ['Engineering', 'Design', 'Medicine', 'Law'], diet: ['Vegetarian', 'Vegan', 'Everything'], smoking: ['Never', 'Occasionally', 'Regularly'], drinking: ['Never', 'Socially', 'Regularly'], fitness_routine: ['Sedentary', 'Occasional', 'Gym 3x/week', 'Athlete'], marital_history: ['Never married', 'Divorced', 'Widowed'], ethnicity: ['South Asian', 'East Asian', 'Mixed', 'Other'], religion: ['Hindu', 'Muslim', 'Christian', 'Other'], languages: ['English', 'Hindi', 'Tamil', 'Bengali'], cuisine: ['North Indian', 'South Indian', 'Italian', 'Cafe'], income_band: ['₹₹ · 10L–25L', '₹₹₹ · 25L–50L', '₹₹₹₹ · 50L+'], budget: ['₹1,500–2,500', '₹2,500–4,000', '₹4,000+'] };
  const STAT_RANGES = { age: [21, 75], height_cm: [140, 210], weight_kg: [40, 150], waist_in: [20, 55] };
  const VERIFIED_KEYS = ['age', 'education', 'nationality', 'profession', 'income_band'];
  const VERIFIED_EDIT_WARNING = 'This is vouched for by a background check. Changing it moves the value now, but drops it out of "verified" until BGV re-checks it — REACH filters and match cards will show it as pending in the meantime. Send it anyway?';
  function statsRows() {
    const editable = ['height_cm', 'weight_kg', 'waist_in', 'diet', 'religion', 'smoking', 'drinking', 'fitness_routine', 'marital_history', 'ethnicity', 'languages', 'cuisine', 'budget'];
    return [
      ...editable.map((key) => ({ key, value: statsData[key] ?? null, editable: true, why: 'open', reason: null, warning: null, check: null })),
      ...VERIFIED_KEYS.map((key) => {
        const verifiedNow = statsChecks[key] === 'verified';
        return { key, value: statsData[key] ?? null, editable: true,
          why: verifiedNow ? 'verified_editable' : 'open', reason: null,
          warning: verifiedNow ? VERIFIED_EDIT_WARNING : null, check: statsChecks[key] || null };
      }),
    ];
  }

  function ensureLockedInState() {
    if (calendar) return;
    calendar = {
      lock_in_id: week.lock_in.id, clock_mode: 'simulation',
      valid_slots: ['Fri', 'Sat', 'Sun'].flatMap((day) => ['breakfast', 'lunch', 'coffee', 'dinner'].filter((m) => !(day === 'Fri' && ['breakfast', 'lunch'].includes(m))).map((meal_slot) => ({ day, meal_slot }))),
      my_slots: [], partner_submitted: false, overlap: [],
      alignment: { mine: { budget: null, diet: null, cuisine: null }, my_missing: ['budget', 'diet', 'cuisine'], partner_missing: ['budget', 'diet', 'cuisine'],
        options: { budget: ['₹1,500–2,500', '₹2,500–4,000', '₹4,000+'], diet: ['No preference', 'Vegetarian', 'Vegan'], cuisine: ['North Indian', 'Italian', 'Cafe'] } },
      current_plan_id: null, editable: true,
      payment: { purpose: 'date_plan', scope_id: week.lock_in.id, satisfied: true, enforced: false, amount_inr: 0, provider_mode: 'simulation', api_payment_available: false },
      cycle: 1,
    };
  }

  const ok = (data, status=200) => ({status, data:{data,error:null}});
  const err = (message, status) => ({status, data:{error:{message},data:null}});

  return async (path, method, body) => {
    if (path.endsWith('/auth/request')) return ok({challenge_id:'local-preview'},202);
    if (path.endsWith('/auth/verify')) {
      if (body.code !== '123456') return {status:401,data:{error:{message:'Preview code is 123456.'},data:null}};
      active=true;
      return ok({access_token:'preview-access',refresh_token:'preview-refresh',expires_in:900});
    }
    if (path.endsWith('/auth/logout')) { active=false; return ok({logged_out:true}); }
    if (!active) return {status:401,data:{error:{message:'Sign in again.'},data:null}};

    if (path.endsWith('/journey/status')) return ok({
      user:{user_id:'preview-user',display_name:'Preview profile',journey_state:userJourneyState,bgv_status:'verified'},
      stage_indicator:{show:true,current:userJourneyState,label:userJourneyState==='dating'?'Dating':'Relationship',stages:[
        {key:'dating',label:'Dating',state:userJourneyState==='dating'?'current':'done'},{key:'relationship',label:'Relationship',state:userJourneyState==='relationship'?'current':'todo'},
        {key:'engaged',label:'Engaged',state:'todo'},{key:'married',label:'Married',state:'todo'}]},
      milestones:['registered','verified'],
      contact_verification:{required:true,satisfied:true,verified_email:false,verified_phone:true},
      clock:week.clock,
      // Preview is a dev/testing build — the stepping controls it proves
      // out (§7.6) are exactly what a real testing build would report.
      simulated_clock:true,
      current_lock_in:week.lock_in,current_date_plan:week.date_plan,current_couple:couple,
      surfaces:[
        {key:'dashboard',eligible:true,blocked_reason:null,api_available:true,request:null},
        {key:'reach',eligible:!week.lock_in,blocked_reason:week.lock_in?'REACH is closed while you are locked in or past Dating.':null,api_available:true,request:week.lock_in?null:{method:'GET',path:'/api/v1/reach'}},
        {key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}},
        {key:'guru',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/guidance'}},
        {key:'vision',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/vision'}},
        {key:'chemistry',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/chemistry'}},
        {key:'stats',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/profile/stats'}},
        {key:'calendar',eligible:!!week.lock_in,blocked_reason:week.lock_in?null:'This opens once you and someone have locked each other in.',api_available:!!week.lock_in,request:week.lock_in?{method:'GET',path:'/api/v1/lock-ins/'+week.lock_in.id+'/calendar'}:null},
        {key:'plan',eligible:!!week.date_plan,blocked_reason:week.date_plan?null:'This opens once a date is actually set.',api_available:!!week.date_plan,request:week.date_plan?{method:'GET',path:'/api/v1/date-plans/'+week.date_plan.id}:null},
        {key:'debrief',eligible:!!week.date_plan,blocked_reason:week.date_plan?null:'This opens once a date is actually set.',api_available:!!week.date_plan,request:week.date_plan?{method:'GET',path:'/api/v1/date-plans/'+week.date_plan.id+'/debrief'}:null},
        {key:'verify',eligible:false,blocked_reason:'You are already verified.',api_available:false,request:null},
        {key:'relationship',eligible:!!couple,blocked_reason:couple?null:'This opens once you have both agreed to be exclusive.',api_available:!!couple,request:couple?{method:'GET',path:'/api/v1/couples/'+couple.id}:null},
        {key:'journey',eligible:!!couple,blocked_reason:couple?null:'This opens once you have both agreed to be exclusive.',api_available:!!couple,request:couple?{method:'GET',path:'/api/v1/couples/'+couple.id}:null},
      ],
      next_action:{headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
        destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}}},
    });

    if (path.endsWith('/couples/'+encodeURIComponent(couple?.id||'')) && method === 'GET') {
      return ok({ couple: { id: couple.id, stage: couple.stage, stage_week_index: couple.stage_week_index, start_date: couple.start_date } });
    }
    if (path.endsWith('/couples/'+encodeURIComponent(couple?.id||'')+'/road') && method === 'GET') return ok(road);
    if (path.endsWith('/road/routine') && method === 'POST') {
      road.my_routine.push({ id: 'routine-'+(road.my_routine.length+1), category: body.category, days: body.days, label: body.label, start: body.start, end: body.end });
      return ok(road);
    }
    if (path.includes('/road/routine/') && method === 'DELETE') {
      const rid = path.split('/road/routine/')[1];
      road.my_routine = road.my_routine.filter((b) => b.id !== rid);
      return ok(road);
    }
    if (path.endsWith('/road/obligations') && method === 'POST') {
      road.my_obligations.push({ id: 'obligation-'+(road.my_obligations.length+1), type: body.type, travel_mode: body.travel_mode ?? null, starts_at: body.start_date, ends_at: body.end_date, title: body.title, shared: !!body.shared });
      return ok(road);
    }
    if (path.includes('/road/obligations/') && method === 'DELETE') {
      const rid = path.split('/road/obligations/')[1];
      road.my_obligations = road.my_obligations.filter((b) => b.id !== rid);
      return ok(road);
    }
    if (path.endsWith('/road/sharing') && method === 'PUT') {
      road.my_shared_slots = body.slots;
      recomputeOverlap();
      return ok(road);
    }
    // Reads straight off statsData/statsChecks rather than a fixed
    // snapshot, so a Dashboard/REACH stats save (round3-fixes-spec.md
    // §2/§3) actually shows up here on the next GET, the same way the
    // real API's per-user state does.
    if (path.endsWith('/profile')) return ok({stats:{...statsData,city:'Bangalore'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});

    // round3-fixes-spec.md §6.1/§6.2/§6.3: mirrors guru_dating.dating_context()/
    // pre_date_briefing() and journey_api.guidance()'s `also_open` — real
    // server content, not invented copy, so the mobile screen has something
    // faithful to render in preview.
    if (path.endsWith('/guidance')) return ok({headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
      destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}},
      also_open: [
        {code:'VB', title:'Vibes', subtitle:'What keeps this alive', destination:{key:'vibes',eligible:false,blocked_reason:"This isn't available right now.",api_available:false,request:null}},
      ],
      dating_context: {
        consent: "Every yes here is a real yes. Declining anything — a match, a slot, a second date — costs you nothing and is never shown to the other person as a rejection. What they see is that it didn't happen, never that you said no.",
        playbook: [
          'Matches are drawn for you through the week — there is no searching or swiping.',
          "Interest is private until it's mutual. A pass is never shown to the other person.",
          'Once you lock in with someone, you stop appearing to anyone else, and REACH closes for you.',
          'Contact details move in-app, only once both of you choose to share them.',
          'A date is confirmed once both of you sign the same agreement — one signature holds nothing.',
        ],
        date_prep: {
          courtesies: ['Arrive on time; message through the app if delayed', 'Be present — phone away, genuine attention', 'Basic table courtesy, and politeness to venue staff', 'Honour the agreed bill split gracefully — no scene over payment', 'End the date respectfully regardless of romantic outcome'],
          safety: ['Meet at the confirmed public venue', 'Share date details with a trusted contact outside the platform', 'In-app reporting is available at any time'],
          boundaries: ["The other person's stated greeting preference is shown before you meet — respect it", 'No recording or photographing without consent', 'Contact exchange happens in-app, by mutual choice'],
          partner_greeting: week.lock_in ? 'handshake' : null,
          note: 'Contact details are exchanged in-app when both are ready — never asked for in person.',
        },
      },
    });

    if (path.endsWith('/profile/vision') && method === 'GET') return ok(visionRead());
    if (path.endsWith('/profile/vision/details')) {
      const map = visionMap();
      const { pillar, sub_selection: sub } = body;
      if (!(pillar in PILLAR_OPTIONS) || (sub && !PILLAR_OPTIONS[pillar].includes(sub))) return err('Unknown pillar or sub-selection.', 400);
      if (pillar in map && (!sub || map[pillar].includes(sub))) return err('That is already part of your Vision.', 400);
      map[pillar] = [...(map[pillar] || []), ...(sub ? [sub] : [])];
      const bad = visionValidate(map);
      if (bad) return err(bad, 400);
      visionCommit(map);
      const row = { id: 'vision-entry-' + (visionEntries.length + 1), user_id: 'preview-user', element_key: pillar, detail_text: sub || pillar, added_at: 'Mon:12', parent_id: null };
      visionEntries = [...visionEntries, row];
      return ok(row);
    }
    if (path.endsWith('/profile/vision/changes')) {
      if (body.disclosed_to_partner !== true) return err('A change must be disclosed to your partner — it cannot be declared silently.', 409);
      if (!visionRcOpen()) return err('This is only editable while Reality Check is open.', 409);
      const map = visionMap();
      const { pillar } = body; const add = body.add || [], remove = body.remove || [];
      if (!(pillar in map)) return err('You have not set this pillar yet — use Add Detail instead.', 400);
      if (!add.length && !remove.length) return err('Nothing to change.', 400);
      const before = [...map[pillar]];
      const after = [...new Set([...before, ...add])].filter((x) => !remove.includes(x)).sort();
      if (after.length) map[pillar] = after; else if (pillar === 'Intimacy') map[pillar] = []; else delete map[pillar];
      const bad = visionValidate(map);
      if (bad) return err(bad, 400);
      visionCommit(map);
      const row = { id: 'vision-change-' + (visionChanges.length + 1), user_id: 'preview-user', element_key: pillar, from_value: before.join(', ') || '(none)', to_value: after.join(', ') || '(none)', declared_at: 'Mon:12', disclosed_to_partner: 1, guru_conversation_id: null };
      visionChanges = [...visionChanges, row];
      return ok(row);
    }

    if (path.endsWith('/profile/chemistry') && method === 'GET') return ok({ activities: chemistryPicks, activity_options: chemistryActivities, buckets: chemistryBuckets });
    if (path.endsWith('/profile/chemistry/activities')) {
      // Mirrors onboarding.MIN_SORTED=4 (validate_activities) so the
      // below-minimum path is actually reachable in preview.
      const count = Object.keys(body.activities || {}).length;
      if (count < 4) return err(`Sort at least 4 activities (${count}/4 so far).`, 400);
      chemistryPicks = { ...body.activities };
      return ok({ activities: chemistryPicks, activity_options: chemistryActivities, buckets: chemistryBuckets });
    }

    if (path.endsWith('/profile/stats') && method === 'GET') return ok({ rows: statsRows(), options: STAT_OPTIONS, ranges: STAT_RANGES, changes: statChanges });
    if (path.endsWith('/profile/stats') && method === 'PATCH') {
      const reopened = [];
      for (const [key, value] of Object.entries(body.fields || {})) {
        const before = statsData[key] ?? null;
        const after = value === '' || value == null ? null : value;
        const changed = JSON.stringify(before) !== JSON.stringify(after);
        if (changed && VERIFIED_KEYS.includes(key) && statsChecks[key] === 'verified') {
          statsChecks[key] = 'in_review';
          reopened.push(key);
        }
        statsData[key] = after;
      }
      return ok({ saved: Object.keys(body.fields || {}), reopened });
    }
    if (path.endsWith('/profile/stats/reverification')) return ok({ status: 'in_review', provider_mode: 'manual_review_required', verification_granted: false });

    if (path.endsWith('/reach') && method === 'GET') return ok(reachState());
    if (path.endsWith('/reach/widen')) {
      const slider = reach.sliders.find((s) => s.key === body.lever);
      if (slider) slider.current = [Math.max(slider.min, slider.current[0] - 2), Math.min(slider.max, slider.current[1] + 2)];
      return ok(reachState());
    }
    if (path.endsWith('/reach/set-range')) {
      const slider = reach.sliders.find((s) => s.key === body.lever);
      if (slider) slider.current = [body.min, body.max];
      return ok(reachState());
    }
    if (path.endsWith('/reach/ignore')) {
      const target = reach.sliders.find((s) => s.key === body.filter) || reach.filters.find((f) => f.name === body.filter);
      if (target) {
        target.ignored = !!body.ignore;
        // Mirrors matching.set_ignored(): turning a dealbreaker ON
        // clears its opposite (wanting kids and not wanting them can't
        // both be held at once).
        if (!body.ignore && target.opposite) {
          const opp = reach.filters.find((f) => f.name === target.opposite);
          if (opp) opp.ignored = true;
        }
      }
      return ok(reachState());
    }
    if (path.endsWith('/reach/show-all')) {
      [...reach.sliders, ...reach.filters].forEach((f) => { f.ignored = !!body.ignore; });
      return ok(reachState());
    }

    if (path.endsWith('/simulated-clock')) {
      if (typeof body.advance_hours === 'number') advanceClock(body.advance_hours);
      else if (body.week && body.day && body.hour != null) { week.clock = { mode: 'simulation', week: body.week, day: body.day, hour: body.hour }; week.phase = weekPhase(week.clock); week.schedule = { grid: personalizedGrid(week.clock), legend: weekMapLegend() }; }
      else return err('Provide either advance_hours or week+day+hour, not both.', 400);
      return ok({}); // caller reloads journey/status + week itself
    }
    if (path.endsWith('/week/prepare')) { week.prepared = true; return ok(week); }
    // Recomputed fresh on every read, same as the real _api_week_state()
    // — a cached week.schedule would go stale the moment date_plan's own
    // status changes (e.g. the ceremony completing) without the clock
    // itself moving.
    if (path.endsWith('/week')) return ok({ ...week, schedule: { grid: personalizedGrid(week.clock), legend: weekMapLegend() } });
    if (path.includes('/matches/') && path.endsWith('/actions')) {
      const id = path.split('/matches/')[1].split('/')[0];
      const match = week.matches.find((m) => m.id === id);
      if (!match) return err('Match not found.', 404);
      if (match.status !== 'open') return ok({ match_id: id, action: match.action, replayed: true });
      match.action = body.action;
      match.status = 'acted';
      if (body.action === 'interest') {
        // Mutual interest with the preview's one open candidate locks you in.
        week.lock_in = { id: 'lockin-preview', status: 'active', week: week.clock.week, dates_completed: 0 };
        week.mode = 'locked_in';
        ensureLockedInState();
      }
      return ok({ match_id: id, action: body.action, replayed: false });
    }

    if (path.endsWith('/calendar') && method === 'GET') return ok(calendar);
    if (path.endsWith('/alignment')) {
      calendar.alignment.mine = { budget: body.budget, diet: body.diet, cuisine: body.cuisine };
      calendar.alignment.my_missing = [];
      return ok(calendar);
    }
    if (path.endsWith('/availability')) {
      calendar.my_slots = body.slots;
      // Preview partner mirrors your first two picks, so overlap has something to confirm.
      calendar.partner_submitted = true;
      calendar.overlap = body.slots.slice(0, 2);
      return ok(calendar);
    }
    if (path.endsWith('/date-plan') && method === 'POST') {
      const id = 'plan-preview';
      calendar.current_plan_id = id;
      week.date_plan = { id, status: 'pending_signatures', datetime: `2026-01-0${['Fri','Sat','Sun'].indexOf(body.day)+9}T19:00` };
      plan = {
        id, lockin_id: week.lock_in.id, datetime: week.date_plan.datetime, meal: body.meal_slot, venue: 'Cafe Noir', cuisine: (calendar.alignment.mine.cuisine || [])[0] || null,
        budget_estimate: (calendar.alignment.mine.budget || [])[0] || null, bill_split: 'pay-your-own', status: 'pending_signatures',
        cancel_notice_hrs: 24, cancel_fee: 0, my_selections: { greeting: null, dietary: null, dress: null }, my_signed: false, partner_signed: false,
        payment: calendar.payment, face_mode: 'simulation', face_simulation_available: true,
      };
      agreement = {
        plan_id: id, step: 'playbook', complete: false, my_signed_name: null, my_signed_at: null,
        acknowledgements: [
          { key: 'ack_conduct', label: 'I will treat my match with respect.', term: 'Standard conduct expectations apply throughout the date.' },
          { key: 'ack_cancellation', label: 'I understand the cancellation terms.', term: '24 hours notice avoids the cancellation fee.' },
          { key: 'ack_not_a_relationship', label: 'I understand this is not a relationship yet.', term: 'Exclusivity is a separate, later step.' },
          { key: 'ack_liability', label: 'I accept the platform is not liable for what happens on the date.', term: 'DhaShu facilitates introductions only.' },
        ],
        clauses: [{ text: 'Meet in a public place for the first date.' }, { text: 'Either of you may leave at any time.' }],
        face_mode: 'simulation', face_simulation_available: true, payment: calendar.payment,
      };
      debrief = {
        plan_id: id, status: 'pending_signatures', clock_mode: 'simulation', opens_at: 'Sun:21', feedback_open: true, cancellable: true,
        cancellation: { late: false, hours_notice: 48, fee_inr: 0, compliance_event: null, reason: '' },
        my_feedback: { green_flags: [], red_flags: [], decision: null, reason: null, photo_consent: { together_photo: false, bill_photo: false }, no_show_reported: false },
        partner_submitted: false, mutual_photo_consent: { together_photo: false, bill_photo: false }, resolution: 'pending', no_show_is_confirmed: false,
        green_flag_options: ['Actually listened', 'On time', 'Asked good questions', 'Kind to staff', 'Made me laugh'],
        red_flag_options: ['Talked over me', 'Showed up late', 'Phone face-up the whole time'],
        decision_options: ['continue', 'relationship', 'pass'],
      };
      return ok({ match_id: id, action: 'confirmed', replayed: false });
    }

    if (path.endsWith('/selections')) { plan.my_selections = { ...plan.my_selections, dietary: body.dietary, dress: body.dress }; return ok(plan); }
    if (plan && path.endsWith('/date-plans/' + encodeURIComponent(plan.id)) && method === 'GET') return ok(plan);
    if (path.includes('/date-plans/') && path.endsWith('/agreement') && method === 'GET') return ok(agreement);
    if (path.endsWith('/agreement/steps')) {
      if (body.step === 'playbook' && agreement.step === 'playbook') agreement.step = 'sign';
      else if (body.step === 'sign' && agreement.step === 'sign') {
        agreement.my_signed_name = body.signed_name; agreement.my_signed_at = 'Fri:19'; agreement.step = 'face'; plan.my_signed = true;
      } else if (body.step === 'face' && agreement.step === 'face') { agreement.step = 'done'; agreement.complete = true; plan.status = 'confirmed'; }
      return ok(agreement);
    }
    if (path.endsWith('/debrief')) return ok(debrief);
    if (path.endsWith('/feedback/flags')) {
      debrief.my_feedback.green_flags = body.green_flags; debrief.my_feedback.red_flags = body.red_flags;
      debrief.my_feedback.photo_consent = { together_photo: !!body.together_photo, bill_photo: !!body.bill_photo };
      return ok(debrief);
    }
    if (path.endsWith('/feedback/decision')) {
      debrief.my_feedback.decision = body.decision; debrief.my_feedback.reason = body.reason;
      debrief.resolution = body.decision === 'pass' ? 'rejected' : body.decision === 'relationship' ? 'both_relationship' : 'keep_dating';
      if (body.decision === 'relationship') { userJourneyState = 'relationship'; ensureCouple(); }
      return ok(debrief);
    }

    throw new Error('Unsupported preview request: '+method+' '+path);
  };
}
