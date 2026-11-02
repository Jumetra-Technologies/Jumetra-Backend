# Project sync API: design (Phase Two, for sprint 11)

Status: built in sprint 11 (`api/routes/projects_sync.py`, migration `0005_projects_sync`, tests in `tests/test_projects_sync.py`), as designed below. Masden reviews the tables and the storage choice. Blobs are in PostgreSQL for now (question 2).

Changes from the draft, found while building it:

- **Blobs are per owner** (`file_blobs` is keyed on owner and hash), not shared. With shared blobs, anyone who knew a file's hash could commit it into their own project and read it back. Storage is still shared between one person's projects and revisions.
- **`POST /{id}/blobs/missing`** takes `{ hashes }` and returns the ones the server doesn't have, so a push uploads only what's new.
- **`world.json` syncs** too (the robot world, sprint 8). Paths are checked against a fixed pattern: `kiungo.json`, `circuit.json`, `world.json`, `sketch/<file>`, `records/<file>` or `records/<folder>/<file>`.
- **Old content is collected:** after each commit, blobs that no current file and no kept revision use are deleted. Deleted projects are purged 30 days after deletion, the next time the list is read.

## What it's for

A desktop project is a folder (`kiungo.json`, `circuit.json`, `sketch/`, `records/`). Sync keeps a copy of it on the person's account so that:

1. it opens on their other computer,
2. it survives a lost laptop, and
3. a Phase One project or lab session on the website can come across (DSK-15).

It is not real-time collaboration. One person, several computers, sometimes offline. The folder on disk is always the working copy; the server copy is a backup and a way across.

## What exists today, and why it isn't enough

`PUT /auth/me/lab-sessions/{id}` stores one lab session as a JSON document. When two copies disagree, it keeps the one with the newer client timestamp.

That breaks for projects:

- **Clocks.** Clocks on two computers disagree. A laptop with a wrong clock silently overwrites newer work.
- **Several files.** A project is several files, and the sketch files are not JSON.
- **No conflicts.** There's no way to say "you both changed it", so one side's work is lost without anyone knowing.

## Model

```
synced_projects
  id              project id from kiungo.json (prj-…), with the owner, the key
  owner_id        users.id
  name            for lists, from kiungo.json
  board           lab part id, for lists
  revision        integer, +1 on every accepted change (the server's clock, not the computer's)
  size_bytes      total of the current files, for the quota
  deleted_at      soft delete: kept 30 days, then purged
  created_at, updated_at

synced_files
  project_id, owner_id, path    path inside the project: "kiungo.json", "sketch/sketch.ino"
  sha256                        of the content
  size_bytes
  revision                      the project revision that last changed this file

file_blobs
  sha256 (key), content (bytea), size_bytes
  Content-addressed: the same file in two projects or two revisions is stored once.

project_revisions
  project_id, owner_id, revision, device_id, created_at,
  files  JSON: [{ path, sha256 }]   the whole tree at that revision
  Keeps the last 20 revisions per project, so "restore an earlier version" is possible later.
```

What gets synced:

- **Synced:** `kiungo.json`, `circuit.json`, everything under `sketch/`, and everything under `records/`.
- **Not synced:** `.kiungo/` (undo history, local to one computer) and anything else.
- **Limits:** each file at most 2 MB; each project at most 20 MB. The default quota is 200 MB per account.

## Endpoints

All of these sit under `/auth/me/projects-sync` and take a bearer token, so the desktop app can use them (see the middleware note in docs/crash-reports.md).

| Method and path | What |
|---|---|
| `GET /` | Every project: `{ id, name, board, revision, updated_at, size_bytes, deleted }`, for Home's "on your account" list. |
| `GET /{id}` | The current tree: `{ revision, files: [{ path, sha256, size }] }`. Header `ETag: "r{revision}"`. |
| `GET /{id}/blobs/{sha256}` | One file's content. Immutable, so the client caches it forever. |
| `POST /{id}/blobs` | Upload contents the server doesn't have yet. Body: `[{ sha256, base64 }]`. The server checks each hash. Idempotent. |
| `PUT /{id}` | Commit a new tree. Header `If-Match: "r{revision}"` (the revision the client started from, or `*` to create). Body: `{ name, board, files: [{ path, sha256 }] }`. Returns 200 `{ revision }`, 409 if the server has moved on (body: the server's current tree), 412 if `If-Match` is missing, 413 over quota, or 422 if a blob is missing. |
| `DELETE /{id}` | Soft delete, with `If-Match`. |
| `POST /{id}/restore` | Undo a delete within 30 days. |

## Sync on the desktop

The app keeps `.kiungo/sync.json` per project: `{ revision, files: { path: sha256 } }`, which is the last tree both sides agreed on.

1. **Push** (after a save settles, at most once every 30 s, and on close):
   - Hash the local files and compare them with `sync.json`.
   - If nothing changed, do nothing.
   - Otherwise upload the missing blobs, then `PUT` with `If-Match: r{sync.revision}`.
   - On 200, write the new `sync.json`.
2. **Pull** (on open, and on Home):
   - `GET /{id}`. If the revision is newer than `sync.json` and nothing changed locally, fetch the changed blobs and write them atomically, the same way saves are written.
3. **Conflict** (409, or the server is newer *and* local files changed):
   - Per file, compare base (`sync.json`), local and server.
   - A file changed on one side only is taken from that side.
   - A file changed on both sides is a real conflict. The local file stays. The server's copy is written next to it as `sketch.ino (from BRAD-THINKPAD, 2 Nov).ino` (`circuit.json`, likewise). The app says which files conflict and lets the person choose.
   - Then commit the merged tree with `If-Match` set to the server's revision.
   - Nothing is ever silently overwritten.
4. **Offline:** everything queues. Sync is never needed to open, edit, build or run.

## Phase One import (DSK-15)

The website's projects and lab sessions (`/auth/me/projects`, `/auth/me/lab-sessions`) become desktop projects:

- A lab session's document becomes `circuit.json` (it's the same format).
- Its board decides `kiungo.json`'s board.
- It starts with a blank sketch.
- Import runs on the desktop, so it needs no new endpoints. Importing the same thing twice makes a second copy and says so.

## Questions for review

1. **Quota.** Is 200 MB per account right for students? (Most projects are under 100 KB; records with photos are the big ones.)
2. **Storage.** Keep blobs in PostgreSQL (`bytea`), or put them in object storage (GCS) from the start? Postgres is simpler while we're small; GCS is cheaper past a few GB. Masden's call.
3. **Revisions.** Is 20 kept revisions per project the right number, or is restore out of scope for launch?
4. **Teachers.** Should a teacher's account ever see a student's synced projects? Not in this design. Classes are Phase Three and need their own consent model.
