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
        {key:'verify',eligible:false,blocked_reason:'You are already verified.',api_available:false,request:null},
        {key:'relationship',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
        {key:'journey',eligible:false,blocked_reason:'This opens once you have both agreed to be exclusive.',api_available:false,request:null},
      ],
      next_action:{headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.',cta:'See this week',
        destination:{key:'week',eligible:true,blocked_reason:null,api_available:true,request:{method:'GET',path:'/api/v1/week'}}},
    });
    if (path.endsWith('/profile')) return ok({stats:{age:30,city:'Bangalore',profession:'Engineering',diet:'Vegetarian'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});

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
      }
      return ok({ match_id: id, action: body.action, replayed: false });
    }

    throw new Error('Unsupported preview request: '+method+' '+path);
  };
}
