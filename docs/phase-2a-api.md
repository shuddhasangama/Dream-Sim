# Phase 2A JSON API

The existing Flask application now also serves `/api/v1`. Gunicorn continues
using `app:app`; the Railway service and PostgreSQL schema need no changes for
this addition. Existing HTML routes and REACH business rules are reused.

## Authentication and scope

`GET /api/v1/health` is public liveness (not a database readiness check).
Every other endpoint requires an existing Flask session identifying a stored
user. Missing or stale sessions return JSON HTTP 401, without redirecting.
This phase adds no login endpoint, token authentication or CORS configuration.
The existing simulation login is not production mobile authentication; that
remains Phase 3. No deployment or production database operation is part of
this local implementation.

`me` and `profile` always describe the session's user. Query parameters cannot
select another user. Responses use explicit fields and do not include account
records, OTPs, other users, or raw database rows. Profile contains the current
stored profile statistics, onboarding visions and matching preferences; the
later journey Vision API is outside this phase.

## Endpoints

| Method | Path | Request / result |
| --- | --- | --- |
| GET | `/api/v1/health` | `status: ok`, `api_version: v1` |
| GET | `/api/v1/me` | `user_id`, `journey_state`, `bgv_status` |
| GET | `/api/v1/profile` | Identity/status plus `city`, `gender`, `age_band`, `stats`, `visions`, `preferences` |
| GET | `/api/v1/reach` | Existing recomputed REACH state |
| POST | `/api/v1/reach/ignore` | `{"filter":"age","ignore":true}` |
| POST | `/api/v1/reach/show-all` | `{"ignore":true}` |
| POST | `/api/v1/reach/widen` | `{"lever":"age"}` |
| POST | `/api/v1/reach/set-range` | `{"lever":"age","min":25,"max":40}` |

POST bodies must be JSON objects with exactly the documented fields. Booleans
must be JSON booleans; bounds must be finite JSON numbers with min <= max.
Allowed filters/levers and range adjustments remain the existing matching
module's responsibility. All successful REACH mutations return the full
recomputed REACH state. REACH reads and mutations return 403 after mutual
lock-in or in Relationship, Engaged or Married states, matching the web rules.
Verification-based pool scoping is unchanged.

## Response format

Success (HTTP 200):

```json
{"data":{"status":"ok","api_version":"v1"},"error":null}
```

Failure:

```json
{"data":null,"error":{"code":"authentication_required","message":"Sign in to continue.","detail":null,"reference":null}}
```

Statuses include 400 validation errors, 401 authentication required, 403 locked
REACH, 404 unknown path, 405 unsupported method, 415 non-JSON request and 500
unexpected failure. Unexpected failures use the existing incident logging and
reference-code mechanism, without returning exception details. Method errors
include `Allow`. API responses set `Cache-Control: no-store`.

The `/api/v1` response wrapper also covers unknown routes and application error
handlers. Other routes retain their existing response formats.

## Validation

`python -m pytest test_api.py -q` covers authentication, privacy allowlists,
REACH parity/persistence, verification scoping, lock-in/stage guards, malformed
requests without mutation, routing errors, and incident handling.

`python -m pytest -q` runs the complete regression suite. These local tests do
not establish live Railway/PostgreSQL deployment health. After an approved
code deployment, check `/api/v1/health` and authenticated API/web behavior in
the deployed environment. No schema migration is needed for Phase 2A.
