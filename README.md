# Digikart

> **The digital product mart** — list and sell files, notes, videos, links and bundles.

> ⚠️ **Migration in progress.** The codebase started life as a single-subject
> study platform and is being generalized into a multi-purpose digital product
> mart. The description below still reflects the study-platform model
> (`Year→Subject→…→{Lecture,Note}`); it will be replaced as the
> `Collection→Product` model lands.

A premium MBBS study platform: students browse year/subject content, watch
chapter-wise YouTube lectures, and read **protected, watermarked notes** unlocked
via Razorpay payments. Notes are priced individually or sold as **chapter / unit /
subject bundles**; students add what they want to a **unified cart** (with optional
**coupon** codes) and buying any level unlocks everything beneath it. Note PDFs are
served straight from private object storage through short-lived signed URLs (Django
never proxies the bytes) and the buyer's watermark is drawn in the browser. A custom
admin dashboard controls all content, pricing, coupons, homepage text, and footer
links — no code changes needed.

---

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + Vite 6 + Tailwind CSS v4 (`client/`) |
| Backend | Django 6 + Django REST Framework (`backend/`) |
| Auth | Google Sign-In only → JWT (SimpleJWT), single-device sessions, refresh-token rotation & blacklist |
| Database | PostgreSQL in prod (via `DATABASE_URL`); SQLite fallback for local dev |
| Cache | Redis in prod (via `REDIS_URL`); in-memory fallback locally |
| Payments | Razorpay (server-side signature verification) |
| Files | Local filesystem in dev; private **Cloudflare R2** bucket in prod (S3-compatible, via django-storages) — every note stored as the untouched **original** + a backend-generated **compressed** rendition |
| PDF | pdf.js viewer — bytes fetched **direct from storage** over HTTP Range via short-lived signed URLs; the **compressed** copy opens first and the **original** upgrades each page in place in the background; both cached in the browser (IndexedDB), watermark drawn **client-side** |

## Repository layout

```
digikart/
├─ backend/                 # Django + DRF API
│  ├─ config/               # project (split settings: base/dev/prod)
│  ├─ apps/
│  │  ├─ accounts/          # custom User, JWT auth, profile, admin users
│  │  ├─ content/           # Year→Subject→Section→Unit→Chapter→{Lecture,Note}
│  │  │                     #   + public read APIs, admin CRUD, access check + signed-URL endpoint
│  │  ├─ payments/          # Order/OrderItem/Entitlement/Coupon, Razorpay, pricing, entitlements
│  │  ├─ engagement/        # Announcements, ContactMessage, Bookmark, Progress
│  │  └─ siteconfig/        # SiteContent (homepage text + footer links, admin-editable)
│  ├─ requirements.txt
│  └─ .env.example
└─ client/                  # React + Vite + Tailwind
   └─ src/
      ├─ auth/  lib/  components/  pages/   # student app
      └─ admin/                            # custom admin dashboard (/admin)
```

---

## Prerequisites

- **Python 3.12+** (developed on 3.14)
- **Node.js 18+** (developed on 25) & npm
- *(optional)* PostgreSQL & Redis for prod-like local runs

## Backend setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env            # then edit .env (see below)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_content        # demo years/subjects/units/chapters/lectures
.venv/bin/python manage.py createsuperuser     # prompts email, full_name, password
.venv/bin/python manage.py runserver           # http://localhost:8000
```

### Backend environment (`backend/.env`)

| Var | Purpose |
|---|---|
| `SECRET_KEY` | Django secret (generate one; see `.env.example`) |
| `DEBUG` | `True` locally, `False` in prod |
| `ALLOWED_HOSTS` | comma-separated hostnames |
| `DATABASE_URL` | Postgres DSN; unset → local SQLite |
| `REDIS_URL` | Redis DSN; unset → in-memory cache |
| `CORS_ALLOWED_ORIGINS` | extra frontend origins (Vite dev origin allowed automatically) |
| `GOOGLE_OAUTH_CLIENT_ID` | **Required** — Google OAuth client id; the backend verifies every sign-in token against it (must match the frontend's `VITE_GOOGLE_CLIENT_ID`) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Razorpay keys (TEST in dev, LIVE in prod) |

> `DJANGO_SETTINGS_MODULE` defaults to `config.settings.dev` (manage.py) and
> `config.settings.prod` (wsgi/asgi). Override via the env var.

## Frontend setup

```bash
cd client
npm install
cp .env.example .env            # set VITE_API_BASE_URL + VITE_GOOGLE_CLIENT_ID + VITE_RAZORPAY_KEY_ID
npm run dev                     # http://localhost:5173
```

| Var | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL (e.g. `http://localhost:8000`) |
| `VITE_GOOGLE_CLIENT_ID` | **Required** — Google OAuth client id (public; the only sign-in method). Same value as the backend's `GOOGLE_OAUTH_CLIENT_ID` |
| `VITE_RAZORPAY_KEY_ID` | Razorpay **public** key id (safe to expose) |

Open **http://localhost:5173** and click **Continue with Google** — the first
sign-in creates the account automatically (Google is the only sign-up method).
To grant admin access, mark a user `is_staff=True` (via Django's `/admin/` using
a superuser, or the DB); after signing in with Google they'll see the React
**`/admin`** dashboard.

---

## Admin dashboard (`/admin`)

A staff user (`is_staff=True`) can manage everything from the branded React admin:

- **Content** — years, subjects, sections (Coming Soon toggles), units, chapters,
  lectures, and **note uploads**, with **per-note pricing** (the note is the priced
  leaf: free, or an individual price) plus **bundle pricing** on each chapter / unit /
  subject (sum of its contents, a custom price, or not sold as a bundle). Also
  standalone dashboard **general videos** (curated YouTube playlists).
- **Coupons** — percentage or flat-amount codes with usage caps, a minimum-amount
  rule, and a validity window.
- **Announcements** — scheduled banner messages.
- **Messages** — the Help & Contact inbox (with status).
- **Site content** — homepage hero text, byline, and footer YouTube/Instagram/Telegram links.
- **Students** — searchable user list.
- **Overview** — totals + sales/revenue.

Django's built-in admin (`/admin/` on the backend) is also available as a
low-level ops tool.

---

## Testing

```bash
cd backend
.venv/bin/python manage.py test --settings=config.settings.test
```

> Always pass `--settings=config.settings.test` — it forces a throwaway local
> SQLite database, so the test run can never touch the real `DATABASE_URL`
> (production Postgres).

Covers auth (incl. single-device sessions), content access-gating via the
signed-URL endpoint (free vs. locked vs. admin-preview, and "no file URL ever
leaks into the public tree"), admin gating, the unified cart + coupon checkout,
and the full payment flow (signature verification + hierarchical entitlement unlock).

---

## How the security model works

- **APIs are secure-by-default**: every DRF endpoint requires auth unless it
  explicitly opts into public access (browsing). Admin endpoints require `is_staff`.
- **Paid notes are never trusted to the client.** The single function
  `content/access.py::chapter_unlocked` decides access (free, valid purchase via
  chapter/unit/subject entitlement, or admin) and every endpoint defers to it.
- **No raw file URLs.** A note's bytes live in a **private** bucket. The only way
  to reach them is `GET /notes/<id>/signed-url/`, which re-checks access on every
  request and returns a **60-second presigned URL**; the browser then fetches the
  file **directly from storage** over HTTP Range. Django never serves the bytes.
- **Per-user watermark.** The viewer draws the buyer's **email + name on every
  page** (client-side, on the page canvas). It's a traceability/deterrent overlay
  rather than an un-strippable burn-in — a deliberate trade for the huge
  performance/cost win of not proxying files through the app.
  *No website can 100% prevent screenshots or screen recording — watermarking +
  protected access (and the [anti-capture wrapper](client/src/components/ProtectedContent.jsx))
  make casual sharing traceable and inconvenient, which is the realistic goal.*
- **Payments** are verified on the backend via Razorpay's HMAC-SHA256 signature
  before any entitlement is granted; prices are always computed server-side.

---

## Production notes (when deploying)

- Set `DJANGO_SETTINGS_MODULE=config.settings.prod`, a strong `SECRET_KEY`,
  `DEBUG=False`, real `ALLOWED_HOSTS`, `DATABASE_URL` (Postgres), `REDIS_URL`,
  and `CORS_ALLOWED_ORIGINS`.
- **File storage**: `django-storages[s3]` + `boto3` ship in `requirements.txt`;
  set the `CLOUDFLARE_R2_*` env vars and `prod.py` switches `STORAGES["default"]`
  to the R2 bucket automatically (see `config/settings/prod.py`). Keep the
  bucket **private** — the app hands out short-lived **signed URLs** and the
  browser fetches files directly, so add a bucket **CORS rule** allowing
  `GET`/`HEAD` + the `range` header from your frontend origin (see
  `cloudflare-r2-cors.json`). Click-by-click setup: `CLOUDFLARE_R2_SETUP.md`.
- Add `gunicorn` + `whitenoise` for serving; run `manage.py collectstatic`.
- Swap Razorpay TEST keys for LIVE keys, and set `RAZORPAY_WEBHOOK_SECRET` to
  enable the server-to-server payment webhook.

## Shipped since the first cut

- **Unified cart + hierarchical bundles** — buy an individual note or a whole chapter / unit / subject; the server re-prices authoritatively and dedupes overlap (a note whose chapter is also in the cart is never charged twice).
- **Coupons** — percentage / flat codes with usage caps + validity window, applied at checkout via a concurrency-safe two-phase **reserve → consume** (only counted once payment succeeds); managed from the admin.
- **Per-note pricing** — the note is the priced leaf; chapters/units/subjects are priced as bundles (sum of contents, a custom price, or not sold whole).
- **Standalone dashboard videos** — `GET /api/v1/general-videos/`: curated YouTube playlists (e.g. "The Academic Edge") shown on the dashboard, outside the MBBS hierarchy.
- **Global search** — `GET /api/v1/search/` + the header `SearchBar` (years/subjects/units/chapters).
- **Direct-from-storage note delivery** — signed URLs + HTTP Range; Django no longer proxies PDF bytes.
- **Browser note cache** — assembled PDFs cached in IndexedDB, so repeat opens cost zero storage egress (cleared on logout).
- **Payment webhook** — `POST /api/v1/payments/webhook/` fulfils orders even if the client callback is dropped (set `RAZORPAY_WEBHOOK_SECRET`).
- **Dark mode** and the **anti-capture wrapper** on the notes viewer.

## Roadmap / deferred

- Video/image note types (the `Note.file_type` field already supports them).
