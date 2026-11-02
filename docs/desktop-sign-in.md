# Desktop sign-in

How Kiungo 2 (the desktop app) signs in. The app never shows a Firebase
popup: the person signs in on the website, and the website hands the app a
one-time code. This is the design jumetra-frontend #62 asked for, and the
contract the Sprint 4 desktop work (DSK-01 to DSK-03) builds against.

The OpenAPI document for every route is `docs/openapi.json`
(`python scripts/export_openapi.py`).

## The flow

```text
Desktop app                           Backend                            Website (browser)
-----------                           -------                            -----------------
1. verifier = random(48 bytes)
   challenge = b64url(sha256(verifier))
   POST /auth/desktop/codes ─────────▶ desktop_auth_codes: pending
   { code_challenge, device }  ◀───── { code_id, authorize_url, expires_in: 600, poll_interval: 3 }

2. open authorize_url ───────────────────────────────────────────────────▶ /desktop/sign-in?code_id=…
                                                                           person signs in (Google or GitHub)
                                      GET  /auth/desktop/codes/{id}/details ◀── "Sign in to Kiungo on Brad's ThinkPad (Linux)?"
                                      POST /auth/desktop/codes/{id}/approve ◀── bearer
                                      status: approved, code_hash set ────▶ { redirect_url: "kiungo://signin?code=…&code_id=…" }
                                                                           browser opens kiungo://signin?code=…
3. kiungo:// handler receives code
   (or: GET /auth/desktop/codes/{id} every 3 s until status is approved; the first poll after approval carries the code once)

4. POST /auth/desktop/token ─────────▶ checks sha256(verifier) == challenge, marks the code exchanged,
   { code, code_verifier }   ◀─────── creates the device, issues tokens
                                      { access_token (15 min), refresh_token (30 days), device, user }

5. POST /auth/desktop/refresh ───────▶ rotates: old refresh token revoked, new pair issued
   POST /auth/desktop/logout  ───────▶ the device and all its tokens revoked
```

Codes expire after 10 minutes. A code can be exchanged once. A wrong
verifier marks the code `denied`, so a code stolen from a URL is useless
without the verifier the app kept in memory.

## Tables (migration `0002_desktop_sign_in`)

**`devices`**: one row per installation that completed a sign-in.

| Column | Notes |
| --- | --- |
| `id` | 32 hex |
| `user_id` | → `users.id`, cascade |
| `name` | what the app reports, e.g. the computer's hostname (≤ 120) |
| `platform` | `windows`, `linux` or `macos` |
| `app_version` | the app's version at sign-in |
| `created_at`, `last_seen_at` | `last_seen_at` moves on every refresh |
| `revoked_at` | set by logout, by the person on the website, or by a replayed refresh token |

**`desktop_auth_codes`**: one row per sign-in attempt.

| Column | Notes |
| --- | --- |
| `id` | the `code_id` the app polls with |
| `status` | `pending` → `approved` → `exchanged`; or `denied`, `expired` |
| `code_challenge`, `code_challenge_method` | PKCE, `S256` only |
| `code_hash` | sha256 of the one-time code; set on approval; unique |
| `redirect_uri` | `kiungo://signin` or a loopback `http://127.0.0.1:<port>/…` |
| `device_name`, `device_platform`, `app_version` | shown on the approval page |
| `user_id` | who approved it |
| `device_id` | the device created at exchange |
| `created_at`, `expires_at`, `approved_at`, `exchanged_at` | |

**`refresh_tokens`** gains `client` (`web` or `desktop`) and `device_id`.
**`access_tokens`** gains `device_id`, so revoking a device ends its access
tokens at once instead of after 15 minutes.

## Rules

- **Rotation.** Every desktop refresh issues a new refresh token and revokes
  the old one. Presenting a revoked desktop refresh token revokes the whole
  device: someone copied it.
- **Devices are per installation.** Signing in again from the same computer
  makes a new device row; the old one stays until it is revoked or the
  person removes it. `GET /auth/me/devices` lists them; `DELETE /auth/me/devices/{id}`
  revokes one. Web sessions are untouched by desktop revocations and the
  other way round.
- **Approval needs the website's session.** `approve`, `deny` and `details`
  require a bearer token from `/auth/google` or `/auth/github`. The app's
  own routes (`codes`, `codes/{id}`, `token`, `refresh`, `logout`) take no
  bearer and are exempt from the authenticated-write middleware.
- **Redirects.** Only `kiungo://signin` and loopback HTTP addresses are
  accepted, so an attacker can't send a code to their own site.
- **Where the sign-in page lives.** `KIUNGO_WEBSITE_URL` (default: the
  Vercel site) + `/desktop/sign-in`. The website page is Sprint 4 frontend work.

## Not in this version

- Rate limits on `codes` and `token` (sprint 4).
- `platform_role` enforcement on desktop tokens (sprint 4).
- Named devices the person can rename.
