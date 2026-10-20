# Agora — website

The launch site for **Agora**, the new town square for free speech.
A human-first digital public square: zero ads, absolute chronology, strict
moderation of harm.

Pure **vanilla HTML / CSS / JS** — no frameworks, no build step. Serve the repository root locally to resolve root-absolute asset URLs.

## Pages

| File               | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `index.html`       | Home — hero, motive/philosophy, CTAs                                    |
| `shared-post.html` | Landing for shared post links (WhatsApp, etc.) when the app is not installed. Parses `?post=` / `?post_id=` / `?id=` and renders a preview stub until the backend is connected |
| `download.html`    | APK download, system requirements, version details, 3-step install guide |
| `about.html`       | Vision, Jayvardhan Bhaskar's creator bio, and the live feedback form     |
| `credits.html`     | Fixed-screen rotary team credits with synchronized off-screen discs and a pendulum role sign |

Shared assets:

| File               | Purpose                                            |
| ------------------ | -------------------------------------------------- |
| `style.css`        | Mobile-first design system for all pages           |
| `app.js`           | Routing, mobile menu, smooth scroll, reveals, feedback form, shared-post preview, dynamic download links |
| `functions/api/latest-release.js` | Cloudflare Pages Function that resolves the newest `.apk` from the Android repo's latest GitHub release |
| `assets/agora-logo.svg`      | Logo / tab icon                                    |
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

## Wiring up the backend

- `initSharedPost()` — `fetchPost(id)` is a stub returning a simulated
  payload after a delay. Replace with `GET /api/v1/posts/:id` when the API is live.
- `functions/api/contact.js` — Cloudflare Pages Function used by the About-page
  feedback form. It validates JSON or FormData, escapes the submitted values,
  and sends the message through Resend to `mail@agora.in.net`.
- `functions/api/latest-release.js` — Cloudflare Pages Function that proxies
  GitHub's `releases/latest` endpoint for the download buttons. See
  **Dynamic download links** below.
- Set `RESEND_API_KEY` as a Cloudflare Pages environment variable (and as a
  local secret when using `wrangler pages dev`). Never put the key in `app.js`
  or any browser-delivered file. The browser posts to `/api/contact`, shows
  `Sending...` while the request is in flight, and reveals the inline
  `Signal received` panel on a successful JSON response.

  A hidden honeypot field absorbs bots, and `SUBMIT_TIMEOUT` (12s) keeps a
  slow API request from hanging the button.

## Dynamic download links

Every download CTA downloads the newest `.apk` from
[`JayBhaskarCoding/agora-android`](https://github.com/JayBhaskarCoding/agora-android)
— **without JavaScript and without touching the GitHub API**. Shipping a build
means publishing a GitHub release; the website needs no edit at all.

### The load-bearing URL

```
https://github.com/JayBhaskarCoding/agora-android/releases/latest/download/app.apk
```

That is GitHub's permanent *latest-release asset* redirect. It resolves
server-side (302) to the `app.apk` attached to whichever release is newest at
click time, and GitHub serves release assets with
`Content-Disposition: attachment`, so the click starts a download instead of
opening a page. It never goes stale, needs no API quota, and works with JS
disabled, in a rate-limit outage, or on a host with no serverless functions.

> **Release requirement: the asset must be named `app.apk`.**
> The redirect is name-based, so a differently named asset makes it 404.
> `PREFERRED_APK_NAME` in `app.js` and `functions/api/latest-release.js` is the
> single place to change if that convention ever moves.

### Markup contract

A download CTA carries `.dynamic-download-btn` (the primary one on each page also
has `id="dynamic-download-btn"`) and its authored `href` is the redirect above —
never a tag-pinned `/releases/download/<tag>/…` URL:

```html
<a id="dynamic-download-btn"
   class="btn btn--primary btn--get-app btn--lg dynamic-download-btn"
   href="https://github.com/JayBhaskarCoding/agora-android/releases/latest/download/app.apk">
  Get the app
</a>
```

These anchors deliberately have **no** `data-page` attribute: `syncPageLinks()`
rewrites `a[data-page]` hrefs on every PJAX boot and would otherwise clobber the
download URL (it also skips `.dynamic-download-btn` explicitly).

### What the API lookup adds

`initDynamicDownload()` (run from `bootPage()` on first load and after every
route swap) is an *enhancement*, never the thing standing between a visitor and
the file. It does two jobs the redirect cannot:

1. **Resolve a differently named asset.** If a release ships `app-release-v1.apk`
   instead of `app.apk`, the redirect would 404 — the lookup finds the real asset
   URL and swaps it in. When the newest asset *is* `app.apk` the authored href is
   deliberately left alone, because it re-resolves at click time and so picks up a
   build shipped mid-session without waiting on a cache.
2. **Refresh the release facts** shown on the page (tag, filename, size).

Lookup order, cheapest first:

1. `sessionStorage` (`agora.latestRelease`, 15 min TTL) — one lookup per tab, so
   PJAX navigation re-applies with no network traffic.
2. `GET /api/latest-release` — the same-origin Pages Function, edge-cached for
   5 min, so visitors do not spend GitHub's unauthenticated 60 requests/hour/IP
   budget. Set an optional `GITHUB_TOKEN` Pages secret to raise it to 5,000/hour.
3. `GET https://api.github.com/repos/JayBhaskarCoding/agora-android/releases/latest`
   — direct, for hosts without Pages Functions (including `npm run dev`).

An exact `app.apk` asset wins; otherwise the first asset whose `name` or
`browser_download_url` ends in `.apk`. Only `https:` URLs are accepted, so a
malformed payload can never produce a `javascript:` href. Each request has an 8s
`AbortController` timeout.

### Failure is silent and safe

Network errors, 403/429 rate limits, a non-JSON response (what a static host
returns for `/api/latest-release`), a release with no `.apk`, or a missing `fetch`
all leave the authored redirect in place and log one `console.warn` — the button
still downloads. A failed lookup is remembered for 5 min so clicking around the
site does not keep re-hitting a rate-limited API.

Resolved buttons gain `.is-release-linked` plus a `title` naming the exact build,
and `[data-download-tag]`, `[data-download-file]`, `[data-download-size]` hooks
refresh the version facts on `download.html` and the size chips on `index.html` /
`shared-post.html` (their authored values are the no-JS fallback).

Local dev note: `python3 -m http.server` has no Functions runtime, so
`/api/latest-release` 404s with HTML and step 3 handles it. Use
`wrangler pages dev` to exercise the proxy itself.

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

## Theming (`style.css`)

The site follows the **operating system's** colour scheme. There is no toggle:
dark is the default fallback and light engages only inside
`@media (prefers-color-scheme: light)`, so an engine that ignores the query
still gets the dark theme unchanged.

### How a theme switch is one variable swap

Section 1 of `style.css` is a token layer, and it is split into **channels**
and **semantics**:

- **Channels** (`--accent-rgb`, `--overlay-rgb`, `--glow-rgb`, …) hold bare
  `r, g, b` triples. Every translucent tint in the file is written as
  `rgba(var(--x-rgb), <alpha>)`, so redefining a channel once re-colours all of
  its alpha variants.
- **Semantics** (`--bg`, `--surface`, `--text`, `--accent`, `--glass`, …) hold
  the colours components actually name.

The light theme therefore redefines ~56 tokens and **zero components**. Three
channels do the heavy lifting:

| Channel | Dark | Light | What it drives |
| --- | --- | --- | --- |
| `--overlay-rgb` | `255, 255, 255` | `15, 23, 42` | The glass inversion — every hairline, sheen, grid texture, glass panel and the credits-screen floating tags flip from white-based to dark-based translucency in one declaration. |
| `--glow-rgb` / `--glow-blue-rgb` | bright violet / blue | deep violet / blue | Neon bloom becomes a diffused drop-shadow. The alpha values stay as authored; only the colour depth changes. |
| `--rim-rgb` | `196, 181, 253` | `255, 255, 255` | The one channel that stays **bright** in both themes, because it edges a fill that stays saturated in both. Letting the rotary sign's rim follow `--lavender-rgb` would make it the same violet as the gradient stop underneath — 1.00:1, an edge that ceases to exist. It measures 5.57–7.25:1 in light. |
| `--bg-rgb`, `--surface-rgb`, `--text-rgb` | near-black / near-white | off-white / dark slate | Page, cards and typography. |

Section 23 holds the only per-site light overrides — the handful of effects
whose dark-tuned alpha (0.8–0.95 bloom) would read as a bruise on white. It
sits at the end of the file because those rules must win the cascade against
the components they tune.

### Deliberately not themed

- **`--device-*`** — the phone frame is hardware around dark app screenshots,
  so a pale bezel would read as broken rather than designed. Text painted
  *inside* the screen (`--device-ink`, `--device-accent-soft`) is pinned to the
  dark values for the same reason; letting it follow `--text-dim` would render
  the pending-state caption dark-on-dark.
- **`--mask-solid: #000`** — that black is an *alpha carrier* for `mask-image`,
  not a colour. It must stay opaque in every theme.
- **`--select-chevron`** — the dropdown arrow is an inline SVG, and a data URI
  cannot contain `var()`, so the whole URL is the token and each theme supplies
  its own. Note that a `%23`-encoded colour inside a URL hides from any
  "no hardcoded hex" scan; `test_light_theme_contract` guards that loophole.

Every *colour* in the file is tokenised — `box-shadow` and gradient
declarations contain no raw literals at all. What is deliberately left alone is
**lengths**: `backdrop-filter: blur(18px)` and the `saturate()`/`brightness()`
filters are theme-invariant geometry rather than colour, and `blur(18px)` is
pinned verbatim by `test_theme_contract`. Tokenising them would add indirection
with no visual difference in either theme.

### Canvas and browser chrome

The ambient dot matrix is painted on a `<canvas>`, which CSS cannot reach, so
`app.js` reads `--blue-rgb` / `--accent-rgb` back out of the stylesheet via
`getComputedStyle` and re-reads them on a `prefers-color-scheme` change. If the
tokens are unreadable it falls back to named literals rather than painting
`rgba(,0.05)`. Each page also carries three `theme-color` metas: an
unqualified fallback plus one per scheme.

### Contrast

`ThemeContrast` in `tests/test_site.py` measures WCAG 2.1 relative luminance
for every text/background pairing both themes render, and grades each token by
how it is *used* — 4.5:1 where it appears as a `color:`, 3:1 (WCAG 1.4.11)
where it only draws outlines, borders and icons. The light theme is held to AA
without exception; the dark theme is held to its shipped baseline, because
`--accent: #8B5CF6` and the brand gradient stops are pinned by
`test_theme_contract` and three dark pairings sit marginally under AA
(`--accent` on `--surface` at 4.33:1, white ink on the `#8B5CF6` and `#60A5FA`
gradient stops at 4.23:1 and 2.54:1). Baseline-locking means the dark palette
cannot regress unnoticed without redesigning a shipped brand colour as a side
effect of a theming change.

## Notes

- The feedback form on `about.html` uses the same-origin `/api/contact`
  Cloudflare Pages Function and Resend. Keep `RESEND_API_KEY` server-side; the
  direct email link below the form remains available as a human fallback.
- Brand lockup: the header and footer render the app-style mark **plus** the
  lowercase `agora.` wordmark (`.nav__logo-name` in `style.css`), including the
  violet period used inside the app. The same lockup is shared across every
  page; `shared-post.html`'s slim footer uses the `.nav__logo--compact` variant
  so it stays compact without changing the brand treatment.
- UI palette: deep dark surfaces, glass panels, and violet-to-blue gradient
  pill-shaped primary buttons with dark text for readable contrast. The same
  gradient carries the period in the `agora.` lockup, while the wordmark fades
  from full brightness on the left to roughly 74% visibility on the right.
  Original logo artwork is centralized at `/assets/agora-logo.svg` for
  replacement with the final approved export.
- Navigation is a lightweight vanilla-JS PJAX flow: internal HTML links are fetched,
  the target header/main shell is swapped in place, and history back/forward rehydrates
  the correct page without a full document reload.
- Ambient interaction uses `/assets/bgMusic.mpeg` as a softly filtered, low-volume
  looping Web Audio buffer. A single AudioBufferSourceNode and gain graph live outside
  the swapped page shell, so the track continues across PJAX navigation without a
  reset or volume spike. The first document click satisfies autoplay policy; the
  visible dot-matrix mesh breathes with the track. The custom cursor is limited to
  fine pointers and is disabled for reduced motion.
- `about.html` names Jayvardhan Bhaskar as the app and website developer and shares
  his motivation. The portrait is stored at `/assets/developer.png`; the avatar
  reserves space and shows a fallback if the image cannot load.
- `vite.config.ts` and `tsconfig.json` are unused legacy scaffold configuration.

## Launch handoff & validation

See [`assets/README.md`](assets/README.md) for the exact **3 screenshot files**
that fill all **6 placements**, logo replacement instructions, and APK handoff.
Old generated screenshot stand-ins have been removed; their frames remain and
show a pending message until real captures are uploaded. Do not add device frames.

All contact links use `mail@agora.in.net`. Exploratory CTAs say **Get the app**;
only the direct release action on `download.html` uses **Download APK**.

No page hard-codes a build any more. Every download CTA (header nav, mobile menu,
hero, closing panel, the download card, and the shared-post card) carries
`.dynamic-download-btn` and ships with GitHub's permanent latest-release redirect
(`…/releases/latest/download/app.apk`) as its `href`, so the click downloads the
newest build even with JavaScript off or the API rate-limited.
`initDynamicDownload()` in `app.js` additionally resolves the exact asset and
refreshes the on-page version facts — see **Dynamic download links** below.
Publishing a new GitHub release **with the asset named `app.apk`** is the whole
update process: no website edit, no version bump, no stale size copy.

```bash
npm test             # dependency-free HTML/asset/theme contract tests
node --check app.js  # JavaScript syntax validation
```

## Navigation and shared links

- “Why Agora” targets `/index.html#why-agora` (a local fragment on home).
  Its 5rem scroll margin keeps the fixed header clear of the section.
  Smooth scrolling honors reduced-motion preferences.
- `shared-post.html` is an external deep-link entrypoint, not a marketing page.
  No standard navigation or download-page buttons link to it; it is also marked
  `noindex, follow`. Existing `/post/:id` and `/p/:id` deployment rewrites remain.
  This isolates navigation, not access: anyone with a valid URL can open it.
- About values use scoped crimson/emerald accents. Other UI accents remain violet.
