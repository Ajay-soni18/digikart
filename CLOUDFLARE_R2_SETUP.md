# Cloudflare R2 — manual setup guide

Everything the code needs from Cloudflare, click by click. The app talks to R2
through its **S3-compatible API** using the `CLOUDFLARE_R2_*` env vars below —
there is nothing to deploy on Cloudflare itself (no Worker, no custom domain,
no public bucket).

How the app uses the bucket, so the setup below makes sense:

- The **admin uploads one PDF** in the dashboard, exactly as before. Django
  validates it, stores the **untouched original**, generates a **compressed
  rendition** (~10–15 % of the original for scans), and saves both privately:
  ```
  notes/{note_id}/{file_version}/original.pdf
  notes/{note_id}/{file_version}/compressed.pdf
  ```
- A student's viewer calls `GET /api/v1/notes/<id>/signed-url/`; Django checks
  access and returns **short-lived presigned URLs** (60 s) for both renditions.
  The browser fetches the bytes **directly from R2** with HTTP Range requests —
  compressed first (instant open), original upgrading each page in the
  background. Django never proxies file bytes.
- Subject/lecture thumbnails also live in the bucket and are served the same
  presigned way.

---

## 1. Create a Cloudflare account

1. Go to <https://dash.cloudflare.com/sign-up> and sign up with your email
   (free plan — no domain needed for R2).
2. Verify the email address. That's it — you do **not** need to add a website.

## 2. Enable R2 and create the bucket (free plan)

1. In the dashboard's left sidebar, open **R2 Object Storage**.
2. The first time, Cloudflare asks you to enable R2. A **card is required for
   verification**, but the free tier costs nothing until you exceed:
   **10 GB storage**, 1 M class-A (writes) and 10 M class-B (reads) operations
   per month — and **egress (downloads) is always free**, which is exactly what
   the direct-from-bucket viewer needs.
3. Click **Create bucket**:
   - **Name**: e.g. `digikart-files` (lowercase; this becomes
     `CLOUDFLARE_R2_BUCKET_NAME`).
   - **Location**: leave **Automatic**, hint **Asia-Pacific (APAC)** if offered
     — closest to your students.
   - **Storage class**: Standard.
4. While you're on the R2 **Overview** page, copy your **Account ID** (a
   32-character hex string shown on the right side; it's also in the dashboard
   URL). This becomes `CLOUDFLARE_R2_ACCOUNT_ID`.

## 3. Keep the bucket private (important)

Private is the **default** — you just have to *not* turn on the public options:

- Bucket → **Settings** → **Public access**:
  - **R2.dev subdomain**: leave **disabled** (never "Allow Access").
  - **Custom domains**: do **not** connect one.
- Don't create any "public bucket" Worker bindings.

With both off, objects are reachable **only** through presigned URLs that your
Django backend mints after its access check. Anyone hitting
`https://<account>.r2.cloudflarestorage.com/digikart-files/...` without a valid
signature gets `401/403`.

## 4. Create the S3 API token (access key + secret)

1. R2 Object Storage → **API** dropdown (top right) → **Manage API tokens**
   *(older dashboards: "Manage R2 API Tokens")* → **Create API token**.
2. Configure:
   - **Token name**: `digikart-django`.
   - **Permissions**: **Object Read & Write** — the app uploads (admin),
     reads/presigns (students), and deletes (note replace/delete). Do **not**
     pick Admin variants; object-level is enough.
   - **Specify bucket(s)**: scope it to **only** your bucket (e.g.
     `digikart-files`) — least privilege.
   - **TTL**: Forever (rotate manually whenever you want).
3. Click **Create API token**. The next screen shows — **once** — :
   - **Access Key ID**      → `CLOUDFLARE_R2_ACCESS_KEY_ID`
   - **Secret Access Key**  → `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
   Copy both now (if lost, just roll/recreate the token).

## 5. Endpoint URL

The S3 endpoint for your account is:

```
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

You can set it explicitly as `CLOUDFLARE_R2_ENDPOINT_URL`, **or leave it
blank** — `config/settings/prod.py` derives exactly that URL from
`CLOUDFLARE_R2_ACCOUNT_ID`. The region for R2 is always `auto`
(`CLOUDFLARE_R2_REGION=auto`, the default).

## 6. CORS policy (required for the viewer)

The browser fetches PDF bytes directly from the bucket with `Range` headers, so
the bucket must allow your frontend origin.

1. Bucket → **Settings** → **CORS policy** → **Add / Edit CORS policy**.
2. Paste the repo's **`cloudflare-r2-cors.json`** (shown below), replacing the
   origins with your real frontend URL(s) — keep `http://localhost:5173` only
   if you want local dev against the real bucket:

```json
[
  {
    "AllowedOrigins": [
      "https://digikart.onrender.com",
      "http://localhost:5173"
    ],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["range"],
    "ExposeHeaders": ["Content-Range", "Content-Length", "Accept-Ranges", "ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

Notes:
- `AllowedHeaders: ["range"]` + the `ExposeHeaders` are what make pdf.js's
  progressive page-priority loading work; without them the viewer falls back to
  slow full-file downloads (or fails under strict CORS).
- No `PUT`/`POST` needed: uploads go **through Django** (server-side boto3),
  which isn't subject to browser CORS.
- If you later move the frontend to a custom domain, add it to
  `AllowedOrigins` (and to Django's `CORS_ALLOWED_ORIGINS`).

## 7. Environment variables

### Local development (`backend/.env`)
Normally **leave all R2 vars blank** locally — dev uses the local filesystem
(`media/`) automatically and everything works offline. Fill them in only if you
explicitly want local Django (with `DJANGO_SETTINGS_MODULE=config.settings.prod`)
to talk to the real bucket.

### Render (or any Django host) — Environment tab
```
CLOUDFLARE_R2_ACCOUNT_ID=<32-hex account id>
CLOUDFLARE_R2_ACCESS_KEY_ID=<from step 4>
CLOUDFLARE_R2_SECRET_ACCESS_KEY=<from step 4>
CLOUDFLARE_R2_BUCKET_NAME=digikart-files
CLOUDFLARE_R2_ENDPOINT_URL=          # optional — derived from the account id
CLOUDFLARE_R2_REGION=auto            # optional — "auto" is the default
SIGNED_URL_EXPIRY_SECONDS=60         # optional — presigned URL lifetime
```
Storage switches to R2 **when `CLOUDFLARE_R2_BUCKET_NAME` is set** (see
`config/settings/prod.py`); with it unset the app falls back to local disk
(don't do that in prod — Render's disk is ephemeral). Redeploy after saving.

`SIGNED_URL_EXPIRY_SECONDS` is deliberately short — the viewer transparently
re-signs before expiry, so readers never notice. Raise it only if you have a
reason (e.g. very slow networks fetching huge originals).

## 8. CDN / custom domain / Worker — not used, by design

**Only presigned R2 URLs are used.** No Worker, no custom domain, no CDN sits
in front of the bucket:

- Notes are **private and per-user authorized**; a CDN cache in front would
  either cache nothing (every URL is uniquely signed) or risk serving files
  without the backend's access check.
- Cloudflare's CDN cannot cache responses to presigned `r2.cloudflarestorage.com`
  URLs anyway, and R2 egress is already free, so a CDN adds no cost win.
- Speed for students comes from: the compressed-first rendition, page-priority
  Range fetching, and the browser's IndexedDB cache (repeat opens are free and
  offline-capable).

So there is **nothing to set up** for this section. (If you ever outgrow this —
e.g. you want truly public sample PDFs cached at the edge — that would be a
separate public bucket with a custom domain, and a deliberate architecture
change. Don't attach a domain to the private notes bucket.)

## 9. Test an upload (admin flow)

1. Deploy the backend with the env vars above (the release step runs the
   migration that adds the new note fields automatically).
2. Log into the React admin (`/admin`) → Content → drill into a chapter →
   **Upload note** → pick a real PDF (try a big scanned one) → Save. The
   request takes longer than before — the server is compressing and uploading
   two files. Keep the **Published** toggle on.
3. Verify in Cloudflare: bucket → **Objects** → you should see
   `notes/<note_id>/<version>/original.pdf` **and** (for files over ~1 MB)
   `compressed.pdf` next to it. The original's size must equal your file
   exactly; the compressed one is typically 10–30 % of it.
   *(Tiny uploads intentionally skip the compressed copy — the viewer then just
   loads the original.)*
4. Error cases worth trying once: a password-protected PDF and a random
   non-PDF file — both must be rejected with a clear message under the file
   field, and nothing should appear in the bucket.

## 10. Test the signed-URL fetch (student flow)

1. As a logged-in student with access (or the admin), open the note in the
   site. Expected behaviour: the loader fills fast, the note appears
   (compressed quality), a subtle **“Loading HD…”** appears in the toolbar and
   pages sharpen in place — current page first — with no page jump, and the
   watermark/zoom/bookmarks behave exactly as before. Repeat opens on the same
   device are instant (IndexedDB).
2. API-level check (optional): with a logged-in session token,
   `GET https://<api>/api/v1/notes/<id>/signed-url/` returns
   ```json
   {
     "version": "20260612...-ab12cd34",
     "expires_in": 60,
     "original":   {"url": "https://<account>.r2.cloudflarestorage.com/...original.pdf?X-Amz-..."},
     "compressed": {"url": "https://...compressed.pdf?X-Amz-..."}
   }
   ```
   - `curl -H "Range: bytes=0-99" "<that url>"` → `206 Partial Content` with a
     `Content-Range` header (Range support = page-priority loading works).
   - The same URL **without** the query-string signature → `401/403` (bucket
     is private).
   - The URL after ~60 s → `403` (expiry works; the viewer re-signs itself).
3. In the browser DevTools → Network: the PDF byte requests must go to
   `r2.cloudflarestorage.com` (never to your API host), as `206` responses.

## 11. Confirm Backblaze is fully retired

- **Code**: `git grep -i backblaze` and `git grep AWS_` in the repo return
  nothing — the integration was removed (storage now configures only from
  `CLOUDFLARE_R2_*`).
- **Runtime**: with DevTools open, browse subjects + open several notes — every
  media/PDF request hits `*.r2.cloudflarestorage.com`. Remove the old `AWS_*`
  env vars from Render so no credential for B2 even exists in the environment.
- **Money**: after students have switched over, the B2 dashboard should show
  zero download activity; nothing in the app writes there anymore.

### Existing notes that still live in Backblaze

Switching providers does **not** move old files. Rows uploaded before this
migration keep working through a legacy fallback **only if the same object
keys exist in R2**. Two options:

- **Recommended — re-upload each note once** via the admin (edit note → choose
  the same PDF → Save). This is what produces the compressed fast-preview
  rendition (old rows never have one) and the versioned keys.
- **Bulk alternative — copy the objects**, e.g. with rclone:
  ```
  rclone copy b2:<old-bucket> r2:<new-bucket>   # preserve paths exactly
  ```
  Copied notes work immediately at original quality only (no compressed copy)
  until re-uploaded. Keep the B2 files until you've verified R2 serves them —
  nothing deletes them automatically.
