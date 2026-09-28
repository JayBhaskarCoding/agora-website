# Agora — website

The launch site for **Agora**, the new town square for free speech.
A human-first digital public square: zero ads, absolute chronology, strict
moderation of harm.

Pure **vanilla HTML / CSS / JS** — no frameworks, no build step. Every page
runs locally, straight from the file system.

## Pages

| File               | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `index.html`       | Home — hero, motive/philosophy, CTAs                                    |
| `shared-post.html` | Landing for shared post links (WhatsApp, etc.) when the app is not installed. Parses `?post=` / `?post_id=` / `?id=` and renders a preview stub until the backend is connected |
| `download.html`    | APK download, system requirements, version details, 3-step install guide |
| `about.html`       | Vision, creator bio (placeholder), feedback form (placeholder)           |

Shared assets:

| File               | Purpose                                            |
| ------------------ | -------------------------------------------------- |
| `style.css`        | Mobile-first design system for all pages           |
| `app.js`           | Routing, mobile menu, smooth scroll, reveals, feedback form, shared-post preview |
| `agora-beta.apk`   | The current Android build served by the download buttons |
| `favicon.svg`      | Logo / tab icon                                    |
| `assets/`          | App screenshots shown in the phone frames — see `assets/README.md` for the exact filenames to replace |

## Run locally

No build needed. Serve the folder from its root:

```bash
npm run dev          # python3 http.server on http://localhost:5173
# or
python3 -m http.server 5173
```

Useful local URLs:

- `http://localhost:5173/`
- `http://localhost:5173/shared-post.html?post=a8f3c2`  ← shared-link flow
- `http://localhost:5173/download.html`
- `http://localhost:5173/about.html`

## Deploy

The repository root **is** the static site. Point any static host
(Netlify, Cloudflare Pages, GitHub Pages, S3+CloudFront…) at the root and
keep `_redirects` / `robots.txt` in place. To test a shared link on a
custom domain, share e.g. `https://your-domain/shared-post.html?post=<id>`.

## Wiring up the backend (TODOs, all in `app.js`)

- `initSharedPost()` — `fetchPost(id)` is a stub returning a simulated
  payload after a delay. Replace with
  `GET /api/v1/posts/:id` (payload shape documented in the comment).
- `initContactForm()` — the About-page form is a demo; replace the
  `setTimeout` with a `POST` to your feedback endpoint.

## Asset paths

All CSS/JS/image/page links are **root-absolute** (`/style.css`, `/app.js`,
`/assets/…`, `/download.html`). This is deliberate: shared links arrive with
query strings and sometimes nested paths (`/post/abc123`), and relative
paths would resolve against that path, break, and get swallowed by the
`_redirects` catch-all. Because of this, serve the site from the **domain
root** (not a sub-folder) — `python3 -m http.server` from this folder does
exactly that. Opening `index.html` via `file://` will no longer resolve the
assets; use the local server instead.

## Responsive breakpoints (`style.css`)

Mobile-first base styles, then: `≤480px` phone, `≤768px` tablet (hamburger
nav), `≥769px` desktop nav, `≥1024px` wide layouts.

## Notes

- Brand assets (palette, type, voice) match the Agora app and logo:
  ink navy + cyan signal + emerald status; indigo/cream logo mark.
- The placeholder name "Jay B." on `about.html` — replace with the
  creator's real name/photo.
- `src/`, `vite.config.ts`, `tsconfig.json` are a legacy React scaffold
  from an earlier concept and are no longer used by the site.
