// perf-worker (DHASHU_ASYNC_GURU): when Guru answers on the worker, the app shows
// "Guru is thinking…", polls the owner-only job status, and then reloads the
// conversation. If the reply is not ready in time (or the status cannot be read),
// it asks the server to settle the message in guided mode — the member always gets
// an answer, and a late AI reply is never stored twice (the server's job no-ops).
export async function waitForReply(session, pendingJob, {timeoutMs = 25000, intervalMs = 1500,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)), now = () => Date.now()} = {}) {
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    await sleep(intervalMs);
    let status;
    try { status = await session.get(`/api/v1/jobs/${encodeURIComponent(pendingJob.job_id)}`); }
    catch { break; }                                   // cannot read the status: settle below
    if (status?.done) return session.get('/api/v1/guru/state');
  }
  return session.post('/api/v1/guru/private', {action: 'settle_pending'});
}
