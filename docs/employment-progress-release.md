# Employment progress release

Release checkout: C:/DreamContractLocalBKP/ChatGPT/dhashu-employment-release
Base: origin/master d62a86d8. Do not deploy the stale dhashu-phase2 checkout for this change.

## Important reconciliation
The latest GitHub code already maps the app current_employer check to Signzy employment_history. It accepts DigiLocker PAN or a verified account mobile and checks returned names against Aadhaar. This release retains that implementation and provider guards; it removes the employer-declaration prerequisite. The older local current-employer-only implementation must not overwrite it.

## Owner view
Your verification > Current employer shows the latest returned employment record, company name and joining/exit dates when available, with a separate receipt date. An open employment-history record is not proof of current employment. The response may lag the user's actual latest job. No manual user confirmation button is included.
Employment details and the employment-status badge are omitted from match-facing verification responses. Internal pre-existing REACH filtering is unchanged. Authorised support access remains available.

## Progress
New verification decisions persist verified_at and field_verified_at; identity receipt dates remain separately labelled. Existing records without known dates are not assigned fabricated historical dates. Pending calls are not blindly retried; ten-minute stale processing is labelled for support reconciliation. Completed searches/results remain saved. Worker iteration failures are logged by type and do not stop its loop.

## Deploy
1. Commit only the files listed by git status in this isolated checkout, then push HEAD:master. Never force push. If rejected, fetch/rebase and resolve before deployment.
2. Railway Dream-Sim and bgv-worker must both deploy that commit from master, using the same database and existing encryption key. Keep preproduction settings. No variable change or new schema migration is required by this patch.
3. The running worker schedules previously missing eligible employment checks using saved consent. This can consume sandbox credits. Do not reset the user or rerun completed checks.
4. Build master in Codemagic for Android and iOS; install the updated test builds to see the UI changes.
5. Check Your verification on the owner account. Confirm the latest employment record, source limitations and dates. Confirm the match response has no employment badge/details.
6. If no request appears, inspect the assigned policy, available identifiers, provider pause status and worker logs. Do not clear records or blindly replay paid calls.

No live provider calls or deployments were performed while preparing this release. The standalone admin dashboard is not modified.
