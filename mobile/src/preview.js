// Local browser development only; imported into a separate module for
// testing. Mutable preview state below exists so widen/ignore/prepare/match
// actions actually change what a later GET returns, the same way the real
// API's per-user state does — not just fixed fixtures.
export function previewTransport() {
  let active = false;

  let reach = {
    counts: { mutual_open: 3, fits_user_filters: 12, no_realistic_matches: false },
    counting_unverified: false,
    deltas: [],
    sliders: [
      { key: 'age', label: 'Age', unit: 'yrs', min: 18, max: 70, step: 1, current: [27, 36], suggested: [26, 38], self_value: 30, ignored: false, delta_if_ignored: 2 },
      { key: 'distance_km', label: 'Distance', unit: 'km', min: 0, max: 1600, step: 10, current: [0, 40], suggested: null, self_value: null, ignored: false, delta_if_ignored: 4 },
    ],
    filters: [
      { name: 'nationality', label: 'Nationality', on_label: 'IN, NRI', kind: 'lever', basic: true, control: 'choice', ignored: false, value: ['IN', 'NRI'], delta_if_ignored: 1, sensitive: true, blurb: '' },
      { name: 'veg_only', label: 'Diet', on_label: 'Vegetarian only', kind: 'dealbreaker', basic: true, control: 'choice', ignored: false, value: true, delta_if_ignored: 3, sensitive: false, blurb: '' },
    ],
  };

  let week = {
    clock: { mode: 'simulation', week: 1, day: 'Mon', hour: 12 },
    phase: 'match_1', mode: 'dating', prepared: true,
    prepare_request: { method: 'POST', path: '/api/v1/week/prepare', body: {} },
    schedule: { grid: { days: [], rows: [{ key: 'reveal', label: 'Reveals', days: [{ day: 'Mon', is_today: true, moments: [{ key: 'm1', at: ['Mon', 12], label: 'Match 1 reveals', tone: 'neutral', kind: 'reveal', means: 'reveal', hour: 12, day: 'Mon', past: false, time: '12:00' }] }] }], midday_after: 'Wed', midday_label: 'Midweek' }, legend: [] },
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
    if (path.endsWith('/profile')) return ok({stats:{age:30,city:'Bangalore',profession:'Engineering',diet:'Vegetarian'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});

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

    if (path.endsWith('/reach') && method === 'GET') return ok(reach);
    if (path.endsWith('/reach/widen')) {
      const slider = reach.sliders.find((s) => s.key === body.lever);
      if (slider) slider.current = [Math.max(slider.min, slider.current[0] - 2), Math.min(slider.max, slider.current[1] + 2)];
      return ok(reach);
    }
    if (path.endsWith('/reach/ignore')) {
      const filter = reach.filters.find((f) => f.name === body.filter);
      if (filter) filter.ignored = !!body.ignore;
      return ok(reach);
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
