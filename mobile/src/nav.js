// Stack/tab navigation shell (mobile-journey-build-spec.md §1). This file
// has no knowledge of what any screen shows — only the mechanics of moving
// between them. Screens are always identified by a `surface` key from the
// server's own journey/status `surfaces[]`/`next_action.destination`
// (api_contract.py's Surface shape); this module never invents one.

// Client-side chrome only: a human label per known key, and which keys earn
// a permanent tab. Never eligibility, never blocked-reason text, never a
// request path — those always come from the server's own surfaces[] on
// every render (§1: "Derive navigation from it — never infer stage
// client-side"). Mirrors disclosure.py's own nav/non-nav split, which is an
// information-architecture choice every client makes for itself, not a
// domain fact that could drift out of sync with the backend.
export const SURFACE_LABELS = {
  dashboard: 'Dashboard', verify: 'Verify', vision: 'Vision', chemistry: 'Chemistry',
  stats: 'Stats', reach: 'REACH', week: 'Week', guru: 'Guru',
  relationship: 'Relationship', journey: 'Journey', married: 'Journey',
  align: 'Before the date', calendar: 'Calendar', plan: 'Date plan',
  boundaries: 'Boundaries', debrief: 'Debrief', ceremony: 'Ceremony',
  after_date: 'After the date', expectations: 'Expectations', escalations: 'Sharing',
  next_level: 'Next level', gate: 'Relationship gate', vibes: 'Vibes', road: 'ROAD',
};
// round3-fixes-spec.md §2: the standalone Stats screen/tab is gone — the
// Dashboard shows and edits stats inline, and REACH links into the same
// inline editor for a missing filter's stat. Nothing routes to 'stats'
// any more.
export const TAB_KEYS = ['dashboard', 'reach', 'week', 'guru', 'vision', 'chemistry', 'relationship', 'journey', 'verify'];

export function labelFor(key) { return SURFACE_LABELS[key] || key; }

// Pure and DOM-free on purpose: which tabs to show is entirely "which
// TAB_KEYS does the server currently mark eligible" — e.g. REACH sunsets at
// lock-in (§2.1) simply because the server stops marking it eligible, no
// separate client-side rule to keep in sync or to test against the wrong
// thing. Order follows TAB_KEYS, not surfaces[]'s order.
export function visibleTabs(surfaces) {
  const byKey = new Map((surfaces || []).map((s) => [s.key, s]));
  return TAB_KEYS.filter((key) => byKey.get(key)?.eligible).map((key) => ({ key, label: labelFor(key) }));
}

export function createNav(onChange) {
  let stack = [{ key: 'dashboard' }];
  return {
    get current() { return stack[stack.length - 1]; },
    get depth() { return stack.length; },
    push(key, params) {
      stack.push(params ? { key, params } : { key });
      onChange();
    },
    pop() {
      if (stack.length <= 1) return false;
      stack.pop();
      onChange();
      return true;
    },
    resetTo(key) {
      stack = [{ key }];
      onChange();
    },
  };
}

// Only registers on a native platform — there is no hardware back button in
// the browser preview, and @capacitor/app's web shim has nothing to fire.
export async function wireHardwareBack(native, nav, onExitAttempt) {
  if (!native) return;
  const { App } = await import('@capacitor/app');
  App.addListener('backButton', () => {
    if (!nav.pop()) onExitAttempt();
  });
}

// Inputs must not be obscured by the on-screen keyboard (§1). A short delay
// lets the keyboard's own show animation finish before we scroll.
export function wireKeyboardScroll() {
  document.addEventListener('focusin', (e) => {
    if (e.target.matches('input,textarea,select')) {
      setTimeout(() => e.target.scrollIntoView({ block: 'center', behavior: 'smooth' }), 300);
    }
  });
}
