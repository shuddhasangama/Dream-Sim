// Height in both units (client answer 6, 2026-11-27). Stored once, as whole cm
// (stats height_cm). Entered and shown in cm and feet/inches. Feet/inches are
// converted to cm (nearest cm) and checked against the same cm range, so validation
// is identical in both units. Same numbers as height_units.py on the server.
export const CM_PER_INCH = 2.54;
export const MIN_CM = 140, MAX_CM = 210;

export function ftInToCm(feet, inches = 0) { return Math.round((Number(feet) * 12 + Number(inches)) * CM_PER_INCH); }

export function cmToFtIn(cm) {
  const total = Math.round(Number(cm) / CM_PER_INCH);
  return [Math.floor(total / 12), total % 12];
}

export function ftInLabel(cm) { const [f, i] = cmToFtIn(cm); return `${f}′ ${i}″`; }

export function heightLabel(cm) {
  if (cm === null || cm === undefined || cm === '' || !Number.isFinite(Number(cm))) return '';
  return `${Math.round(Number(cm))} cm (${ftInLabel(cm)})`;
}

export function ftInRange(low = MIN_CM, high = MAX_CM) {
  const ok = [];
  for (let n = 36; n < 100; n++) { const cm = Math.round(n * CM_PER_INCH); if (cm >= low && cm <= high) ok.push(n); }
  return [[Math.floor(ok[0] / 12), ok[0] % 12], [Math.floor(ok[ok.length - 1] / 12), ok[ok.length - 1] % 12]];
}

export function rangeText(low = MIN_CM, high = MAX_CM) {
  const [[f1, i1], [f2, i2]] = ftInRange(low, high);
  return `${low}–${high} cm (${f1}′ ${i1}″–${f2}′ ${i2}″)`;
}

// {cm, error} from the three inputs' raw values; cm wins when it is filled in.
export function readHeight({cm = '', ft = '', inch = ''} = {}, low = MIN_CM, high = MAX_CM) {
  const c = String(cm ?? '').trim(), f = String(ft ?? '').trim(), i = String(inch ?? '').trim();
  let value;
  if (c) {
    value = Number(c);
    if (!Number.isFinite(value) || !Number.isInteger(value)) return {cm: null, error: 'Height must be a whole number of centimetres.'};
  } else if (f || i) {
    const feet = Number(f || 0), inches = Number(i || 0);
    if (!Number.isInteger(feet) || !Number.isInteger(inches) || feet < 0) return {cm: null, error: 'Height in feet and inches must be whole numbers.'};
    if (inches < 0 || inches > 11) return {cm: null, error: 'Inches must be from 0 to 11.'};
    value = ftInToCm(feet, inches);
  } else return {cm: null, error: null};
  if (value < low || value > high) return {cm: null, error: `Height must be between ${rangeText(low, high)}.`};
  return {cm: value, error: null};
}

// The two extra inputs shown next to a height_cm input (names never sent to the server).
export function ftInInputs(cm, safe, prefix = '') {
  const [f, i] = (cm === null || cm === undefined || cm === '') ? ['', ''] : cmToFtIn(cm);
  return `<span class="height-ftin"><input type="number" inputmode="numeric" name="${prefix}height_ft" min="4" max="7" value="${safe(f)}" aria-label="Height, feet" placeholder="ft">
    <input type="number" inputmode="numeric" name="${prefix}height_in" min="0" max="11" value="${safe(i)}" aria-label="Height, inches" placeholder="in"></span>`;
}

// Keep cm and feet/inches in step while typing, anywhere under root (one delegated listener).
export function installHeightSync(root) {
  if (!root || root.__heightSync) return;
  root.__heightSync = true;
  root.addEventListener('input', (event) => {
    const name = event.target?.name || '';
    const m = name.match(/^(.*)height_(cm|ft|in)$/);
    if (!m) return;
    const form = event.target.form || root;
    const field = (k) => form.querySelector(`[name="${m[1]}height_${k}"]`);
    const cm = field('cm'), ft = field('ft'), inch = field('in');
    if (!cm || !ft || !inch) return;
    if (m[2] === 'cm') {
      if (cm.value.trim() === '') { ft.value = ''; inch.value = ''; return; }
      const [f, i] = cmToFtIn(cm.value); ft.value = String(f); inch.value = String(i);
    } else if (ft.value.trim() !== '' || inch.value.trim() !== '') {
      cm.value = String(ftInToCm(ft.value || 0, inch.value || 0));
    }
  });
}
