export const TEST_TIMETABLE = [
  ['0', 'Monday 10:00', 'REACH / Reality Check'],
  ['3', 'Monday 12:00', 'Match 1 opens'],
  ['6', 'Tuesday 12:00', 'M1 closes · Match 2 opens'],
  ['9', 'Wednesday 12:00', 'M2 closes · Match 3 opens'],
  ['12', 'Wednesday 18:00', 'M3 closes · share weekend Slots'],
  ['15', 'Thursday 12:00', 'Calendar closes · overlap / plan selection'],
  ['18', 'Thursday 18:00', 'Review and sign the agreement'],
  ['21', 'Selected date start*', 'Meet · time rounded up if needed'],
  ['24', 'Date’s Debrief opening*', 'Share flags and your decision'],
  ['27', 'Sunday 21:00', 'Reality Check, if your lock-in has ended'],
  ['30', 'Next Monday 12:00', 'Cross RC close at 11:00 · next cycle'],
];

export function timetable(safe) {
  return `<div class="timetable-scroll"><table class="test-timetable"><caption>Accelerated testing timetable · real elapsed minutes</caption>
    <thead><tr><th>Minutes</th><th>Jump to</th><th>What to do</th></tr></thead>
    <tbody>${TEST_TIMETABLE.map(row=>`<tr>${row.map(v=>`<td>${safe(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    <p class="hint">*The shared test clock uses the latest saved weekend date across the test environment, so all partners stay on the same clock. Without a plan, these two checkpoints remain at Thursday 18:00. Debrief opens only for an eligible date.</p>
    <p class="hint">The timetable runs only when your test administrator enables it. It stops at the next Monday. Your choices, consent and signatures are never automated.</p>`;
}

export function howItWorks(safe) {
  return `<details class="card how-it-works"><summary><strong>How it works · watch the walkthrough</strong></summary>
    <p>Sign up with your invited number, review your profile, then follow REACH → Week → Calendar → Agreement → Debrief.</p>
    <video controls playsinline preload="none" aria-label="DhaShu how it works walkthrough">
      <source data-src="/media/how-it-works.mp4" type="video/mp4">
      <track kind="captions" data-src="/media/how-it-works.vtt" srclang="en" label="English">
      Your device cannot play this video.</video>
    <p class="hint video-error" hidden>Video unavailable. The timetable below is still available.</p>
    ${timetable(safe)}</details>`;
}

export function bindHowItWorks(root) {
  root.querySelectorAll('.how-it-works video').forEach(video=>{
    video.closest('details').addEventListener('toggle',event=>{
      if(!event.target.open) { video.pause(); return; }
      if(video.querySelector('source').hasAttribute('src')) return;
      video.poster='/media/how-it-works-poster.jpg';
      video.querySelectorAll('[data-src]').forEach(node=>{node.src=node.dataset.src;});
      video.load();
    });
    const failed = ()=>{ video.parentElement.querySelector('.video-error').hidden = false; };
    video.addEventListener('error', failed);
    video.querySelector('source')?.addEventListener('error', failed);
  });
}
