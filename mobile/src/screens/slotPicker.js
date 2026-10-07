const meals={breakfast:'Breakfast',lunch:'Lunch',coffee:'Coffee',dinner:'Dinner'};
export function slotPicker(valid, selected, safe, disabled=false) {
 const choices=new Set(selected.map(s=>`${s.day}|${s.meal_slot}`));
 const allowed=new Set(valid.map(s=>`${s.day}|${s.meal_slot}`));
 return `<div class="weekend-grid" role="group" aria-label="Your weekend availability"><span></span>${['Fri','Sat','Sun'].map(d=>`<strong>${d}</strong>`).join('')}${Object.entries(meals).map(([m,label])=>`<strong>${label}</strong>${['Fri','Sat','Sun'].map(d=>allowed.has(`${d}|${m}`)?`<label class="slot-choice"><input type="checkbox" name="slot" value="${safe(d)}|${safe(m)}" aria-label="${d} ${label}" ${choices.has(`${d}|${m}`)?'checked':''} ${disabled?'disabled':''}><span aria-hidden="true">✓</span></label>`:'<span class="slot-unavailable" aria-label="Not available">—</span>').join('')}`).join('')}</div>`;
}
