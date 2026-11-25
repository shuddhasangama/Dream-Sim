// vis-chem: warn before leaving a screen with unsaved changes. A screen arms the
// guard with a function that says whether it is dirty; navigation asks first.
let isDirty = null;
let ask = (message) => window.confirm(message);

export const MESSAGE = 'You have unsaved changes. Leave without saving?';

export function arm(dirtyFn) { isDirty = dirtyFn; }
export function disarm() { isDirty = null; }

// true = go ahead (nothing unsaved, or the member chose to leave).
export function confirmLeave() {
  if (!isDirty || !isDirty()) return true;
  if (!ask(MESSAGE)) return false;
  isDirty = null;
  return true;
}

export function dirty() { return !!(isDirty && isDirty()); }

// Tests only: replace the confirm dialog.
export function setAsk(fn) { ask = fn; }

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (event) => {
    if (dirty()) { event.preventDefault(); event.returnValue = MESSAGE; }
  });
}
