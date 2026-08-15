# Zonovia Web (`web/`)

React 19 + TypeScript + Vite + TanStack Query + React Router + Tailwind 4 frontend for Zonovia's Phase 2
tracking baseline: sign in, then scan a QR code or barcode (camera or manual entry) to resolve it to an
asset and log a tracking event.

## Running locally

```bash
npm install
npm run dev
```

The dev server runs at `http://localhost:5173`. It talks directly to the backend API (no dev proxy) —
the backend already has CORS configured for `http://localhost:5173`.

Copy `.env.example` to `.env` (or `.env.development`) and set:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

This is also the default baked into `src/core/apiClient.ts` if the env var is unset, so a local backend
on port 8000 works with no `.env` file at all.

Demo tenant slug: `acme-demo` (seeded by the backend's `seed.py`).

## Other scripts

- `npm run build` — type-checks (`tsc -b`) then builds a production bundle to `dist/`.
- `npm run lint` — runs `oxlint`.
- `npm run preview` — serves the production build locally.

## Camera scanning and HTTPS

`ScanPage` uses `@zxing/browser`'s `BrowserMultiFormatReader` against `getUserMedia`, which requires a
**secure context**. Plain `http://localhost` is exempted by browsers, so scanning works out of the box in
local dev. Testing on an actual phone over LAN (e.g. `http://192.168.x.x:5173`) will *not* get camera
access, because that origin isn't a secure context — you'd need an HTTPS dev workaround (a tunnel like
ngrok/Cloudflare Tunnel, or a locally-trusted TLS cert for Vite's dev server). That workaround is out of
scope for this phase; the manual "enter code" fallback on `ScanPage` works everywhere regardless.
