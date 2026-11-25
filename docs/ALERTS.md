# Alerts

The code emits alert events through `alerts.emit()` (`alerts.py`). Each event is:
- one structured log line `{"alert": "<event>", ...}` on the `dhashu.alert` logger (WARNING), and
- when `SENTRY_DSN` is set, a Sentry message `alert:<event>` with the fields as tags.

Fields are counts, provider names and ids only, never personal data. Each event (per provider) fires at most once per `DHASHU_ALERT_COOLDOWN_SECONDS` (300 s) per process.

| Event | Emitted when | Fields | Respond by |
|---|---|---|---|
| `server_error_spike` | ≥ `DHASHU_ALERT_5XX_PER_MINUTE` (20) responses with 5xx in 60 s, in one process | `count_last_minute` | Open Sentry issues and the Railway logs (search the `request_id`). Roll back if it started with a deploy. |
| `circuit_open` | A provider breaker opened after 5 consecutive outage failures | `provider` (`twilio`, `msg91`, `signzy`, `openai`, `openai-images`, `razorpay`, `digilocker-files`) | Check the provider's status page. The app is already failing fast and degrading gracefully. |
| `otp_provider_down` | The breaker for `twilio` or `msg91` opened. **Members can't get sign-in codes.** | `provider` | Check the provider, or switch `DHASHU_SMS_PROVIDER` to the other provider if it's configured. |
| `stuck_verification_jobs` | BGV requests or provider jobs have been running longer than `DHASHU_ALERT_STUCK_MINUTES` (15). Checked by the worker every 5 minutes. | `count`, `minutes` | Check that the bgv-worker service is running, and look in its logs for `dead-lettered`. |
| `payment_webhook_failure` | Integration point. The billing webhook should call `alerts.emit('payment_webhook_failure', reason=...)` (sec-pay owners). | `reason` | Check Razorpay webhook deliveries. |
| `abuse_spike` | Request-abuse protection saw a burst of rejected requests (c-api-abuse) | `count`, `kind` | Check the source in Cloudflare and tighten rate limits. |

## Manual step: Sentry alert rules (after the DSN is set)

Sentry → **Alerts** → **Create Alert** → **Issues**:

1. **Errors:** "A new issue is created" OR "The issue is seen more than **10** times in **5 minutes**". Environment `production` → notify **#dhashu-alerts** (Slack integration) and email the owner.
2. **Alert events:** "An event's **message** contains `alert:`" → notify **#dhashu-alerts**. Add a second rule for `alert:otp_provider_down` with **Urgent** priority (it blocks sign-in).
3. **Regression:** "The issue changes state from resolved to unresolved" → notify **#dhashu-alerts**.
4. Performance (optional, needs `SENTRY_TRACES_SAMPLE_RATE` > 0): "p95(transaction.duration) > **500 ms** for 10 minutes".

**Slack:** Sentry → Settings → Integrations → **Slack** → Add Workspace, then choose the channel in each rule above.
