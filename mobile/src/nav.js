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
  boundaries: 'Boundaries', debrief: 'Debrief', ceremony: 'Ceremony', identity: 'Identity check',
  after_date: 'After the date', expectations: 'Expectations', escalations: 'Sharing',
  next_level: 'Next level', gate: 'Relationship gate', vibes: 'Vibes', road: 'ROAD',
};
// round3-fixes-spec.md §2: the standalone Stats screen/tab is gone — the
// Dashboard shows and edits stats inline, and REACH links into the same
// inline editor for a missing filter's stat. Nothing routes to 'stats'
// any more.
// round4-fixes-spec.md §2: likewise Vision and Chemistry — they are
// collapsible Dashboard sections now (see main.js FOLDS), so neither earns
// a tab.
export const TAB_KEYS = ['dashboard', 'reach', 'week', 'guru', 'relationship', 'journey', 'verify'];

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

// design_handoff_app_ui_pulse/README.md ("Pulse", option 1a): the four main
// navigations move onto a floating bottom tab bar, always exactly these
// four keys in this order — never sourced from disclosure.py's ordering,
// which is a home for many more surfaces than a phone's thumb-reach bar can
// hold. 'dashboard' shows as "Home" here only — SURFACE_LABELS keeps calling
// it "Dashboard" everywhere else (blocked/unavailable messages, generic
// screens), since that rename is purely the tab bar's own label.
export const PRIMARY_TAB_KEYS = ['dashboard', 'reach', 'week', 'guru'];
const PRIMARY_LABELS = { dashboard: 'Home', reach: 'Reach', week: 'Week', guru: 'Guru' };

export function primaryTabs(surfaces) {
  const byKey = new Map((surfaces || []).map((s) => [s.key, s]));
  return PRIMARY_TAB_KEYS.filter((key) => byKey.get(key)?.eligible).map((key) => ({ key, label: PRIMARY_LABELS[key] }));
}

// Everything else nav-worthy (Verify, Relationship, Journey — stage-gated
// surfaces the floating bar has no room for) still has to be reachable, so
// it lives behind the Home avatar's profile sheet instead of a tab. Derived
// from visibleTabs() rather than re-reading surfaces itself, so it can never
// disagree with which keys are known/eligible.
export function secondaryTabs(surfaces) {
  return visibleTabs(surfaces).filter((t) => !PRIMARY_TAB_KEYS.includes(t.key));
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
