export class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.status = status; }
}

// No automatic mutation retries. Refresh is serialized; a lost response requires
// OTP again because replaying a consumed refresh credential revokes its family.
export class Session {
  constructor(send, vault, now = () => Date.now()) {
    this.send = send; this.vault = vault; this.now = now;
    this.tokens = null; this.flight = null; this.generation = 0;
  }
  async raw(path, method = 'GET', body, token) {
    if (!/^\/api\/v1\/[a-zA-Z0-9/_-]+$/.test(path)) throw new ApiError('Invalid API path.');
    let response;
    try { response = await this.send(path, method, body, token); }
    catch { throw new ApiError('Connection unavailable. Check your internet and try again.'); }
    const envelope = response.data;
    if (response.status < 200 || response.status >= 300) {
      throw new ApiError(envelope?.error?.message || 'Request could not be completed.', response.status);
    }
    if (!envelope || envelope.error !== null || !envelope.data) throw new ApiError('Unexpected server response.');
    return envelope.data;
  }
  async requestCode(destination) {
    if (!/^\+[1-9]\d{7,14}$/.test(destination)) throw new ApiError('Include the country code, for example +91 followed by your number.');
    return this.raw('/api/v1/auth/request', 'POST', {channel: 'phone', destination});
  }
  async verify(challenge_id, code) {
    if (!/^\d{4,10}$/.test(code)) throw new ApiError('Enter the code from your SMS.');
    const epoch = this.generation;
    const result = await this.raw('/api/v1/auth/verify', 'POST', {challenge_id, code});
    await this.accept(result, epoch);
  }
  async accept(value, epoch) {
    if (typeof value.access_token !== 'string' || typeof value.refresh_token !== 'string' || !Number.isFinite(value.expires_in)) throw new ApiError('Invalid sign-in response.');
    if (epoch !== this.generation) throw new ApiError('Sign-in was cancelled.');
    await this.vault.write(value.refresh_token);
    if (epoch !== this.generation) { await this.vault.clear(); throw new ApiError('Sign-in was cancelled.'); }
    this.tokens = {...value, expiresAt: this.now() + value.expires_in * 1000};
  }
  async restore() {
    const stored = await this.vault.read();
    if (!stored) return false;
    await this.refresh(stored); return true;
  }
  async refresh(stored) {
    if (this.flight) return this.flight;
    const epoch = this.generation;
    const refreshToken = stored || this.tokens?.refresh_token;
    this.flight = (async () => {
      try {
        if (!refreshToken) throw new ApiError('Please sign in again.', 401);
        this.tokens = null;
        await this.vault.clear();
        const result = await this.raw('/api/v1/auth/refresh', 'POST', {refresh_token: refreshToken});
        await this.accept(result, epoch);
      } catch (e) {
        this.tokens = null; await this.vault.clear();
        throw new ApiError('Your session could not be renewed. Please sign in again.', e.status || 401);
      } finally { this.flight = null; }
    })();
    return this.flight;
  }
  async get(path) {
    if (this.flight) await this.flight;
    if (!this.tokens) throw new ApiError('Please sign in.', 401);
    if (this.tokens.expiresAt < this.now() + 30000) await this.refresh();
    try { return await this.raw(path, 'GET', undefined, this.tokens.access_token); }
    catch (e) {
      if (e.status === 401) { this.tokens = null; await this.vault.clear(); }
      throw e;
    }
  }
  async logout() {
    // Do not race logout against a pending rotation or permit it to resurrect UI.
    if (this.flight) { try { await this.flight; } catch {} }
    const token = this.tokens?.access_token;
    this.generation++; this.tokens = null;
    await this.vault.clear();
    if (token) {
      try { await this.raw('/api/v1/auth/logout', 'POST', {}, token); }
      catch (e) { if (e.status !== 401) return false; }
    }
    return true;
  }
}
