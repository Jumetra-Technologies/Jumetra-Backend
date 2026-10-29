# Database

## Which database

`DATABASE_URL` picks it. Without it the server uses a SQLite file,
`<data dir>/platform.db`, which is right for development and tests.

Staging and production use PostgreSQL:

```text
DATABASE_URL=postgresql+psycopg://kiungo:<password>@<host>:5432/kiungo
```

`postgres://` and `postgresql://` are accepted and rewritten to the psycopg
driver. The driver is `psycopg` 3 (`requirements.txt`).

## Migrations

Alembic, in `alembic/versions`. The server runs `upgrade head` when it starts
(`api/db/init_db.py`), so a deploy needs no separate migration step. To run
them by hand, or to write a new one:

```bash
DATABASE_URL=… alembic upgrade head
alembic revision --autogenerate -m "what changed"   # then read the file it wrote
```

A database created by the old `create_all` path (the Render disk, or a local
file from before this) has no `alembic_version` table. `init_db` adds the
columns the baseline expects, stamps it at `0001_baseline`, and upgrades from
there.

| Revision | What |
| --- | --- |
| `0001_baseline` | Every table before migrations existed: the Phase One platform tables, the identity tables, the account data tables |
| `0002_desktop_sign_in` | `devices`, `desktop_auth_codes`; `client` and `device_id` on `refresh_tokens`; `device_id` on `access_tokens` |

Write migrations with `batch_alter_table` for anything that changes an
existing table (`alembic/env.py` sets `render_as_batch`), so they run on
SQLite as well as PostgreSQL.

## Setting up staging

1. Create the database and a role with rights on it.
2. Set `DATABASE_URL`, `SESSION_SECRET`, `FIREBASE_CREDENTIALS` and
   `HHIP_CORS_ORIGINS` on the service.
3. Start the server: it creates the schema.
4. Point the website at it with `NEXT_PUBLIC_API_URL`.

The current production deploy (Cloud Functions, `main.py`) stores its data
under `/tmp`, which does not survive a cold start. Moving it to PostgreSQL is
the point of this setup; see jumetra-frontend #56.
