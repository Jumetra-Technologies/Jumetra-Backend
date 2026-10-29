# Accounts API

What the website calls for sign-in and the signed-in person's own data. The
request and response shapes are the ones `lib/api-client.ts`,
`lib/auth-store.ts` and `docs/accounts-and-profile.md` in jumetra-frontend use.

## Sign-in

| Route | Body | Answer |
| --- | --- | --- |
| `GET /auth/config` | | Firebase web config for the sign-in popup. `503` until Firebase credentials are set up on the server. |
| `POST /auth/google` | `{ id_token }` (Firebase ID token) | A session: `access_token`, `refresh_token`, `token_type`, and the user (both flattened and under `user`). |
| `POST /auth/github` | `{ id_token }` | Same. The token must have signed in with `github.com`. |
| `POST /auth/link-provider` | `{ id_token, provider }` + bearer | Attaches the provider to the signed-in account. `409` if the provider identity belongs to another account or the Firebase UID differs. |
| `POST /auth/refresh` | `{ refresh_token }`, `X-Refresh-Token` or the cookie | A new session. The old refresh token stops working. |
| `POST /auth/logout` | bearer or refresh token | Revokes every session of the account. |
| `POST /auth/ws-ticket` | bearer | `{ ticket, expires_in: 30 }` for a WebSocket. |

Account continuity, in order: the provider identity, the Firebase UID, then a
verified email. An unverified email never merges into an existing account; a
sign-in whose unverified email is already taken answers `409` and tells the
person to sign in the way they did before and connect the provider from their
profile.

## The person

| Route | Body | Answer |
| --- | --- | --- |
| `GET /auth/me` | bearer | The user: `id`, `email`, `email_verified`, `display_name`, `picture_url`, `auth_provider`, `linked_providers`, `role`, `role_other`, `profile_complete`, `platform_role`, `organization`, `location`, `bio`. |
| `PATCH /auth/me` | any subset of `display_name`, `role`, `role_other`, `organization`, `location`, `bio` | The full user. `422` on validation errors. `email` and `picture_url` aren't editable. |
| `DELETE /auth/me` | bearer | `204`. The account and everything under it are gone; its tokens stop working. |
| `GET /auth/users/search?q=` | bearer | Up to 10 people who have signed in, whose name or email starts with `q` (2+ characters): `{ id, display_name, email }`. |

`role` is what the person says they are (`student`, `researcher`,
`technician`, `instructor`, `club_lead`, `school_admin`, `hobbyist`, `other`).
`platform_role` is the permission the server grants (`ADMIN`, `RESEARCHER`,
`TEACHER`, `STUDENT`, `VIEWER`) and can't be changed through this API.

## The person's data

The owner is always the signed-in person. Another person's record answers `404`.

| Route | Answer |
| --- | --- |
| `GET /auth/me/projects` | `[project]`, newest first |
| `POST /auth/me/projects` | `201` with the project |
| `GET`, `PUT`, `DELETE /auth/me/projects/{id}` | the project; `{ deleted: true }` |
| `GET`, `POST /auth/me/projects/{id}/experiments` | the journal entries; `201` |
| `PUT`, `DELETE /auth/me/projects/{id}/experiments/{record_id}` | the entry; `{ deleted: true }` |
| `GET`, `PUT /auth/me/learning-progress` | `{ completed: [moduleId] }`, deduplicated and sorted |
| `GET /auth/me/lab-sessions` | the full `LabSession` documents |
| `PUT /auth/me/lab-sessions/{id}` | the saved document. A newer server `updatedAt` wins over an older client copy. `413` over 700,000 bytes. |
| `DELETE /auth/me/lab-sessions/{id}` | `{ deleted: true }` |

A project: `id`, `owner_id`, `name`, `description`, `objectives`,
`contributors`, `category`, `hardware[]`, `teammates[{ id, display_name, email }]`,
`created_at`, `updated_at`. An experiment: `id`, `project_id`, `title`,
`objective`, `hardware[]`, `procedure`, `observations`, `results`, `notes`,
`created_at`, `updated_at`.

## Running without Firebase

The server starts without Firebase credentials. Sign-in routes answer `503`
until `FIREBASE_CREDENTIALS` (or `credentials/firebase-adminsdk.json`) is in
place; everything else works, and the tests replace the token verifier.
