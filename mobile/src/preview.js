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
    sliders: [
      { key: 'age', label: 'Age', unit: 'yrs', min: 18, max: 70, step: 1, current: [27, 36], suggested: [26, 38], self_value: 30, ignored: false, delta_if_ignored: 2, basic: true, sensitive: false },
      { key: 'distance_km', label: 'Distance', unit: 'km', min: 0, max: 1600, step: 10, current: [0, 40], suggested: null, self_value: null, ignored: false, delta_if_ignored: 4, basic: true, sensitive: false },
      { key: 'height_cm', label: 'Height', unit: 'cm', min: 140, max: 210, step: 1, current: [160, 185], suggested: [158, 182], self_value: 169, ignored: false, delta_if_ignored: 1, basic: false, sensitive: false },
    ],
    filters: [
      { name: 'veg_only', label: 'Diet', on_label: 'Vegetarian only', kind: 'dealbreaker', basic: true, control: 'choice', ignored: false, value: true, delta_if_ignored: 3, sensitive: false, blurb: '' },
      { name: 'wants_kids', label: 'Wants kids', on_label: 'Required', kind: 'dealbreaker', basic: true, control: 'choice', ignored: true, value: true, delta_if_ignored: 1, sensitive: false, blurb: '' },
      { name: 'no_kids_wanted', label: 'Does not want kids', on_label: 'Required', kind: 'dealbreaker', basic: true, control: 'choice', ignored: true, value: false, delta_if_ignored: 0, sensitive: false, blurb: '' },
      { name: 'nationality', label: 'Nationality', on_label: 'IN, NRI', kind: 'lever', basic: false, control: 'choice', ignored: false, value: ['IN', 'NRI'], delta_if_ignored: 1, sensitive: true, blurb: '' },
    ],
  };
  function reachIgnoredSummary() {
    const switched = [...reach.sliders.filter((s) => s.ignored), ...reach.filters.filter((f) => f.ignored)];
    const all = [...reach.sliders, ...reach.filters];
    return { ignored_count: switched.length, all_ignored: all.length > 0 && all.every((f) => f.ignored) };
  }
  function reachState() { return { ...reach, ...reachIgnoredSummary() }; }

  // "The week" grid, mirroring week_map.py's own algorithm (BANDS/MOMENTS)
  // against a fixed clock — a faithful preview fixture, not a second copy
  // of production logic (the real grid always comes from the server).
  const WM_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const WM_BANDS = [['morn', 'MORN', 0, 12], ['aft', 'AFT', 12, 17], ['eve', 'EVE', 17, 21], ['night', 'NIGHT', 21, 24]];
  const WM_MOMENTS = [
    { key: 'match_1', at: ['Mon', 12], label: 'Match 1', tone: 'match', kind: 'Matches', means: 'Match 1 is revealed. You have until Tuesday midday.' },
    { key: 'rc_ends', at: ['Mon', 11], label: 'RC ends', tone: 'reality', kind: 'Reality Check', means: "Last week's Reality Check closes, just before the new week opens." },
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
    { key: 'feedback', at: ['Sun', 21], label: 'Reality', tone: 'reality', kind: 'After', means: 'Feedback closes the week, and next week’s Reality Check is drawn from it.' },
  ];
  function weekMapGrid(now) {
    const today = now?.day ?? null;
    const bandFor = (hour) => (WM_BANDS.find(([, , s, e]) => hour >= s && hour < e) || WM_BANDS[WM_BANDS.length - 1])[0];
    const cells = {};
    for (const m of WM_MOMENTS) {
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

  const visionGoals = [{ key: 'Intimacy', stance: ['Emotional'] }, { key: 'Cohabitate', stance: ['Chores split'] }];
  const visionElementKeys = ['children', 'cohabitation', 'relocation', 'career', 'intimacy', 'travel'];
  let visionEntries = [];
  let visionChanges = [];

  const chemistryBuckets = [['good', '★', 'Already good at it'], ['improve', '↑', 'Want to improve'], ['maybe', '?', 'Never considered, so maybe'], ['no', '✕', 'Not my cup of tea']];
  const chemistryActivities = ['Cooking', 'Hiking', 'Salsa', 'Tennis', 'Yoga', 'Photography', 'Board games', 'Live gigs', 'Cycling', 'Pottery', 'Stand-up', 'Scuba diving'];
  let chemistryPicks = { Cooking: 'good', Hiking: 'good', Salsa: 'improve', Tennis: 'improve', Yoga: 'no', Photography: 'maybe' };

  let statsData = { age: 30, height_cm: 169, weight_kg: 66, waist_in: 31, income_band: '₹₹₹ · 25L–50L', education: "Master's", nationality: 'IN', profession: 'Engineering',
    diet: 'Everything', religion: 'Hindu', smoking: 'Never', drinking: 'Socially', fitness_routine: 'Gym 3x/week', marital_history: 'Never married', ethnicity: ['South Asian'], languages: ['English', 'Hindi'], cuisine: ['North Indian', 'Italian'], budget: ['₹2,500–4,000'] };
  const statChanges = [];
  const STAT_OPTIONS = { education: ["Bachelor's", "Master's", 'PhD'], nationality: ['IN', 'NRI'], profession: ['Engineering', 'Design', 'Medicine', 'Law'], diet: ['Vegetarian', 'Vegan', 'Everything'], smoking: ['Never', 'Occasionally', 'Regularly'], drinking: ['Never', 'Socially', 'Regularly'], fitness_routine: ['Sedentary', 'Occasional', 'Gym 3x/week', 'Athlete'], marital_history: ['Never married', 'Divorced', 'Widowed'], ethnicity: ['South Asian', 'East Asian', 'Mixed', 'Other'], religion: ['Hindu', 'Muslim', 'Christian', 'Other'], languages: ['English', 'Hindi', 'Tamil', 'Bengali'], cuisine: ['North Indian', 'South Indian', 'Italian', 'Cafe'], income_band: ['₹₹ · 10L–25L', '₹₹₹ · 25L–50L', '₹₹₹₹ · 50L+'], budget: ['₹1,500–2,500', '₹2,500–4,000', '₹4,000+'] };
  const STAT_RANGES = { age: [21, 75], height_cm: [140, 210], weight_kg: [40, 150], waist_in: [20, 55] };
  function statsRows() {
    const editable = ['height_cm', 'weight_kg', 'waist_in', 'diet', 'religion', 'smoking', 'drinking', 'fitness_routine', 'marital_history', 'ethnicity', 'languages', 'cuisine', 'budget'];
    const verified = ['age', 'education', 'nationality', 'profession', 'income_band'];
    return [
      ...editable.map((key) => ({ key, value: statsData[key] ?? null, editable: true, why: 'open', reason: null })),
      ...verified.map((key) => ({ key, value: statsData[key] ?? null, editable: false, why: 'verified', reason: 'Vouched for by a background check, so it is not typed over. If one has genuinely changed, send it back to be re-checked — the value moves when the check clears, not when you say so.' })),
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
      user:{user_id:'preview-user',display_name:'Preview profile',journey_state:'dating',bgv_status:'verified'},
      stage_indicator:{show:true,current:'dating',label:'Dating',stages:[
        {key:'dating',label:'Dating',state:'current'},{key:'relationship',label:'Relationship',state:'todo'},
        {key:'engaged',label:'Engaged',state:'todo'},{key:'married',label:'Married',state:'todo'}]},
      milestones:['registered','verified'],
      contact_verification:{required:true,satisfied:true,verified_email:false,verified_phone:true},
      clock:week.clock,
      current_lock_in:week.lock_in,current_date_plan:week.date_plan,current_couple:null,
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
        {key:'relationship',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
        {key:'journey',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
      ],
      next_action:{headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
        destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}}},
    });
    if (path.endsWith('/profile')) return ok({stats:{age:30,height_cm:169,weight_kg:66,waist_in:31,income_band:'₹₹₹ · 25L–50L',diet:'Everything',education:"Master's",nationality:'IN',religion:'Hindu',city:'Bangalore',profession:'Engineering'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});

    if (path.endsWith('/guidance')) return ok({headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
      destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}}});

    if (path.endsWith('/profile/vision') && method === 'GET') return ok({goals:visionGoals,element_keys:visionElementKeys,entries:visionEntries,changes:visionChanges});
    if (path.endsWith('/profile/vision/details')) {
      const existing = visionEntries.filter((e) => e.element_key === body.element_key);
      const row = { id: 'vision-entry-'+(visionEntries.length+1), user_id: 'preview-user', element_key: body.element_key, detail_text: body.detail_text, added_at: 'Mon:12', parent_id: existing.length ? existing[existing.length-1].id : null };
      visionEntries = [...visionEntries, row];
      return ok({goals:visionGoals,element_keys:visionElementKeys,entries:visionEntries,changes:visionChanges});
    }
    if (path.endsWith('/profile/vision/changes')) {
      if (body.disclosed_to_partner !== true) return err('A reversal must be disclosed to the partner.', 409);
      const row = { id: 'vision-change-'+(visionChanges.length+1), user_id: 'preview-user', element_key: body.element_key, from_value: body.from_value, to_value: body.to_value, declared_at: 'Mon:12', disclosed_to_partner: true, guru_conversation_id: 'guru-preview' };
      visionChanges = [...visionChanges, row];
      return ok({goals:visionGoals,element_keys:visionElementKeys,entries:visionEntries,changes:visionChanges});
    }

    if (path.endsWith('/profile/chemistry') && method === 'GET') return ok({ activities: chemistryPicks, activity_options: chemistryActivities, buckets: chemistryBuckets });
    if (path.endsWith('/profile/chemistry/activities')) {
      chemistryPicks = { ...body.activities };
      return ok({ activities: chemistryPicks, activity_options: chemistryActivities, buckets: chemistryBuckets });
    }

    if (path.endsWith('/profile/stats') && method === 'GET') return ok({ rows: statsRows(), options: STAT_OPTIONS, ranges: STAT_RANGES, changes: statChanges });
    if (path.endsWith('/profile/stats') && method === 'PATCH') {
      Object.assign(statsData, body.fields);
      return ok({ saved: Object.keys(body.fields || {}) });
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
      if (target) target.ignored = !!body.ignore;
      return ok(reachState());
    }
    if (path.endsWith('/reach/show-all')) {
      [...reach.sliders, ...reach.filters].forEach((f) => { f.ignored = !!body.ignore; });
      return ok(reachState());
    }

    if (path.endsWith('/week/prepare')) { week.prepared = true; return ok(week); }
    if (path.endsWith('/week')) return ok(week);
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
      return ok(debrief);
    }

    throw new Error('Unsupported preview request: '+method+' '+path);
  };
}
