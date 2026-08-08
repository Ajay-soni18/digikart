# Digikart

> **The digital product mart** — list and sell files, notes, videos and bundles.

Digikart sells digital products. A buyer browses a category tree, opens a
product, and pays via Razorpay; the files they bought are then served straight
from private object storage through short-lived signed URLs, with PDFs opening
in a watermarked in-browser viewer that never offers a download.

The catalog is deliberately domain-neutral:

- **Categories** are navigation only. They nest to any depth and never carry a
  price or an entitlement, so the storefront can be reorganised freely without
  ever granting or revoking someone's access.
- **Products** are the sellable unit. Each holds one or more files of any type,
  and may be fronted by a free, public YouTube video used as the hook — the
  video sells the files, and the files are what's actually gated.
- **Bundles** sell a set of products, and can nest other bundles. Membership is
  resolved live, so anything added to a bundle later reaches everyone who
  already bought it.

A custom admin dashboard controls the whole catalog, pricing, coupons, homepage
text and footer links — no code changes needed.

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
| Files | Local filesystem in dev; private **Cloudflare R2** bucket in prod (S3-compatible, via django-storages). PDFs are stored as the untouched **original** plus a backend-generated **compressed** rendition; every other type is stored as-is |
| PDF | pdf.js viewer — bytes fetched **direct from storage** over HTTP Range via short-lived signed URLs; the **compressed** copy opens first and the **original** upgrades each page in the background; both cached in the browser (IndexedDB), watermark drawn **client-side** |

## Repository layout

```
digikart/
├─ backend/                 # Django + DRF API
│  ├─ config/               # project (split settings: base/dev/prod)
│  ├─ apps/
│  │  ├─ accounts/          # custom User, JWT auth, profile, admin users
│  │  ├─ catalog/           # Category tree + Product + ProductFile + Bundle
│  │  │                     #   access.py       the single access rule
│  │  │                     #   entitlements.py "do they own this?"
│  │  │                     #   pricing.py      server-authoritative pricing
│  │  │                     #   membership.py   Bundle→Product closure table
│  │  │                     #   files.py        upload / compress / store
│  │  ├─ payments/          # Order/OrderItem/Entitlement/Coupon, Razorpay
│  │  ├─ engagement/        # Announcements, ContactMessage, Bookmark, Progress
│  │  └─ siteconfig/        # SiteContent (page copy, admin-editable)
│  ├─ requirements.txt
│  └─ .env.example
└─ client/                  # React + Vite + Tailwind
   └─ src/
      ├─ auth/  lib/  components/  pages/   # storefront
      └─ admin/                            # custom admin dashboard (/admin)
```

---

## Prerequisites

- **Python 3.12+**
- **Node.js 18+** & npm
- *(optional)* PostgreSQL & Redis for prod-like local runs

## Backend setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

cp .env.example .env            # then edit .env (see below)
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_catalog --preset both   # demo catalog
.venv/bin/python manage.py createsuperuser              # prompts email, full_name, password
.venv/bin/python manage.py runserver                    # http://localhost:8000
```

`seed_catalog` ships two presets. `study` builds a course-shaped catalog
(Medicine → Year 2 → Pathology); `creative` builds an unrelated one
(Photography → presets, sample packs). The second one exists to keep the model
honest — if `creative` ever becomes awkward to express, the catalog has drifted
back towards being education-shaped. `--reset` clears the catalog first.

### Backend environment (`backend/.env`)

| Var | Purpose |
|---|---|
| `SECRET_KEY` | Django secret (generate one; see `.env.example`) |
| `DEBUG` | `True` locally, `False` in prod |
| `ALLOWED_HOSTS` | comma-separated hostnames |
| `DATABASE_URL` | Postgres DSN; **leave commented out** for local SQLite (an empty value is not the same as unset — django-environ raises on `""`) |
| `REDIS_URL` | Redis DSN; same empty-vs-unset trap |
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
a superuser, or the DB); after signing in they'll see the React **`/admin`**
dashboard.

---

## API

Everything lives under `/api/v1/`. Browsing is public; anything that reaches a
file requires auth.

| Endpoint | Purpose |
|---|---|
| `GET /categories/` | the whole published navigation tree, in one response |
| `GET /categories/<slug>/` | one category: breadcrumb, children, products, bundles |
| `GET /products/<slug>/` | one product: metadata, its files, the bundles containing it |
| `GET /bundles/<slug>/` | one bundle: price and members |
| `GET /search/?q=` | across categories, products and bundles |
| `GET /files/<id>/signed-url/` | **auth + ownership required** — short-lived signed URLs |
| `POST /payments/quote/` | price a cart (server-authoritative, dedupes overlap) |
| `POST /payments/create-order/` → `verify/` | Razorpay order + signature verification |
| `POST /payments/webhook/` | server-to-server fulfilment fallback |

Admin CRUD sits under `/api/v1/admin/` (`categories`, `products`,
`product-files`, `bundles`, `bundle-items`, plus `overview` and `revenue`) and
requires `is_staff`.

---

## Admin dashboard (`/admin`)

A staff user (`is_staff=True`) can manage everything from the branded React admin:

- **Catalog** — categories, products, and each product's files, with per-product
  pricing (free, an individual price, or ₹0 to sell only inside a bundle) and a
  per-file delivery mode (protected viewer for PDFs, or direct download).
- **Bundles** — build a set from products and other bundles, priced as the sum
  of its contents or at a custom price.
- **Coupons** — percentage or flat-amount codes with usage caps, a minimum-amount
  rule, and a validity window.
- **Announcements** — scheduled banner messages.
- **Messages** — the Help & Contact inbox (with status).
- **Site content** — page copy and footer links.
- **Buyers** — searchable user list.
- **Overview / Revenue** — totals, time series, and revenue rolled up the
  category tree (a parent's figure is the true total of everything beneath it).

Django's built-in admin (`/admin/` on the backend) is also available as a
low-level ops tool.

---

## Testing

```bash
cd backend && .venv/bin/python manage.py test --settings=config.settings.test
cd client  && npm test
```

> Always pass `--settings=config.settings.test` — it forces a throwaway local
> SQLite database, so the test run can never touch the real `DATABASE_URL`.

Covers auth (incl. single-device sessions), the access rule via the signed-URL
endpoint (free vs locked vs admin-preview, and "no storage key ever leaks into a
public payload"), admin gating, the unified cart + coupon checkout, and the full
payment flow. `apps/payments/test_security_audit.py` is a separate adversarial
suite: forged and replayed payments, another user's order, amounts tampered with
after a quote, signed URLs without a purchase, and coupon probing.

---

## How the security model works

- **APIs are secure-by-default**: every DRF endpoint requires auth unless it
  explicitly opts into public access (browsing). Admin endpoints require `is_staff`.
- **Paid files are never trusted to the client.** The single function
  `catalog/access.py::product_unlocked` decides access (free, staff preview, or a
  product/bundle entitlement) and every endpoint defers to it.
- **Categories can never grant access.** Navigation and ownership are separate
  graphs; there is a test asserting that an entitlement wrongly pointing at a
  category unlocks nothing.
- **No raw file URLs.** Bytes live in a **private** bucket. The only way to reach
  them is `GET /files/<id>/signed-url/`, which re-checks access on every request
  and returns a short-lived presigned URL; the browser then fetches the file
  **directly from storage** over HTTP Range. Django never serves the bytes.
- **Per-user watermark.** The viewer draws the buyer's **email + name on every
  page** (client-side, on the page canvas). It's a traceability/deterrent overlay
  rather than an un-strippable burn-in — a deliberate trade for the large
  performance/cost win of not proxying files through the app.
  *No website can 100% prevent screenshots or screen recording — watermarking +
  protected access (and the [anti-capture wrapper](client/src/components/ProtectedContent.jsx))
  make casual sharing traceable and inconvenient, which is the realistic goal.*
- **YouTube videos are never treated as protected.** A YouTube URL can't be
  access-gated, so it is shown to everyone as a free hook rather than pretended
  to be secure.
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
- If bundle membership ever looks wrong after a bulk import or a restore,
  `manage.py rebuild_bundle_membership` recomputes the closure table from
  scratch. It's idempotent and safe to run any time.

## Roadmap / deferred

- Multi-seller support (seller accounts, payouts, moderation). The catalog is
  single-seller by design today.
- Uploaded (non-YouTube) video products with signed-URL streaming.
