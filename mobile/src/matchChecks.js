// Server supplies only consented statuses/dates, never private evidence.
export function render(summary,safe){
 if(!summary?.shared)return '<section class="match-checks"><h3>Verification</h3><p class="hint">Verification summary not shared.</p></section>';
 return `<section class="match-checks"><h3>Verification</h3>${summary.sandbox?'<p class="hint">Sandbox results · test environment</p>':''}<ul>${(summary.checks||[]).map(c=>`<li><strong>${safe(c.label)}</strong><span>${safe(c.status_label)}${c.checked_on?` · Checked on ${safe(c.checked_on)}`:''}</span></li>`).join('')}</ul><p class="hint">These are dated check results. Employment history does not confirm current employment. Choose Like or Pass below.</p></section>`;
}
