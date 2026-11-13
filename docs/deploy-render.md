# Running the API on Render, with its data in Neon

Kiungo's API runs on [Render](https://render.com) (free plan) and keeps its
data in a [Neon](https://neon.tech) PostgreSQL database (free plan). Neither
needs access to the Google Cloud project; both sign in with GitHub.
`render.yaml` describes the service. Render redeploys on every push to `main`
and runs the database migrations when the server starts (`docs/database.md`).

Sign-in still uses the Firebase project `hhipsystemv0`. With only
`FIREBASE_PROJECT_ID` set, the server checks sign-in tokens against Google's
public keys (`auth/firebase.py`). The service-account file isn't needed.

## Set it up (once)

### 1. The database (Neon)

1. Go to neon.tech and choose **Sign up**, then **Continue with GitHub**.
2. Create a project: name it `kiungo`, keep the newest Postgres version, and
   pick the region **AWS Europe Central 1 (Frankfurt)**. That's where the
   Render service runs.
3. On the project's dashboard, choose **Connect**. Turn **Connection pooling
   off** and copy the connection string. It looks like
   `postgresql://neondb_owner:...@ep-...eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   Keep it private: it is the database's password.

### 2. The Firebase values the website needs

Open `https://europe-west4-hhipsystemv0.cloudfunctions.net/api/auth/config` in a
browser. Copy `apiKey` and `appId` from it. They're public: the website sends
them to every visitor.

### 3. The service (Render)

1. Go to render.com and choose **Get started**, then **GitHub**. Allow Render to
   see the `Jumetra-Technologies/jumetra-backend` repository.
2. Choose **New**, then **Blueprint**, pick `jumetra-backend`, and keep the branch `main`.
3. Render reads `render.yaml` and asks for the values marked `sync: false`:
   - `DATABASE_URL`: the Neon connection string from step 1
   - `FIREBASE_API_KEY` and `FIREBASE_APP_ID`: from step 2
   - `HHIP_ADMIN_PASSWORD_HASH`: required for the admin portal. Paste the output of
     `python -m api.services.admin_auth 'new password'`. Without it, admin
     sign-in answers 503: the built-in default is only for local development.
4. Choose **Apply**. The first deploy takes a few minutes. When it's live,
   `https://<service>.onrender.com/health` answers `{"status": "ok"}`.
5. Copy the service's address (shown at the top of its page). The website and
   the desktop app are pointed at it in jumetra-frontend.

## Good to know

- **The free plan sleeps** after 15 minutes without requests. The next request
  wakes it in about a minute. While anyone has Kiungo open, its heartbeats keep
  it awake. A paid plan ($7/month) never sleeps.
- **Neon's free plan** holds 0.5 GB and pauses its compute when idle; it wakes
  in under a second.
- **`SESSION_SECRET`** is made by Render and stays the same across deploys.
  Changing it signs everybody out.
- **People sign in again once.** Accounts on the old hand-deployed API aren't
  in this database, so the first sign-in makes a new account record.
- The Phase One workspace services keep their JSON files in `/tmp`, as they did
  on Cloud Functions. Accounts, projects, lab sessions, project sync, releases
  and the admin portal's figures are all in the database.
- **Logs and restarts:** the service's page on Render, under **Logs** and
  **Manual Deploy**.
