# Admin portal

The website's admin portal shows what's happening across Kiungo: how many
accounts and projects there are, how long each account spends in Kiungo on
the website and the desktop app, which pages get used, and who is online now.

## Getting in

Click the Kiungo logo at the top left eight times. A password box opens; the
right password opens `/admin` on the website for 30 minutes.

The password is checked by this server (`POST /admin/session`), never by the
website, whose code anyone can read. What's stored is a scrypt hash:
`HHIP_ADMIN_PASSWORD_HASH` when it's set, otherwise `DEFAULT_HASH` in
`api/services/admin_auth.py`.

**To change the password**, run

```bash
python -m api.services.admin_auth 'the new password'
```

and set `HHIP_ADMIN_PASSWORD_HASH` to what it prints. Do it on production
before sharing the portal with anyone: the default hash is in this repository.

- Five wrong passwords from one address, or 30 from everywhere, in 15 minutes
  lock sign-in for that address (or everyone) until the oldest of them is 15
  minutes old. The server answers 429 with `Retry-After`.
- Every try, right or wrong, is recorded (time, and a keyed hash of the address,
  never the address) and the portal lists the last 12.
- The token is not an account token: it opens `/admin/*` only, account routes
  refuse it, and account tokens don't open the portal. Signing out
  (`DELETE /admin/session`) ends it at once.
- Responses are `Cache-Control: no-store`.

## Where the figures come from

`POST /telemetry/heartbeat`, sent by:

| Client | When | Page |
| --- | --- | --- |
| Website | on each page, then every 30 s while the tab is visible and the person moved, typed or scrolled in the last 5 minutes; a last one (`navigator.sendBeacon`) when the tab closes | the path, ids replaced with `:id` |
| Desktop app | every 60 s while its window is shown and the computer has had input in the last 5 minutes, from the main process with the desktop session's token | `/desktop/home` or `/desktop/project` |

Time is credited for the gap since the previous heartbeat, at most 75 seconds,
so a window left open with nobody there adds nothing. Online means a heartbeat
in the last two minutes.

Body (JSON; `text/plain` is accepted for `sendBeacon`, at most 2 KB):

```json
{ "client": "web", "page": "/lab", "event": "view", "visitor": "random-id-the-browser-made", "app_version": "" }
```

`event` is `view` (a page opened), `beat` or `leave`. Signed in, the heartbeat
counts for the account (bearer token, the access cookie, or the refresh cookie,
read without being used up). Signed out, it counts for a keyed hash of
`visitor`. Without a token it must come from one of the website's origins.

## What's stored

| Table | What | Kept |
| --- | --- | --- |
| `activity_presence` | per person or visitor and client: the page now, when this visit started, last heartbeat | 30 days after the last heartbeat |
| `activity_daily` | seconds per person or visitor, per day (UTC), per client | 400 days |
| `activity_pages` | views and seconds per page, per day, per client | 400 days |
| `admin_sessions`, `admin_sign_in_attempts` | admin sign-ins | 90 days |

No log of what anyone did, no IP addresses, no page contents or query strings.
Deleting an account deletes its rows. Old rows are removed by the server
(every 500 heartbeats, and each time the portal loads).

## `GET /admin/overview?days=7`

`days` is 1 to 90 and sets the range for time, pages and the daily chart.

- `totals`: accounts (people who signed in with Google or GitHub; the demo
  users the platform seeds aren't counted), new accounts in the range,
  projects (the website's, plus the desktop app's synced to the account; `desktop_projects` is the second part), lab sessions, experiment records, desktop devices, online accounts
  and visitors, seconds in the range, active accounts in the range
- `online`: each account online now, with client, page and since when
- `accounts`: every account with time in the range (web and desktop), all time,
  active days, projects, lab sessions, last seen, sign-in method
- `pages`: the 20 pages with the most time in the range
- `daily`: per day, active accounts, signed-out visitors, seconds, new accounts
- `clients`: seconds on the website and the desktop app
- `admin_sign_ins`: the last 12 tries at the password
