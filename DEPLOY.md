# Deploying Digikart to production

## Recommended architecture

```
                 ┌──────────────┐         ┌──────────────────┐
  Buyers    ───▶ │  Frontend     │  HTTPS  │  Backend          │
  (browser)      │  static + CDN │ ──────▶ │  Django + gunicorn│
                 │  (Vite build) │   API   │                   │
                 └──────┬───────┘         └───────┬───────────┘
                        │                          │
                        │              ┌───────────┼───────────┐
                        │              ▼           ▼           ▼
                        │      ┌──────────────┐ ┌────────┐ ┌──────────┐
                        │      │ PostgreSQL    │ │ Redis   │ │ Razorpay  │
                        │      │ (managed)     │ │(cache+  │ │(payments) │
                        │      └──────────────┘ │throttle)│ └──────────┘
                        │                       └────────┘
                        │  signed URLs (60s) + HTTP Range       ▲
                        │  ── note bytes fetched DIRECTLY ──────┘ sign only
                        ▼
                ┌─────────────────────┐
                │ Cloudflare R2        │   ◀── Django signs URLs; the BROWSER
                │ (PRIVATE bucket)     │       downloads the bytes (never proxied)
                └─────────────────────┘
```

- **Frontend**: static build hosted on a CDN (Render Static Site / Netlify / Vercel / Cloudflare Pages).
- **Backend**: Django served by **gunicorn** (Render / Railway / Fly.io / a VPS).
- **PostgreSQL**: a managed database (never the local SQLite fallback).
- **Redis**: managed cache — backs **request throttling shared across workers** and general caching. (Repeat PDF loads are served from the browser's own IndexedDB cache, not Redis.)
- **Cloudflare R2**: a **private** bucket for uploaded note PDFs & images (S3-compatible API, free 10 GB storage, **zero egress fees**). Required because most hosts have ephemeral disks (local uploads vanish on redeploy). Every note upload is stored twice by the backend — the untouched **original** plus an auto-generated **compressed** fast preview — and the backend only **signs** short-lived URLs; the browser fetches the bytes directly, so the bucket needs a CORS rule (see Step 3).

The examples below use **Render** (the repo already ships a `Procfile` + `build.sh`), but every step maps to other hosts.

---

## Step 1 — PostgreSQL
Create a managed Postgres instance and copy its connection string:
```
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME
```
Enable automatic daily backups.

## Step 2 — Redis
Create a managed Redis instance and copy its URL:
```
REDIS_URL=rediss://:PASSWORD@HOST:6379/0
```
This backs request throttling shared across all gunicorn workers (login/payment rate limits) and general server-side caching. It is configured to **fail soft** — a flaky or over-quota Redis returns misses instead of 500ing requests. (Fast *repeat* PDF opens come from the browser's IndexedDB cache, not Redis, so Redis is no longer on the hot path for note loading.)

## Step 3 — Object storage (Cloudflare R2, private bucket)
The app uses **Cloudflare R2** through its S3-compatible API. The complete
click-by-click walkthrough lives in **`CLOUDFLARE_R2_SETUP.md`** (account,
bucket, API token, CORS, env vars, testing); the short version:
1. Cloudflare dashboard → **R2 Object Storage** → create a bucket. Keep it
   **private**: never enable *Public Access* / the `r2.dev` subdomain, and
   don't attach a custom domain to the bucket.
2. R2 → **API → Manage API tokens** → create a token with **Object Read &
   Write**, scoped to that one bucket. Copy the **Access Key ID** / **Secret
   Access Key** it shows once.
3. Add a **CORS rule** on the bucket (Settings → CORS policy) — **required for
   note PDFs**, since the browser fetches them directly from the bucket with
   HTTP **Range** requests. Allow `GET`/`HEAD` from your frontend origin,
   permit the `range` request header, and expose the range/length response
   headers. The repo's **`cloudflare-r2-cors.json`** is the ready-to-paste
   policy. Without it the viewer's range probe fails and notes fall back to a
   slow full-file download (or won't load at all under strict CORS).
4. Collect (see `backend/.env.example`):
   ```
   CLOUDFLARE_R2_ACCOUNT_ID=...         # 32-hex Account ID (R2 Overview page)
   CLOUDFLARE_R2_ACCESS_KEY_ID=...
   CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
   CLOUDFLARE_R2_BUCKET_NAME=...
   CLOUDFLARE_R2_ENDPOINT_URL=          # optional; defaults to https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   CLOUDFLARE_R2_REGION=auto            # R2 is always "auto"
   ```

## Step 4 — Backend (Django + gunicorn)
Create a **Web Service** from the repo, root = `backend/`.

- **Build command:** `./build.sh`  (installs deps, `collectstatic`, `migrate`)
- **Start command:** `gunicorn config.wsgi:application --workers 3 --threads 4 --timeout 300 --bind 0.0.0.0:$PORT`
  *(or rely on the `Procfile`. `--timeout 300` gives admin note uploads room:
  the request receives the PDF, validates it, generates the compressed
  rendition and uploads both files to R2 — slow on small shared CPUs.)*
- **Health check path:** `/healthz`

**Environment variables:**
```
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=<generate a long random value>
DEBUG=False
ALLOWED_HOSTS=api.yourdomain.com
DATABASE_URL=postgres://...
REDIS_URL=rediss://...
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
RAZORPAY_KEY_ID=rzp_live_xxx
RAZORPAY_KEY_SECRET=xxx
CLOUDFLARE_R2_ACCOUNT_ID=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET_NAME=...
CLOUDFLARE_R2_REGION=auto
SIGNED_URL_EXPIRY_SECONDS=60
```
Generate a secret key:
```
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```
After the first deploy, create your admin from the host's shell:
```
python manage.py createsuperuser --settings=config.settings.prod
```
HTTPS, the proxy header, secure cookies and HSTS are already enabled in `config/settings/prod.py`.

## Step 5 — Frontend (static + CDN)
Create a **Static Site** from the repo, root = `client/`.

- **Build command:** `npm ci && npm run build`
- **Publish directory:** `dist`
- **Build-time environment variables:**
  ```
  VITE_API_BASE_URL=https://api.yourdomain.com
  VITE_RAZORPAY_KEY_ID=rzp_live_xxx
  ```
SPA routing is handled by `client/public/_redirects` (`/* → /index.html`), which Render/Netlify honour. On **Vercel**, add a `vercel.json` rewrite; on **Cloudflare Pages** it's automatic.

## Step 6 — Razorpay (live)
1. Complete Razorpay KYC and switch to **Live** mode.
2. Put the **live** key id + secret in the backend env, and the **public** key id in `VITE_RAZORPAY_KEY_ID`.
3. The backend verifies every payment's signature before unlocking content (`/api/v1/payments/verify/`).
4. **Set up the webhook** (already implemented): Dashboard → Settings → Webhooks → point it at `https://api.yourdomain.com/api/v1/payments/webhook/`, subscribe to `payment.captured` and `order.paid`, and set its signing secret as `RAZORPAY_WEBHOOK_SECRET` in the backend env. This fulfils the order even if the buyer closes the tab before the client `verify` callback runs. Fulfilment is **idempotent** (row-locked), so the webhook and the callback can't double-grant. Leaving `RAZORPAY_WEBHOOK_SECRET` blank disables the endpoint (it returns 404).

## Step 7 — DNS
- `api.yourdomain.com` → backend service
- `yourdomain.com` (+ `www`) → frontend site
- `CORS_ALLOWED_ORIGINS` and `ALLOWED_HOSTS` must exactly match these hostnames.

---

## Go-live checklist
- [ ] `DEBUG=False`, strong secret `SECRET_KEY`, correct `ALLOWED_HOSTS`.
- [ ] `python manage.py check --deploy --settings=config.settings.prod` is clean.
- [ ] HTTPS works and HTTP redirects to HTTPS (enabled in prod settings).
- [ ] Fresh admin created with a strong password via `python manage.py createsuperuser --settings=config.settings.prod` (never hardcode passwords in the repo).
- [ ] **Scrub the Razorpay test keys from `backend/.env.example`** (committed template) — keep secrets only in the host's env.
- [ ] Postgres backups enabled.
- [ ] Verify a note's object in the bucket is **not** publicly downloadable (private).
- [ ] Smoke test: signup → login → single-device logout (log in on a 2nd device, confirm the 1st is kicked) → buy a note → open the watermarked PDF → admin **Revenue** shows the transaction.

---

## Making PDF loading fast & smooth
- **Bytes never touch Django (biggest win):** `GET /files/<id>/signed-url/` only checks access and returns short-lived presigned URLs (60 s by default — `SIGNED_URL_EXPIRY_SECONDS`); the browser streams the file **directly from R2** over HTTP Range (current page first, the rest in the background). The backend bears no per-file CPU/RAM/bandwidth — so concurrency is bounded by R2, not the dyno. **This requires the bucket CORS rule from Step 3.**
- **Compressed-first, original-in-background:** every admin upload is stored as TWO renditions — the untouched original and an auto-compressed fast preview (images downsampled to reading DPI; typically ~10–15 % of the original for scans). The viewer opens the compressed copy almost immediately, then fetches the original with the same page-priority order and **upgrades each page in place** (page N replaces page N only — no reflow, no page jump). Tiny uploads skip the second copy; a compression failure just means the original alone is served.
- **Browser cache for repeat opens:** the viewer assembles the streamed bytes and stores BOTH renditions in **IndexedDB**, keyed by `user + note + file version + quality`. Re-opening the same note on the same device is served from disk — **zero storage egress, zero signed-URL call** (a cached original wins outright; a cached compressed shows instantly while the original still upgrades) — and the cache is wiped on logout. Replacing a note's file bumps its `file_version`, which auto-invalidates the old cached copies.
- **gunicorn threads:** buyer requests are light + I/O-bound (auth, sign URLs, small JSON); `--threads 4` lets one worker serve many concurrently. Since byte-streaming no longer lives in the worker, scaling `--workers` is memory-cheap (see `Procfile`).
- **Frontend is already optimised:** routes are code-split and **pdf.js is lazy-loaded only on the notes route**, so first paint is fast and the heavy PDF engine downloads only when a note is opened.
- **CDN:** the frontend is served from the static host's CDN. Note PDFs are private + per-user-signed so they can't be CDN-cached, but the compressed-first flow + per-device IndexedDB cache cover fast first and repeat views.

## Local production smoke test (optional)
```
cd backend
SECRET_KEY=test ALLOWED_HOSTS=localhost DATABASE_URL=postgres://... REDIS_URL=redis://localhost:6379/0 \
  .venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000
```
