# Signzy error recovery

Prepared 6 November 2026. Deploy both Dream-Sim and bgv-worker from the same release. Startup applies the additive SignzyGuard table in SQLite/PostgreSQL; do not manually reset existing user/check tables. No new Railway variables are required. Both services must use the same database and the same Signzy environment/credential for a shared pause.

## Behaviour

- Wallet exhaustion, ambiguous HTTP 402, and authentication failure pause all Signzy calls for that credential/environment. Raw credentials are never stored in the guard; a SHA-256 fingerprint scopes it.
- API access denial pauses only the affected operation. Rate limiting pauses that operation for 60 seconds; provider 5xx for five minutes. Timed expiry releases only unsent queued work, not attempted requests.
- Validation errors, no-record responses, malformed responses and uncertain transport outcomes have distinct action messages. They do not imply an identity mismatch or legal finding. An error envelope overrides apparent success fields, even with HTTP 200/202.
- Claimed paid attempts are not automatically replayed. A pause is checked before worker claims; an additional pre-send check handles pauses observed after claim. A request caught at that second check gets local evidence `provider_request_sent=false` and is held for manual handling; it is not requeued automatically.
- Calls already in flight when another worker detects a fault cannot be cancelled. This is not a guarantee that zero concurrent requests reach Signzy during an outage.
- Existing session ownership, consent, cooldowns and duplicate protections remain in place. No automatic identity/account approval is added.
- There is no new alert delivery or reviewer dashboard. The operator must inspect the status command and encrypted provider evidence. User-facing messages say contact support; they do not claim that support was notified.
- OpenAI avatar errors and Razorpay payment errors use their existing separate workflows. This guard controls Signzy only.

## Inspect in Railway Dream-Sim console

```bash
cd /app && /app/.venv/bin/python signzy_guard_admin.py status
```

The output shows environment, operation (`*` means all operations for the account), classification, active flag and pause expiry. `paused_until=0` means manual recovery is required; timed expired rows can remain active in the audit table but no longer block dispatch.

## Recover after fixing the provider issue

1. Check Signzy logs and billing for the attempted request. Top up the wallet, correct credentials or have the affected product enabled as appropriate.
2. Confirm the configured sandbox/production environment; do not switch environments to bypass a failed check.
3. Clear the exact scope reported by status. First run without `--apply` for a dry run.

```bash
cd /app && /app/.venv/bin/python signzy_guard_admin.py resume --operation '*' --reason 'Wallet topped up and provider billing reconciled' --apply
```

For product-only denial, replace `*` with the reported operation, for example `fir_search`, `individual_result`, `employment_history`, `digilocker_create_url`, `digilocker_eaadhaar`, `digilocker_details`, `liveness_secure_create`, `liveness_secure_data` or `face_match`.

4. Existing workers may continue unsent queued jobs. Do not change failed/unknown rows to queued, reset allowances or generate new paid IDs indiscriminately. Reconcile each attempted request first and use an explicitly approved recovery path.
5. Read the member status again. Confirm no failed attempt was silently replayed and the result belongs to the same user/session/search.

Credential rotation produces a different scope. Check the old key's provider logs/billing before allowing new work; the status CLI intentionally displays only the currently configured credential scope. Recovery reasons must contain no personal details or secrets.

## Release validation

Tests use synthetic local responses only; no paid requests, live credentials or user identity documents are consumed. Live wallet exhaustion is not deliberately triggered. After deployment, inspect status and complete a normal consented sandbox E2E test; deployment and production entitlement are not established by unit tests.
