# Crash reports and consent

The desktop app sends a crash report only when the person said yes. It asks once and keeps the answer on the computer; a signed-in person's answer is also kept on their account, so it follows them.

## Tables (migration `0004_consents`)

- `consents`: one row per account that has answered. `crash_reports` (yes or no), `decided_at`, `decided_in` ("desktop 0.6.0"). No row: not asked yet.
- `crash_reports`: `install_id` (random per installation), `user_id` (only if signed in), `app_version`, `platform`, `arch`, `process`, `message`, `stack`, `occurred_at`, `received_at`. Never sketches, projects or file contents. Kept 90 days: older rows are deleted on each new report.

## Routes

- `GET /auth/me/consents` → `{ crash_reports: true | false | null, decided_at, decided_in }`
- `PUT /auth/me/consents` `{ crash_reports, decided_in }`. Saying no also deletes the reports sent under that account.
- `POST /crash-reports` (signed in or not) with `consent: true` in the body, 202. Refused with 403 when it carries the session of an account that said no.

## Sign-in middleware change (for review)

Writes need a signed-in session and, until now, a website `Origin` on every request. The origin check is there to stop other websites using the browser's cookies (CSRF). The desktop app sends a bearer token and no `Origin`, so its writes were refused. A browser only sends an `Authorization` header cross-site after a CORS preflight, which only allowed origins pass, so a request with a bearer token can't be forged that way. Such requests now skip the origin check; they still need a valid session. Cookie requests are checked as before (`tests/test_crash_reports.py` covers both).

`/crash-reports` (signed-out reports with consent) and `/releases` (the pipeline's token) check their own credentials and pass through the middleware.
