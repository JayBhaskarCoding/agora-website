# Agora — website

The launch site for **Agora**, the new town square for free speech.
A human-first digital public square: zero ads, absolute chronology, strict
moderation of harm.

Pure **vanilla HTML / CSS / JS** — no frameworks, no build step. Serve the repository root locally to resolve root-absolute asset URLs.

## Privacy Policy — effective October 24, 2026

`privacy.html` is served at `/privacy`, with the same shared header, footer, fonts,
theme tokens and persistent PJAX shell as the main pages. All seven page footers
include a visible **Privacy Policy** link; credits uses its compact bottom colophon
without changing the wheel or contributor geometry. The policy has a linked contents
list, semantic sections, a canonical URL, and a readable text measure. Email links
use the existing runtime hydration mechanism, with readable no-JavaScript address
fallbacks, to avoid Cloudflare email-obfuscation breakage.

The policy describes the owner-supplied app architecture and practices: Supabase
Auth/Storage, Google One-Tap, public content, reports (including reporter email in
moderation alerts), Cloudflare/Resend, 30-day daily report/email cleanup via `pg_cron`,
age 13+, and registered-email account deletion requests. It also discloses the
website's actual contact-form fields, Google Fonts requests, and release session cache.

**Operational verification before publication:** the website does not implement or
verify the app's report collection, database cron, Agora Mail cleanup, account deletion,
or provider contracts. The operator must ensure these deployed systems match the
policy, especially permanent deletion of both database reports and notification emails.
This policy is not a claim of an independent legal compliance audit.

Known legacy `.html` URLs now have explicit 301 redirects to their clean routes ahead
of the 200 rewrites. Client boot normalization remains as a fallback for static servers.
No double-extension HTML filenames were found. No asset paths were changed.

## Clean URLs and local static-server support

Public page URLs are `/`, `/about`, `/download`, `/contact`, `/credits`, and
`/shared-post` and `/privacy`. The files remain `index.html`, `about.html`, `download.html`,
`contact.html`, `credits.html`, `shared-post.html`, and `privacy.html` on disk. Navigation, download
CTAs and the Android intent's browser fallback all use the clean paths. CSS,
JavaScript and `/assets/` references are unchanged.

`_redirects` explicitly rewrites the six extensionless page paths to their files
with status **200**, ahead of the catch-all. The enriched `/post/:id` and `/p/:id`
rules remain unchanged. Direct clean visits and refreshes therefore serve the right
page on Cloudflare Pages rather than the home-page fallback.

At boot, known `.html` aliases are replaced in the address bar with
`history.replaceState`, preserving existing state, query parameters and fragments.
PJAX normalizes both legacy and clean links before pushing history. Unknown routes,
assets, API requests and enriched share URLs are not treated as static page aliases.

On a basic local server such as `python3 -m http.server 5173`, start at `/` or a real
`.html` file. A PJAX request for `/contact` that returns **404** is retried as
`/contact.html`, with the same query and abort signal; history still records
`/contact`, never the fallback filename. Other HTTP errors are not silently retried.
A direct clean-path refresh on such a server still needs rewrite support: the browser
cannot run the fallback helper before the server has delivered the page.

The test suite checks route-to-file resolution, clean HTML links and CTAs, rewrite
ordering, legacy URL normalization, query/hash preservation, and runs the actual
JavaScript routing helpers against a mock static server to verify 404 fallback and
clean history updates.

## Pages

| File               | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `index.html`       | Home — hero, motive/philosophy, CTAs                                    |
| `shared-post.html` | Landing for shared post links (WhatsApp, etc.) when the app is not installed. On `/post/<id>` and `/p/<id>` the author card is rendered **server-side** from Supabase; `app.js` resolves the id from the **path** (with `?post=` / `?post_id=` / `?id=` as a fallback) and owns the chip, the error states and the Android intent link |
| `download.html`    | APK download, system requirements, version details, 3-step install guide |
| `about.html`       | Vision, Jayvardhan Bhaskar's creator bio, and the live feedback form     |
| `credits.html`     | Fixed-screen rotary team credits with synchronized off-screen discs and a pendulum role sign |

Shared assets:

| File               | Purpose                                            |
| ------------------ | -------------------------------------------------- |
| `style.css`        | Mobile-first design system for all pages           |
| `app.js`           | Routing, mobile menu, smooth scroll, reveals, feedback form, shared-post preview, dynamic download links |
| `functions/api/latest-release.js` | Cloudflare Pages Function that resolves the newest `.apk` from the Android repo's latest GitHub release |
| `functions/post/[id].js` | Cloudflare Pages Function serving `/post/<id>`: resolves the author in Supabase, renders the card into `shared-post.html`, and writes the per-post `og:*` / `twitter:*` tags |
| `functions/p/[id].js` | The `/p/<id>` alias — re-exports the same handlers so both routes agree |
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
- `http://localhost:5173/download`
- `http://localhost:5173/about`

`python3 -m http.server` does not process `_redirects`, so locally a pretty
`/post/<id>` URL 404s and the shared-link flow must be driven with the
`?post=` fallback. That asymmetry is exactly how the query-only parser shipped:
it looked correct on every local URL. See
[Shared post deep links](#shared-post-deep-links-postid).

## Deploy

The repository root **is** the static site. Point any static host
(Netlify, Cloudflare Pages, GitHub Pages, S3+CloudFront…) at the root and
keep `_redirects` / `robots.txt` in place. On a host that honours
`_redirects` (Cloudflare Pages, Netlify) the canonical share link is
`https://your-domain/post/<id>`; the `?post=<id>` form keeps working
everywhere, including on hosts with no redirect engine.

## Android App Links (`assetlinks.json`)

`/.well-known/assetlinks.json` is what lets `net.agora.app` auto-verify deep
links for `https://agora.in.net`. It lives at **`.well-known/assetlinks.json`
in the repository root** — not under `public/`.

That placement is the whole ballgame. The repository root *is* the published
site (see [Deploy](#deploy)), so a copy under `public/` is served at
`/public/.well-known/assetlinks.json` while the canonical URL falls through the
`/*` catch-all in `_redirects` and answers **200 with `index.html`**. Android
then receives HTML where it expects JSON, verification fails, and the Play
Console reports only a generic "not associated" error with nothing pointing at
the real cause. `AssetLinksContract` in `tests/test_site.py` fails if the file
moves or if `public/` comes back.

The file carries two SHA-256 certificate fingerprints — release and debug — so
a debug build verifies against the same domain without anyone editing the site:

```
28:46:3B:…:AE:E1:44   release
8C:F7:C9:…:9B:1E:58:4F   debug
```

`package_name` is **`net.agora.app`** — a chosen `applicationId`, *not* the site
domain reversed (that would be the earlier pin, which reverses to
`agora.in.net`). The reversal heuristic was a useful typo-catcher while it held,
and it no longer does, so
`test_package_name_is_one_agreed_identifier_everywhere` replaced it: it checks
the identifier is well formed and, more importantly, that `assetlinks.json` and
`app.js`'s `ANDROID_PACKAGE` name the **same** package. That agreement is the
invariant that actually matters — if they drift, the intent:// button targets an
app the statement never authorised, and it fails silently on exactly the devices
it was built for.

> **The app side is not there yet.** As of the `v1.0-Release` tag the APK still
> ships the scaffold placeholder `applicationId`, and its manifest auto-verifies
> against an alias domain with `pathPrefix="/post/"`. Until the app declares
> `net.agora.app` and `agora.in.net`, Android cannot verify this statement and
> the intent button falls back to the download page. Nothing on the site can
> compensate for that; see [What the app still owes](#what-the-app-still-owes).

`_headers` pins `Content-Type: application/json` and `nosniff` for the path,
because a wrong content type fails verification exactly as hard as a 404 does.
`Cache-Control` is one hour so a rotated signing key propagates quickly instead
of sitting in an edge cache.

### Rotating or adding a fingerprint

Regenerate from a keystore with:

```sh
keytool -list -v -keystore release.keystore -alias <alias> \
  | grep -A1 'SHA256:'
```

Then paste the value in **uppercase with colon separators** — the format Google
expects, and the format the tests enforce.

**If the app is enrolled in Play App Signing**, the certificate that matters is
the *app signing* key held by Google, not the local upload keystore. Read it
from Play Console → **Setup → App integrity → App signing key certificate**.
Publishing only the upload-key fingerprint is the single most common reason
auto-verification fails for an app that otherwise looks correctly configured.

### Verifying after deploy

```sh
curl -sS -D- https://agora.in.net/.well-known/assetlinks.json | head -20
```

Expect `HTTP/2 200`, `content-type: application/json`, and the JSON body — not
HTML, and not a redirect. Google's
[Statement List Generator and Checker](https://developers.google.com/digital-asset-links/tools/generator)
will confirm the association end to end. On-device, re-trigger verification with:

```sh
adb shell pm verify-app-links --re-verify net.agora.app
adb shell pm get-app-links net.agora.app    # want: verified
```

Note that Cloudflare Pages serves dot-prefixed directories from Git deploys,
which is what makes the root `.well-known/` work. If a future deploy target ever
skips hidden directories, the fix is a `_redirects` **200 rewrite** (never a
301/302 — Google rejects redirects on this path) from the canonical URL to a
non-dot copy, keeping a single source of truth.

## Shared post deep links (`/post/<id>`)

The Android app shares **pretty** links — `https://agora.in.net/post/<id>`,
plus the short `/p/<id>` — and `_redirects` rewrites both to
`shared-post.html`:

```
/post/:id          /shared-post.html          200
/p/:id             /shared-post.html          200
/*                 /index.html                200
```

### The trap: a 200 rewrite never changes the browser URL

Those are **200 rewrites**. The edge serves `shared-post.html`'s bytes while
the address bar stays `/post/<id>`, so the script sees:

```js
location.pathname === '/post/<id>'
location.search   === ''          // always empty
```

Writing `?post=:id` on the rewrite destination *looks* like it fills that in.
It does not — the destination query only steers the edge's internal file
lookup and never reaches the client. So a parser that read the query string
alone answered **"This link doesn't include a post id"** to every real share
link in production, while passing every local test (where the visitor types
`?post=` by hand). The destination query is gone from `_redirects` on purpose;
`test_rewrite_destination_carries_no_query_string` keeps it gone.

### The resolver contract (`app.js` → `resolvePostId`)

1. **Path first** — `/\/(?:post|p)\/([^/?#]+)\/?$/i` captures the segment.
   Tolerates a trailing slash and route casing, and does not false-positive on
   `/support/<x>`, `/app/<x>` or `/shared-post.html`.
2. **Query fallback** — `?post=`, then `?post_id=`, then `?id=`, for legacy
   links and for local dev.
3. **The first candidate that validates wins**, so an unreadable path segment
   never masks a usable `?post=` value.
4. **Decode, then validate** against `/^[A-Za-z0-9][A-Za-z0-9._=-]{2,127}$/`.
   Decoding first is what stops `%2F` smuggling a slash past the charset test,
   and `decodeURIComponent` is wrapped because a stray `%` throws. The charset
   is deliberately permissive — UUIDs, short hex, nanoid and base64url all pass.

`SharedPostRouting` in `tests/test_site.py` lifts those two regexes out of
`app.js` and compiles them, so the tests assert what the route *means* rather
than merely that a regex exists.

### Four states, decided by two different layers

| State | Decided by | Trigger | Copy |
| ----- | ---------- | ------- | ---- |
| author | the Function | the post exists and a profile was found | that member's avatar, name and handle |
| generic | the markup | the Function did not run, or found no profile | "A member of the square" |
| gone | the Function | Supabase answered and there is no such post | "That post is no longer available." |
| missing | `app.js` | no id anywhere in the URL | "This link doesn't include a post id." |
| invalid | `app.js` | an id that fails validation | "That link's post id doesn't look valid." |

A valid `/post/<uuid>` must never reach either client-side error state — that
was the bug. Telling someone their id is *missing* when the URL plainly carries
one sends them back to the app to re-share a link that was never broken.

Note the split: **the server owns the card, the client owns the id.** `app.js`
never writes `[data-author]` — if it did, it would overwrite the real member
with the generic fallback on every deep link, because it has no data to put
there. `test_app_js_never_renders_the_author` holds that line.

### The greeting is personalised, and the schema default is a trap

The `<h1>` carries the same server render:

```html
It looks like <span data-first-name>someone</span> shared a post with you.
```

Enriched, it reads *"It looks like Jayvardhan shared a post with you"*. Three
details are load-bearing:

- **The sentence stops there.** It used to end *"…but you don't have the app
  installed yet!"*, which the page cannot know — and which told a visitor who
  **does** have the app that they were wrong, before offering them any way in.
  That audience now gets the **Already have the app?** row described below, and
  the sentence no longer argues with it. `<title>`, `og:title`, `twitter:title`
  and both descriptions were reworded to match, because a chat preview that
  contradicts the page it links to is worse than a plain one.
- **The fallback is lowercase.** It sits mid-sentence, so a capitalised
  `Someone` would be a grammar bug on every link the Function does not enrich —
  which is the majority of them. `FIRST_NAME_FALLBACK` and the authored markup
  have to be the same word, or an unenriched page and an enriched page with no
  first name would read differently; `test_the_h1_is_personalised_and_grammatical_by_default`
  asserts both halves of that.
- **`profiles.first_name` is `text default 'User'`.** Every member who never
  chose a name stores the literal word `User`, so injecting it verbatim would
  announce *"It looks like User shared a post with you"*. The Function
  treats that placeholder (case-insensitively) as no first name and falls back
  to `someone`. The display name beside the avatar is **not** touched by this —
  it still shows what the app shows, `User Nandi`, so the guard is scoped to the
  sentence only.

`app.js` never writes `data-first-name`. The server owns the greeting for the
same reason it owns the card: a client-side write would race the render and, on
a deep link, lose.

### The author card is server-rendered, on purpose

A chat app scrapes a shared URL the moment it is pasted, long before anyone
taps it, and it never runs JavaScript. So the `og:*` / `twitter:*` tags have to
be correct in the very first response — a client-side fetch can never produce a
per-post link preview.

Since that lookup has to happen before the HTML is returned anyway,
`functions/post/[id].js` renders the author card into the same HTML:

- the avatar and name are in the **first paint**, with no flash of a generic
  name while a request is in flight;
- the card still reads correctly with **JavaScript off**;
- there is no `</script>`-escaped JSON blob to get wrong, because nothing is
  serialised — the values are written straight into element text and attributes.

The card is authored **visible**. The generic member is a truthful card for
every request the Function does not enrich (`?post=` and the other query
fallbacks, local dev, and any lookup that declines), so a visitor without
scripts gets an answer instead of a hole.

### Both routes are served, and they agree

`/p/<id>` is the short alias. `functions/p/[id].js` re-exports the long route's
handlers rather than duplicating them, so the two cannot drift into disagreeing
about who posted:

```js
export { onRequestGet, onRequestHead } from '../post/[id].js';
```

It is a real route file importing a sibling route file *on purpose*. Putting the
shared logic in `functions/_shared/` would depend on Pages excluding
underscore-prefixed paths from routing, and a share link is a poor thing to bet
on that detail.

`og:url` still names `/post/<id>` on **both** routes. Chat apps deduplicate
previews by `og:url`, so one post shared both ways has to produce a single card,
not two. `test_og_url_is_canonical_so_an_alias_makes_one_preview_not_two` holds
that, and `test_the_short_alias_delegates_rather_than_duplicates` fails if the
alias ever grows its own copy of the lookup.

### What the preview shows, and what it never shows

Who posted, and that a real post exists. Never the post text, its images, or
its like/reply counts — the page proves a person posted something and sends the
visitor to the app to read it.

That boundary is enforced as data, not as a comment. The Function reads two
allow-listed column sets:

```js
const POST_COLUMNS    = 'id,user_id,created_at';
const PROFILE_COLUMNS = 'handle,first_name,last_name,avatar_url';
```

`profiles` is world-readable under RLS, which means anyone holding the anon key
— and it ships inside every APK — can already read `email`, `dob`, `gender` and
the per-device push credentials. None of that is needed to draw an avatar, so
none of it is requested: `test_only_allow_listed_columns_are_ever_selected`
walks every `select=` the Function builds and fails if a forbidden column
appears in one.

Two traps worth knowing before touching this code:

- **`posts.user_id` carries TWO foreign keys to `profiles`** (`fk_posts_user_id`
  and `posts_user_id_fkey`), and PostgREST refuses an ambiguous embed with
  *"more than one relationship was found"*. The embed therefore names the
  constraint — `profiles!fk_posts_user_id(...)` — and because that hint goes
  stale if the constraint is ever renamed, the plain query remains as a
  fallback, with the profile then read separately.
- **Storage has no SELECT policy on `storage.objects`.** Anonymous avatar reads
  work only while the `avatars` bucket stays public, so the avatar is treated as
  best-effort: the frame always paints the member's initial underneath, and
  `initAvatarFallback()` swaps the image in only once it has really loaded
  (`complete` *and* `naturalWidth > 0` — a broken image reports `complete` too).
  A failed avatar degrades to the initial, never to a broken-image glyph.

### Failure is a fallback, never an error

This response blocks first paint, so it is on a tight leash and every unhappy
path hands back the static page:

| Situation | Behaviour |
| --------- | --------- |
| no `SUPABASE_URL` / `SUPABASE_ANON_KEY` | `context.next()` — static page, untouched |
| id is not a UUID | `context.next()`, and Supabase is never queried |
| timeout (1500 ms), 5xx, non-JSON body, thrown error | `context.next()` |
| `ASSETS` missing or 404 | `context.next()` |
| post not found | the "no longer available" card, `200` |

A shared link must never 500 because a preview lookup was slow.
`test_no_failure_path_can_return_an_error_page` counts the real `return
context.next()` statements and asserts the handler *ends* with one, so an
unexpected throw cannot become a 5xx either.

Responses are cached at the edge for 300 s but sent to the browser with
`max-age=0`, so a scraper hitting within seconds of the share gets the enriched
card while a visitor refreshing after a deletion sees it go away.

A full UUID is 36 characters and would blow out the mono chip, so the chip
shows the leading group and keeps the whole value in its `title`. The id is
URL data on a publicly reachable page, so it reaches the DOM through
`textContent` only — never `innerHTML`.

### Opening the app from the landing page

When `assetlinks.json` verification is working, a device **with** the app
installed hands `/post/<id>` straight to Android and this page never loads —
but verification only completes on the *first* tap after install, and plenty of
visitors arrive through a stale tab, an in-app browser, or a link forwarded
somewhere that strips App Links. For them the hero carries a second row:

```html
<p class="shared-card__have-app" id="open-in-app-row" hidden>
  <span>Already have the app?</span>
  <a class="btn btn--ghost btn--sm" data-open-intent-btn …>Open this post in Agora</a>
</p>
```

It lives in the hero beside **Get the app**, not in the preview card where the
button it replaced used to sit: it answers a question about the *visitor* (do
you already have the app?), not about the post, and under the fold it was
effectively invisible on a phone. There is exactly one such button on the page —
`test_the_open_in_app_row_lives_in_the_hero_not_under_the_fold` counts them.

On Chromium/Android it becomes an `intent://` URL for the same https path:

```
intent://agora.in.net/post/<id>#Intent;scheme=https;package=net.agora.app;S.browser_fallback_url=https%3A%2F%2Fagora.in.net%2Fdownload.html;end;
```

Android routes it to the verified app; if the app is absent it opens
`browser_fallback_url` (the download page) instead.

**Two gates, deliberately different.** `isAndroid()` decides whether the row
exists for this visitor at all; `supportsIntentUrls()` decides which URI it
gets. Collapsing them is wrong in both directions:

- Revealing the row everywhere would promise an app the device cannot install —
  Agora is Android-only, and on iOS or desktop the **Get the app** CTA above
  already covers the visitor. So the row stays hidden off Android.
- Giving *every* Android browser an `intent://` URI would hand Gecko a scheme it
  ignores entirely, with a `browser_fallback_url` it also ignores — a dead
  button. So non-Chromium Android gets `buildAppWebUrl()` instead: the plain
  `https://agora.in.net/post/<id>` App Link, which Android itself offers to the
  app. Every Android browser therefore ends up somewhere useful, and the two
  paths differ only in who performs the handoff.

`test_intent_package_matches_the_asset_links_statement` pins the package to
`assetlinks.json`, because an intent aimed at a stale package fails silently on
exactly the devices it was built for.

The row is authored `hidden` and only JS reveals it, so its stub
`href="/download"` is never seen — unlike the old card row, which was
authored visible-capable and needed that href as a pre-JS fallback.
`test_every_id_init_shared_post_looks_up_exists_on_the_page` binds each
`getElementById` in `initSharedPost` to an id the page actually authors, because
a rename on one side alone fails silently: the lookup returns `null`, every
`if (row && btn)` guard degrades to a no-op, the page still renders, and every
source-level assertion still passes.

`app.js` finds the button by its `data-open-intent-btn` hook. The host in that
URI is `CANONICAL_HOST`, **pinned** to `agora.in.net` rather than derived from
`window.location.host`: the manifest only auto-verifies the one host, so an
intent built on a `*.pages.dev` preview or on localhost could never hand off to
the app — it would fail with no fallback at all. `browser_fallback_url` *is*
origin-relative, because that one should land on whichever deployment the
visitor is actually on. `buildAppWebUrl()` uses the same pinned host, since a
verified App Link only verifies against the host the manifest declares.
`test_canonical_host_matches_the_verified_domain` is the drift lock, mirroring
the package one above.

`postId` still goes through `encodeURIComponent` even though the intent syntax
would take it raw: `resolvePostId`'s charset permits `=`, which is a delimiter
inside an intent URI. For a UUID the encoding is a no-op, so the emitted string
is byte-identical either way.

### Every domain, one canonical URL

`agora.in.net`, `auth-agora.info` and `auth-agora.online` are all owned and all
point at this same Cloudflare Pages project. That is convenient for visitors and
a trap for social tags: `og:url` used to be built from the *request's* origin, so
one post shared from two of those hosts published two different canonical URLs —
and because chat apps key their preview cache on `og:url`, the same post rendered
as two unrelated cards in a single thread.

`CANONICAL_ORIGIN` in `functions/post/[id].js` is now the only basis for any
absolute URL the Function emits (`og:url`, `og:image`, `twitter:*`), so all three
domains publish identical tags, and `/p/<id>` and `/post/<id>` agree on top of
that. `test_every_absolute_url_is_pinned_to_the_canonical_host` also asserts the
request-origin helper is *gone* rather than merely unused — leaving it in place
invites the next tag to be built from the wrong host.

The alias domains are deliberately not named in any served file, so
`test_no_superseded_identity_survives_in_served_files` fails if one is ever
emitted into a URL. This section is the only place they are written down.

### What the app still owes

The site is now correct for the released product's intended identity; the APK is
not yet. Four changes in the app repo make deep links actually work. Until they
land, share links still open this page (all three domains serve it), but they
never hand off to the app:

| Where | Now | Needs to be |
| --- | --- | --- |
| `app/build.gradle.kts` | scaffold placeholder `namespace` / `applicationId` | `net.agora.app` |
| `AndroidManifest.xml` | `autoVerify` filter on an alias domain, `pathPrefix="/post/"` | `android:host="agora.in.net"`; consider adding `/p/` |
| `FeedScreen.kt` share intent | builds the share URL from an alias domain | `https://agora.in.net/post/${post.id}` |
| `DeepLinkRouter.kt` | matches only the alias host | match `agora.in.net`, and keep matching the old host so links already in the wild still open |

Changing `applicationId` makes the app a **different identity**, so existing
installs will not update in place — they reinstall. The release currently shows
two downloads, which makes now the cheapest moment this will ever be.

### Verifying after deploy

`/post/<id>` must serve the landing page, **not** fall through to `/*`. Both
answer `200 text/html`, so check for a marker unique to this page:

```sh
curl -sS https://agora.in.net/post/<uuid> | grep -c 'id="post-preview"'   # want: 1
curl -sS -o /dev/null -w '%{http_code} %{url_effective}\n' \
  https://agora.in.net/post/<uuid>                                        # want: 200, URL unchanged
```

`0` means the `/post/:id` rule did not apply and the catch-all served
`index.html`. A changed `url_effective` means something redirected (3xx)
instead of rewriting. Then open the link in a browser and confirm the chip
reads `post #<first 8 chars>` with no error copy.

The card and its link preview are separate checks — the page can be served
correctly while the Function stays unconfigured:

```sh
# The author, not the generic fallback:
curl -sS https://agora.in.net/post/<uuid> | grep -o 'data-author>[^<]*'
# The per-post social tags a chat app scrapes:
curl -sS https://agora.in.net/post/<uuid> | grep -oE '<meta property="og:(title|image)"[^>]*>'
```

A generic `A member of the square` plus the site's static `og:title` means the
Function ran but found no credentials — check `SUPABASE_URL` and
`SUPABASE_ANON_KEY` in the Pages project. Paste the link into a chat app to
confirm the card renders the avatar; that is the behaviour the whole Function
exists for.

## Wiring up the backend

- `functions/post/[id].js` — Cloudflare Pages Function that owns `/post/<id>`,
  resolves the author in Supabase and renders the card plus the `og:*` tags into
  `shared-post.html`. See **Shared post deep links** above. It needs two
  environment variables, and treats their absence as "serve the static page":

  | Variable | Value |
  | -------- | ----- |
  | `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
  | `SUPABASE_ANON_KEY` | the project's **anon / publishable** key |

  Set both in *Cloudflare Pages → Settings → Environment variables*, and as
  local secrets when using `wrangler pages dev`. The anon key is a public
  client identifier — it already ships inside every APK — but it still belongs
  in the environment rather than in the repo, so the project can be rotated
  without a commit. **Never** set `SUPABASE_SERVICE_ROLE_KEY` here: this
  Function reads only what RLS already publishes.

  `initSharedPost()` in `app.js` no longer fetches anything. It resolves the
  id, sets the chip, decides the missing/invalid states, wires the avatar's
  load-or-fallback swap, and reveals the `intent://` row.
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

**Exactly one element on the whole site downloads the APK**: the *Download APK*
button on `download.html`. Every other *Get the app* CTA — the header button, the
mobile-menu button, the home hero, the home closing panel, the About panel and
the shared-post card — is ordinary navigation to `/download`, so the install
decision happens on the one page that carries the version, size and requirements
next to it. Those links are PJAX-routed like any other internal link.

That one button downloads the newest `.apk` from
[`JayBhaskarCoding/agora-android`](https://github.com/JayBhaskarCoding/agora-android)
**without JavaScript and without touching the GitHub API**. Shipping a build
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

Two kinds of CTA, and the difference is load-bearing.

**The one download button** (`download.html` only) carries
`.dynamic-download-btn` and `id="dynamic-download-btn"`, and its authored `href`
is the redirect above — never a tag-pinned `/releases/download/<tag>/…` URL:

```html
<a id="dynamic-download-btn"
   class="btn btn--primary btn--lg btn--block dynamic-download-btn"
   href="https://github.com/JayBhaskarCoding/agora-android/releases/latest/download/app.apk">
  Download APK
</a>
```

It deliberately has **no** `data-page` attribute: `syncPageLinks()` rewrites
`a[data-page]` hrefs on every PJAX boot and would otherwise clobber the download
URL (it also skips `.dynamic-download-btn` explicitly).

**Every other CTA** is a plain internal link using the repo's normal routing
convention, so it works with JS off and is swapped in place by PJAX when JS is
on. These must *not* carry the dynamic marker, or `applyReleaseToPage()` would
turn them back into a direct download:

```html
<a class="btn btn--primary btn--get-app btn--lg"
   href="/download" data-page="download">
  Get the app
</a>
```

`test_download_ctas` and `test_only_the_download_page_exposes_the_asset` enforce
both halves: exactly one element site-wide may carry the release href or the
marker, and every other CTA must resolve to `/download`.

### What the API lookup adds

`initDynamicDownload()` (run from `bootPage()` on first load and after every
route swap) is an *enhancement*, never the thing standing between a visitor and
the file. It bails out unless the page has a download button **or** a
`[data-download-*]` facts hook — which matters now, because `index.html` and
`shared-post.html` display the size but no longer carry a button. Keying off the
facts too is what keeps those chips live instead of frozen at their authored
fallback. It does two jobs the redirect cannot:

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
`/assets/…`, `/download`). This is deliberate: shared links arrive with
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


## Credits rotary geometry

`credits.html` is the one screen whose correctness is arithmetic rather than
markup. Two wheels sit on opposite viewport corners, each carrying three
contributors in 120-degree sectors. Everything below is load-bearing: change a
number without re-deriving it and the screen still renders, still animates, and
silently describes the wrong person, overflows the viewport, or collides with its
own labels.

### One equation decides where the copy lands

The plate rotates by `--disc-rotation`, each segment counter-rotates by its own
`--segment-angle`, and the detail block counter-rotates again. Those cancel, so
the **settled** block always lands at:

```
landing = hub + rotate(v, --sector-offset)
```

where `v` is the block's offset from the disc centre and `hub` is where the
wheel's centre sits. It does not depend on which member is showing, which is why
the whole layout is two numbers per breakpoint instead of six per wheel.

`v` is measured from the block's **centre**, not its corner, because
`.rotary-segment__content` starts its transform with `translate(-50%, -50%)`.
Hung from a corner, the landing point moves with the block's own height and one
extra line of bio shoves it through the viewport edge. Centred, it is exact at
any `--segment-scale`.

| Block | Breakpoint | `top` | `left` |
| --- | --- | --- | --- |
| contribution (upper wheel) | desktop | `58%` | `76%` |
| profile (lower wheel) | desktop | `64%` | `76.5%` |
| contribution | `max-width: 768px` | `85.5%` | `108.5%` |
| profile | `max-width: 768px` | `84.5%` | `103.5%` |

**Each block carries its own arm**, and that is a geometric necessity rather than
a stylistic choice. With the sectors exactly 180 degrees apart and the hubs on
opposite corners, one shared `v` forces `top = hub + u` and `bottom = hub' - u`,
so a single arm can only reach two boxes that mirror each other about the
viewport centre. These do not: they differ by ~48px horizontally and ~36px
vertically at 1440x900. Sharing an arm split that error across both blocks and
left the profile block ~74px short of its zone. `--sector-offset` (`40deg` upper,
`220deg` lower) still decides which *direction* each arm points.

### The hubs are inset, and that inset is the sector-utilisation dial

```css
.rotary-disc--top    { transform: translate(-44%, -44%); }
.rotary-disc--bottom { transform: translate( 44%,  44%); }
```

Both breakpoints share these — the narrow-screen block deliberately declares no
hub override. Pinned to the exact corners (`-50%`) only **19.7%** of each wheel
was on screen and the middle of the viewport was dead space; narrow screens were
worse, pushed to `-65%` so each hub sat 15% of the disc *off-screen* and only
**7.3%** of the wheel showed. At `-44%` it is **25.8%** on desktop and **26.0%**
on a phone.

`-44%` is also the limit. Past it the two rims intersect on the tighter
viewports — at `-42%` they overlap by 42px on 1024x768 — and the sector lines of
one wheel draw across the face of the other. The worst-case clearance at `-44%`
is `+24px`, and a test asserts it never goes negative on any of the 14 viewports.

### The sector angles are not in order, on purpose

```
top    --segment-angle:  40deg, 280deg, 160deg     (= 40  - 120i)
bottom --segment-angle: 220deg, 340deg, 100deg     (= 220 + 120i)
```

Read as a list they look shuffled, and the temptation to "tidy" them into
`40, 160, 280` is exactly the bug. They are dictated by `indexForRotation()`
(`round(rotation / 120) % 3`) and by the lower wheel turning the other way
(`bottomRotation = -state.rotation`). The invariant is
`A_i == --sector-offset -/+ 120i`.

A useful consequence: the three **landing directions** per wheel are always
`{40, 160, 280}` and `{220, 340, 100}` no matter which member is settled,
because `A_i -/+ 120m` reduces to the same three angles. That is what makes
collision checking exhaustive rather than sampled.

### The stylesheet is the only source of those numbers

They used to exist in four places: `--segment-angle` in CSS, two hardcoded JS
arrays (`TOP_SEGMENT_ANGLES`, `BOTTOM_SEGMENT_ANGLES`), and two literal
active-centre arguments (`40`, `220`). A drifted copy does not throw — it puts
the scale-and-opacity emphasis on the wrong contributor while the wheel keeps
turning and snapping normally.

`initCreditsRotary()` now reads them back with `getComputedStyle`. If the read
fails, `anglesReadable` is false and the JS emphasis is skipped entirely rather
than guessed — the `.rotary-segment.is-active` rule still scales and fades the
settled segment on its own, so the screen degrades instead of misplacing.

### Four hard constraints, solved not eyeballed

The offsets come from a search over 14 viewports subject to:

1. **Safe area** — clear of the edges (24px), the header, and the status bar.
2. **Zone** — upper wheel lands upper-left, lower wheel lower-right.
3. **No block-on-block overlap** between the two contributors.
4. **No block-on-label overlap.** The hanging role sign and the name plate sit on
   the same ray as their own block, and the sign hangs straight *down in screen
   space* while the ray points wherever its sector does — so on an upward-pointing
   ray the sign swings back toward the copy. Checked on all three rays per wheel,
   with the two non-settled blocks measured at the `0.6` scale they really render
   at.

Constraint 4 is the binding one, and it is invisible without modelling it: the
previously shipped offsets passed 1-3 comfortably and still put a role sign
across its own contribution text on the upward ray.

Those four are hard constraints. The **objective** is the distance from each
block's landed centre to the box the design review asked for — description at
`left: clamp(24px, 2.8vw, 48px)` / `top: clamp(140px, 22vh, 220px)`, profile
block right-aligned at `clamp(20px, 2.2vw, 40px)` and centred in the `42vh`-`82vh`
band. A rotary cannot teleport a block to an arbitrary viewport box, so the
solver minimises the residual instead of matching exactly: worst case **122px on
desktop, 96px on a phone**, asserted per viewport by
`test_the_blocks_reach_the_requested_viewport_boxes`.

A fifth candidate constraint was dropped on purpose. "The block's farthest corner
stays inside the wheel rim" is satisfiable on desktop (119px of clearance) but
**provably impossible on a phone**: a 230px block inside a 421px disc leaves 57px
of reach while the header and padding need 184px. Enforcing it there yields no
solution at all, so narrow screens solve against 1-4 only.

The requested widths are floored for the same reason. Bare `min(23vw, 340px)` is
90px on a 390px phone — about eleven characters a line — and bare
`min(17.5vw, 260px)` is 68px, narrower than the 110px avatar it has to contain.
Both are therefore `min(max(<vw>, <floor>), <cap>)`, and the narrow-screen block
declares no width of its own, so the solver only ever has one set of numbers to
reason about.

### Role signs hang from their own segment

The three upper-wheel signs were once positioned by hand with per-index
`top`/`left`, and two of the three were a full 120 degrees away from the sector
they described — in the base rule **and** in the mobile rule. Hand-authored
coordinates per index are the bug class, not just the bug.

Each sign now lives inside its own `[data-rotary-segment]` and inherits
`--segment-angle`, the way the lower wheel's name tags always did:

```css
.rotary-sign-hanger {
  top: 50%;
  left: 99.7%;   /* 49.7% of the disc out from the hub */
  transform: translate(-50%, 0)
    rotate(calc(0deg - var(--segment-angle, 0deg) - var(--disc-rotation, 0deg)
              + var(--tag-swing-angle, 0deg)));
  transform-origin: 50% 0;   /* the pivot is the cord, not the sign */
}
```

It has to subtract **both** ancestors' rotations, or it comes out tilted by its
own sector angle. On narrow screens only `left` changes (`91.2%`, a 41.2% orbit).
`.rotary-tag-track` is gone; a sibling track is what let the signs drift.

`.rotary-segment` also no longer sets `overflow: hidden` or a wedge `clip-path`.
The wedge looked tidy and silently truncated copy at narrow viewports (corners
reach 64-78 degrees against a 60-degree limit), and a clip-path is invisible in a
text diff. `.rotary-disc__sector-track::before` is `z-index: 1`, below the detail
blocks at `4`; at `5` the decorative radial lines drew across the text.

### The backdrop: one canvas, triangulated, autonomous

**One** canvas sits behind this screen and behind every other page on the site. It is
a jittered grid subdivided into triangles — not a square lattice, and not a true
Delaunay. The topology (how far each vertex sits off the lattice, and which diagonal
each cell splits along) is hashed from `(row, column)` once per resize, so it is
identical every frame; a triangulation recomputed per frame would boil, and
Bowyer–Watson on ~600 moving points is not survivable on a phone.

Cell size is `54px` on desktop and `38px` under 600px: ~600 vertices, ~550 triangles
and ~1700 edges at 1440×900, drawn in **two** `stroke()` calls.

It is **not connected to the audio engine**. Nothing in `initAmbientMesh` reads the
`AnalyserNode`, a frequency array, or any band metric, and there is no path by which
it could — the field is a pure function of vertex position and an integrated clock.
That is a reversal of the previous three rounds, in which bass, treble, onset, pitch
and centroid all drove it, and it buys three things at once: the animation is
identical whether the music is playing, paused, muted or unsupported; four of the five
pages now run **no audio analysis at all**, because the credits wheel driver is the
only remaining consumer and it early-returns off that page; and the frame has no
branch depending on a value from another subsystem.

Calibrated six times. All six rows are recorded because the numbers are load-bearing
and the direction of travel is not guessable from the end state — it has reversed
three times, and the middle row was a deliberate over-correction that a later review
pulled back.

| | vertices | lines | motion |
| --- | --- | --- | --- |
| original | 0.7-1.25px @ 0.045-0.13 | ≤ 0.13 | 0.12 cell |
| "too faint" review | 2-4.5px @ 0.75-0.95 | 0.28-0.45 | 0.26 cell |
| one mesh, first pass | 1.5-2.2px @ 0.25-0.35 | 0.15-0.20 | 0.26 cell |
| unified, frequency-budgeted | 1.5-2.2px @ 0.25-0.30 | 0.15-0.20 | up to 0.75 cell |
| smooth flow + audio droplets | 1.5-2.2px @ 0.25-0.30 | 0.15-0.20 | flow 0.24 cell |
| autonomous noise, "make it pop" | 2-3px @ 0.45-0.60 | 0.36-0.43 | 0.42 cell |
| dimmed for readability | 1.5-2px @ 0.16-0.22 | 0.07-0.10 | 0.42 cell, autonomous |
| **current** (elevation-shaded) | **1.5-2.0px @ 0.06 / 0.18 / 0.35** | **0.03 / 0.10 / 0.24** | **0.42 cell, autonomous** |

Hold the current row, and read it as three numbers rather than a range: trough, flat
baseline, crest. Note what it is: the seventh calibration, and the third reversal.
The band has now been "under 0.13, stay subtle", "at least 0.28, be prominent", a narrow
0.15-0.20, "0.35-0.45, make the lattice eye-catching", and 0.07-0.12 — which is very
nearly where it started. Every row is recorded rather than overwritten, because each was
a deliberate review decision and the next one should be able to see the whole path
instead of discovering it by accident. The opacities are roughly double what three consecutive rounds
pinned, and the vertex radius is up from 1.5-2.2px. Both are `Math.min` ceilings, and
both ramps *reach* their ceiling exactly — a `Math.min` that never binds is decoration,
and a calibration comment describing a range the code does not produce is worse than no
comment. Measured on the real code path: lines 0.360 and 0.430, vertices 0.4500-0.5843
alpha at 2.00-2.90px.

Because the mesh sits directly behind body copy, the numbers that matter are not the
mesh's but the copy's. `test_the_scrim_outweighs_the_mesh_at_its_brightest` computes the
contribution paragraph's contrast against the brightest thing the mesh paints, in both
themes, with and without the scrim, reading the alphas out of `app.js` rather than
restating them — it used to hardcode 0.30 and kept passing at half the real brightness
after the calibration moved, which is what a guard that hardcodes the number it guards
looks like. At the current calibration:

| | paragraph on the bare mesh | through the scrim |
| --- | --- | --- |
| dark | **5.59:1** (AA) | **7.59:1** (AAA) |
| light | **4.96:1** (AA) | **6.92:1** (AA) |

Both clear AA *without* the scrim, which is the actual requirement — body text and
headings effortless to read — and the scrim is insurance again rather than structure. It
is therefore back to the `0.9/0.6` it shipped with, after one round at `0.93/0.74` when
the mesh was at 0.45-0.60 alpha and the paragraph measured 2.39:1 on the bare mesh with
the scrim doing all the work. The floor behind the scrim stays strict at 6.0, so the next
brightness increase fails here instead of shipping.

**Glow is a pre-rendered gradient sprite, not `shadowBlur`.** The brief offered either;
this takes the gradient, and the choice is not aesthetic. At ~600 vertices and 60fps,
per-vertex `shadowBlur` is 36,000 of the most expensive calls a 2D context has per
second, re-rasterised every frame because the vertices move. `makeGlowSprite()` bakes
the same radial falloff into an off-screen canvas once per colour and `drawGlow()`
blits it. `bloom` is up from 0.42 to **0.78** and `spread` from 1.9 to **2.8** — a real
halo now, but still under 1.0, which was the original `shadowBlur` 8-12 look and past
which a vertex lights up its whole neighbourhood and reads as glare.

Which sprite a vertex uses is **static**: one in four gets the brighter texture, decided
by its lattice position and never changed. A version of this switched on a moving
threshold, and vertices popped between two baked textures as a crest passed under them —
that popping reads as flicker no matter how smooth the geometry is. All continuous
variation lives in alpha and radius, which cannot pop.

**`--mesh-ink` is one dial on how hard the layer presses, and both themes currently sit
at 1.** That is a consequence of the calibration, not an oversight: when the alphas were
0.45-0.60, light needed 0.55, because violet-800 at that strength over off-white measures
3.02:1 and prints a lavender graph across body copy. At the current bands the deepened
light channels land in the same place as dark on their own — at the crest, line 1.46:1
against 1.29:1 and vertex 1.83:1 against 1.83:1, a parity of 0.999 — so scaling back would
make light *fainter* than dark for no reason. The dial stays, and the test asserts the
**outcome** (both themes within 0.75-1.35× of each other, measured at the crest) rather
than the dial's value, so it survives either arrangement and survives a palette change.

**Glow is back to a soft edge.** `bloom` 0.78 → **0.30** and `spread` 2.8 → **1.8**. There
has never been a literal `shadowBlur` in this file — at ~600 vertices and 60fps that is
36,000 of the most expensive calls a 2D context has per second — so "remove the heavy glow"
means turning the sprite's bloom down, which is one constant precisely because the glow is
pre-rendered.

### Autonomous motion: multi-octave value noise

The displacement field is 3D value noise summed as fBm — four octaves at 560/292/152/79px
texels with a 0.5 gain — sampled at `(x, y, t)`. Value noise rather than Simplex because
it needs one hash per corner and two lerps per axis instead of a skew, an unskew and a
gradient table, and at this scale the difference is invisible. Its known weakness, faint
alignment along the lattice axes, is suppressed by the advection: the sample grid is never
stationary relative to the texel grid.

The interpolant is Perlin's improved **quintic**. That is not a refinement — a cubic or
linear one has a discontinuous second derivative at every texel boundary, which reads as
a faint grid pulsing through the motion. It is the exact artefact this is meant to avoid.

On top of the morph the domain is **advected**, `NOISE_DRIFT_X = 240` px/s in +x and
`-84` in y. Both together are what make it read as liquid: advection alone slides a rigid
pattern, morphing alone makes the field pulse where it stands. `dx` and `dy` sample
regions `NOISE_SEED = 41.3` apart, so they are decorrelated — sampling the same region for
both makes every vertex travel along one diagonal instead of looping.

#### Every mover is integrated, never multiplied by the clock

```js
driftX    += NOISE_DRIFT_X * dt;      // not: driftX = time * NOISE_DRIFT_X
noiseTime += NOISE_TIME_SCALE * dt;
var dt = clamp((timestamp - lastTimestamp) / 1000, 0, MAX_FRAME_DT);   // 0.05s
```

A rate can be applied two ways and one of them is a landmine. `position = time * rate` is
correct only while the rate never changes; the moment it does, the position jumps by
`time × Δ`, and after a minute open that jump is the whole field teleporting. Two rounds
ago the mesh did exactly that, with the rate derived from the dominant pitch: **239
radians of jump after a minute**, worse the longer the page stayed up. Nothing is
audio-derived now so the rates are constants and either form would work — but the
integrated form is kept, because the discipline is what survives the next person adding a
rate that varies.

`dt` is clamped for the same reason from the other side: a backgrounded tab hands back a
several-second timestamp, and integrating it unclamped flings the field across the screen
on return. Measured now: **0.695px peak** per-vertex motion across 420 frames, and
**2.41px** returning from a 9-second tab.

#### The advection sign — the third backwards direction in this file

A feature at noise coordinate `N` appears on screen where the sample coordinate equals `N`:

```
(gx - driftX) * NOISE_SCALE = N   ->   gx = N / NOISE_SCALE + driftX
```

so `d(gx)/d(driftX) = +1` and the feature travels in **+x** as `driftX` grows. With a plus
sign in the sample it is `gx = N/NOISE_SCALE - driftX` and the whole field runs left.

It shipped that way, and the harness reported it as *"stationary"* rather than as
*"backwards"* — because the shift search only looked at positive lags, and the correct lag
was negative. Widening the search to both directions turned a null result into a sign
error. Measured after the fix, cross-correlating a lattice row against itself 960ms later:
peaks at **+4 columns = +225 px/s** against a declared 240, correlation 0.584 unshifted →
**0.819** shifted in +x → **0.048** shifted the other way.

That is the third time. `sin(k*x + w*t)` in the layer this replaced; `sin(time*0.23 +
column*0.17)` in the idle drift after that, which was the loudest term in silence so the
one wave every visitor saw with the music off travelled backwards; and now a domain
advection sign. All three look identical frame to frame, which is why each one is now
derived in a test rather than pattern-matched.

#### Jitter is gentle because it is the expensive kind

Per-vertex jitter is 0.06 of a cell, down from 0.12 and 0.22 before that. Jitter is the one
term whose wavelength *is* one cell, so it spends `2 × JITTER` of the tear budget
unconditionally before the noise field moves anything. The random **diagonal lean** carries
most of the organic character for none of that cost, because a diagonal is a topology choice
rather than a displacement.

#### Displacement is budgeted by gradient, from a theorem

Two neighbours cross only when their displacements *differ* by more than the gap between
them, so a broad swell cannot tear the lattice however far it carries a vertex. The map
`x ↦ x + u(x)` is injective and orientation-preserving whenever the operator norm of the
displacement gradient is under 1, and the Frobenius norm bounds the operator norm — so
`sqrt(sum of the four squared partials) + 2·JITTER < 1` is a sufficient condition for "no
triangle inverts".

For value noise the per-axis partial is `amplitude × gradient`, and a quintic-interpolated
texel whose corners span −1..1 peaks at 3.75 per texel (`fade'` maxes at 1.875), summed over
octaves at their normalised weights. That gives **0.628 against a `TEAR_LIMIT` of 0.75** —
a 25% allowance below the theorem's 1.0 — recomputed from the constants on disk by
`test_the_tear_budget_covers_every_term`, so any amplitude, octave-count or lacunarity bump
fails there.

The bound is roughly 3× pessimistic: it wants every octave's corners at opposite extremes
and all four partials peaking at the same vertex. Measured, the lattice uses about a fifth
of the available deformation — **0 inverted triangles in 231,420 sampled cells, minimum
signed area 81% of a cell**. The arithmetic catches an amplitude bump in review; the
measurement catches everything else.

One trap worth recording: `fbm()` dividing by its normaliser is load-bearing. Delete the
`/ norm` and the field's range grows 1.875×, so **every** amplitude — and therefore the
gradient, the velocity and the tear spend — is silently 87.5% bigger than the arithmetic
says, with no constant changing. That mutation survived the first sweep.

### Opacity follows elevation, in five buckets

A mesh at a uniform opacity has to be bright enough to see, which is bright enough to
fight the type — that tension is what the last three calibrations kept flipping
between. Shading the surface by its own height resolves it: the flat majority can sit
at 0.10 while only the crests reach 0.24, so the lattice reads as a lit surface with
relief rather than as a grid printed over the page.

| band | 0 trough | 1 | **2 flat** | 3 | 4 crest |
| --- | --- | --- | --- | --- | --- |
| line alpha | 0.03 | 0.07 | **0.10** | 0.16 | 0.24 |
| vertex alpha | 0.06 | 0.11 | **0.18** | 0.26 | 0.35 |
| vertex radius | 1.50 | 1.62 | **1.75** | 1.87 | 2.00 |

Elevation is `dy` normalised against the field's amplitude, so it is free — the
displacement is already computed. An edge takes the band its **midpoint** is in, not its
first endpoint's, or it flickers between two as the wave passes.

**Five buckets is a performance decision with a hard edge to it.** A stroke carries
exactly one `strokeStyle`, so continuous per-edge opacity would mean one
`beginPath`/`stroke` pair per edge — ~1700 of them a frame, and the state changes alone
would drop frames on the credits screen, which is the page least able to afford them.
Quantising means five `strokeStyle` assignments and five strokes for the whole lattice,
and five `globalAlpha` changes instead of ~600. Measured: **4012 context calls and 15
state changes per frame, 0.54ms of JavaScript** — 3.2% of a 16.7ms budget.

The trade is that rows can no longer be contiguous polylines. A row whose elevation
varies along its length spans several bands, so every edge is emitted as its own
two-point segment: ~1700 `moveTo`/`lineTo` pairs where the row-batched version needed
~600. Path operations are cheap appends to the current path and strokes are the
expensive part, so that is the right way round — but it is a real cost and it is why
the call count went *up* (2904 → 4012) while the state changes went *down* (2 → 15
per frame, against ~1701 for per-edge stroking).

Five is also enough. The step between adjacent bands is ~0.05 on lines and ~0.07 on
vertices, both below the just-noticeable difference at these sizes, so the
quantisation is invisible while the shading it produces is not. Which matters, because
quantising *is* thresholding, and a threshold on a moving value is exactly what made
vertices pop between two baked sprites in an earlier version. The difference is
magnitude: a band crossing nudges a 1.9px dot's alpha by 0.07, where a sprite swap
changes its texture outright.

#### The normalisation had to be measured, not assumed

`ELEVATION_SPREAD` is the one constant here whose correct value comes from a
measurement. Dividing the elevation by `2 × amplitude` assumes the field reaches its
theoretical ±1 — and it does not. Over 336,000 vertex samples the normalised fBm sum
has sd **0.264** and 1st/99th percentiles of **-0.57/+0.64**. With the naive divisor the
band occupancy was:

| | trough | 1 | flat | 3 | crest |
| --- | --- | --- | --- | --- | --- |
| spread 1.00 (naive) | 0.7% | 22.4% | **54.6%** | 20.9% | 1.5% |
| spread 0.50 (shipped) | 11.8% | 26.1% | **28.8%** | 19.2% | 14.1% |
| spread 0.35 | 21.8% | 20.8% | 20.3% | 15.6% | 21.4% |

At 1.00 the specified 0.03 trough and 0.24 crest were **dead code** — the bands existed
in the table and nothing ever painted them. At 0.35 a fifth of the field is clipped at
each end, which is posterisation rather than shading. 0.50 puts both extremes in play
with 5.9% clipping, which is what makes a peak read as a peak instead of stretching the
ramp so thin that nothing arrives.

This touches brightness only; the displacement is untouched, so the tear budget and the
geometry are exactly as they were. Verified: 0 inverted triangles in 77,140 sampled
cells, minimum signed area 82% of a cell, peak per-frame vertex motion 0.52px, and all
five bands populated in both the edge and vertex passes.

### Nothing is audio-reactive any more

Three rounds of this site drove visuals from the music: the mesh read six band metrics,
the credits wheels scaled and glinted from three of them, and a droplet system dropped
expanding rings on detected transients. All of it is gone, and the removal is total rather
than gated — there is no `AudioContext`, `AnalyserNode`, `createMediaElementSource`,
`getByteFrequencyData`, band calculation, or `--wheel-*` custom property anywhere in
`app.js` or `style.css`. `test_the_analysis_and_the_wheel_driver_are_both_gone` asserts the
absence on comment-stripped source in both files, because each of those names appears in
prose explaining why it is gone.

What that bought, concretely:

* **Four of the five pages now run no audio analysis at all.** `readBands()` had exactly two
  callers; the mesh's went last round, and the wheel driver's went this round. The analysis
  was `getByteFrequencyData` into a 1024-byte array plus a per-bin loop over the mid and
  treble ranges for pitch and centroid, sixty times a second.
* **The credits screen lost a per-frame style-recalculation driver on top of its two large
  rotating discs.** `initWheelReactivity()` ran its own rAF loop — separate from the rotary's,
  which stops when the wheel settles — and wrote three custom properties per disc per frame.
  Each write invalidated `calc()`s in a `scale()`, an `opacity`, a `border-color`, and two
  `box-shadow` radii, on elements carrying masks, `repeating-conic-gradient` and
  `drop-shadow`. That is the lag, and it is now structurally impossible rather than merely
  reduced.
* **The mesh has no input from another subsystem**, so its frame has no branch that depends
  on a value arriving from somewhere else.

The wheels themselves are untouched: every spring, damping, snap and velocity constant is
byte-identical, `CreditsRotaryGeometry` and `CreditsScrollPhysics` still pass unchanged, and
the counter-rotation that keeps the contributor copy upright is still there. What was removed
is only the decoration that sat on descendant-free layers above it.

#### The invariant that outlived the reactivity

The audio-reactive wheels were built around one hard constraint, and it is worth keeping now
that they are gone. The contributor text, avatars and rim tags all live under
`.rotary-disc__sector-track`, whose coordinates are solved against 14 viewports and locked. A
`scale()` on any **ancestor** of them moves the text — a bass pulse of 3.5% on a 1260px disc
is 44px — and silently breaks that solve. So the old code only ever transformed layers with no
descendants.

`test_nothing_audio_driven_may_transform_the_copy_subtree` now asserts the stronger version:
the sector track carries no transform at all, and no transform anywhere in the credits CSS
references `--wheel-*` or a band. It also pins the content block's own transform, because that
one is large, essential, and easy to mistake for decoration:

```css
transform: translate(-50%, -50%)
           rotate(calc(0deg - var(--segment-angle) - var(--disc-rotation, 0deg)))
           scale(var(--segment-scale));
```

The `rotate` is the counter-rotation that keeps the block upright as the wheel turns, the
`translate` centres it on its solved landing point instead of hanging it from its top-left
corner, and the `scale` is the settled emphasis that moves `0.6 → 1` between sectors. Deleting
any of them does not fail a test about audio — it silently moves the copy off its mark.

#### Two things flagged rather than silently changed

* **A few resting alphas in the wheel decoration were originally lowered to leave headroom for
  a flare that no longer exists.** The dashed outer ring's `opacity: 0.6` was `1.0`, and the
  spokes' `0.4` was `0.48`, before the reactivity was added. They are left exactly as authored,
  because restoring them is a visual decision and this round was about removing a hook, not
  redesigning the screen. Both are one number away from their pre-reactivity values.
* **The track lost its 2200Hz lowpass and its compressor.** Those were `AudioContext` nodes on
  the path to the destination, so removing the Web Audio API removed them too. The music now
  plays as authored rather than softly filtered, at the same `0.075` volume the master gain
  used. If the brighter sound is wrong, the fix is a pre-processed asset, not an audio graph —
  putting the graph back would put the per-frame cost back with it.

#### The droplets went with the analysis

Last round's ripple system — a novelty detector with an asymmetric envelope follower, a
soft-knee strength curve, a threshold, a 160ms refractory period and a four-ring buffer — was
audio-triggered by definition, so removing the audio removed its only trigger. It is deleted
rather than left dormant: ~70 lines nothing could reach, and an invented autonomous trigger
would be behaviour nobody asked for. `test_the_droplet_system_is_gone_rather_than_dormant`
pins the removal so it cannot return as dead code.

What replaced it as the source of contrast is the surface's own height: each vertex's brightness
rides its normalised vertical displacement, which is free because `dy` is already computed, and
it reads as light falling across a moving sheet. With no audio left to modulate anything, that
is the only place contrast comes from — and it survived the dimming pass intact, measured at an
alpha span of 0.054 and a radius span of 0.45px, which elevation shading has since taken
over — see the bucket table above.

#### Scrolling still cannot reach the canvas either

Removed the round before, and now over-determined: the mesh has no audio input *and* no scroll
input, so the only things that can affect it are the viewport size, the theme, the reduced-motion
preference and its own integrated clock. `test_the_only_inputs_left_are_the_four_it_is_allowed`
asserts that list positively, so a fifth input fails rather than only a removed one passing.

The removal was done at the level of the channel rather than a gate — the module-level
`wheelSpin` slot, `readSpin()`, both spin constants, the physics loop's publish and the mesh's
credits body-class check are all deleted, because a gate is something a future edit forgets and
a slot that does not exist cannot be. Measured: flinging the credits wheel eight times leaves the
lattice bit-for-bit identical, while the wheel still turns and commits (`01 → 03 → 01`).

### Scroll physics

The wheel is a **critically damped spring**, integrated in seconds:

```js
var SPRING_STIFFNESS = 132;
var SPRING_DAMPING = 2 * Math.sqrt(SPRING_STIFFNESS);  // the critical boundary
var MAX_ANGULAR_VELOCITY = 760;                        // deg/s ceiling
```

`damping == 2*sqrt(stiffness)` is the exact boundary at which the wheel returns
to its target as fast as possible **without overshooting**. Under-damped and it
wobbles past the contributor and settles back; over-damped and it crawls. At
critical damping the error decays exponentially — fast while the gap is large,
automatically easing off as it arrives — so there is no separate ease-out stage
to tune. The relationship is asserted as an expression, not as two numbers, so
retuning the stiffness cannot silently break the damping.

Two details that are easy to lose:

* **Seconds, not frames.** The previous integrator multiplied by a frame count
  normalised to 16.67ms, which is frame-rate dependent: the same flick settled
  visibly differently at 144Hz than at 60Hz.
* **The settle lock must test the post-integration error.** Testing the
  pre-integration error lets the loop exit one frame early — a frame arrives with
  error `0.025` (no lock), integrates to `0.0198`, the stop test sees "close
  enough" and quits, freezing the wheel at `119.98` degrees instead of `120`.

Dead space is a number, not a vibe. A standard mouse notch is `deltaY 100`; at
`WHEEL_DAMPING 0.11` that is 11 degrees, so committing a sector at
`SNAP_THRESHOLD 0.5` takes about **6 notches** (it took ~13 at the old `0.05` /
`0.65`). A hard notch (`deltaY >= 60`) arms `SNAP_THRESHOLD_FAST 0.26` for
240ms, so one firm flick advances a whole sector — while a hesitant drag still
has to pass half a sector before it commits, so the wheel never jumps under a
hand that is still deciding. Each single input is clamped to `WHEEL_MAX_STEP` /
`TOUCH_MAX_STEP` so one event can never throw it past a sector.

### Switching contributors animates the arrival, not a rewrite

Each segment **permanently owns** its member (`setSegmentContent` maps segment
index to member index), so no copy is ever rewritten when the wheel settles —
only the `.is-active` classes and the `01/02/03` counter change. The earlier
version dimmed every block to nothing, waited 190ms, "swapped" text that was
already correct, and faded back: a full-screen blink on every sector change,
fighting the emphasis the spring was already ramping per frame.

Now the classes and counter update synchronously, and `@keyframes rotary-arrive`
eases the **incoming** block up into place (fade, 12px slide, 3px blur) while the
outgoing one eases down under the same spring. `ARRIVAL_MS` in app.js must equal
the animation's duration; a test asserts the two agree.

The animation is applied to `.rotary-segment__content.is-arriving > *` — the
**children**. `.rotary-segment__content` and `.rotary-sign-hanger` are
counter-rotated every frame, so a transform animation on either would fight that
and smear the wheel into a visible lag. Their children are not frame-driven and
are safe. Reduced motion suppresses it.

### Why there is only one canvas

This page used to carry two animated background layers on purpose, and that was
wrong. The site-wide matrix and the credits-only wave mesh were calibrated to the
same numbers specifically so they would not read as two unrelated effects stacked
on each other — which is a lot of careful work spent making two things behave like
one thing that could have simply been one thing. They still cost two clear-rects,
two position buffers and two draw loops a frame, and where their lattices crossed
at slightly different spacings they produced moiré.

What is specific to the single layer that replaced them:

* **Two buffers, four consumers.** The vertex loop fills a shared `Float32Array` of
  positions once per frame; the row pass, the column-and-diagonal pass and the blit
  pass all read it. Rows and columns are stroked separately over the same lattice, so
  if displacement depended on which pass reached a vertex the mesh would tear at every
  intersection. This used to be enforced by a `bandAt(row, column)` helper that
  blended the row's band with the column's to make displacement a pure function of
  `(row, column)`; sharing one buffer makes the agreement structural instead. A second
  buffer carries each vertex's crest brightness to the blit pass, because recomputing
  the fBm there would double the most expensive part of the frame — twelve hash mixes
  per octave per vertex.
* **Two `stroke()` calls for ~1700 edges.** Rows are one batch of contiguous
  polylines; columns and every diagonal share a second. The diagonals are not
  contiguous, so they go in as individual segments — but inside the column pass's
  single `beginPath`/`stroke`. A stroke per edge would be ~1700 state changes a
  frame, and that alone would not survive a phone.
* **There is no idle path, because there is no audio path.** The field is not gated on
  anything: it runs at exactly the same amplitude and speed whether the music is playing,
  paused, muted, unsupported or absent. Previous rounds needed a sentence here about how
  every audio term was *multiplied* by its driver so silence cancelled it exactly; with no
  audio terms there is nothing to cancel and nothing to keep in sync.
* **The noise is the expensive part and it is bounded.** Four octaves at twelve hash mixes
  each, twice per vertex, is ~57,600 mixes a frame. The four `(x, y)` pairs are hashed once
  and reused across both `z` faces, which is twelve mixes per corner-set rather than sixteen.
  Nothing is allocated per frame: positions and brightness live in `Float32Array`s allocated
  at resize.
* **Measured cost: 0.51ms of JavaScript per frame** — 2,904 context calls, 600 vertices,
  ~1700 edges, eight fBm evaluations each — which is **3.1% of a 16.7ms budget**. The fBm
  costs 0.30ms more than the three-sine field it replaced, and it is worth it: broadband
  spatial character is what stops the eye picking out a wavelength. That is the JS side only,
  measured in node with a stubbed 2D context; rasterisation and compositing are the browser's,
  and removing `mix-blend-mode` was the lever there.
* **It is global and session-scoped.** Built once in `initAmbientExperience()`, not
  in `bootPage()`, so a PJAX swap cannot stack a canvas per navigation — which is
  also why it needs no teardown closure. The draw loop still stops itself the
  moment `!canvas.isConnected`.
* **`prefers-reduced-motion` gets one static frame and no loop.** The preference is about
  motion, and an autonomously drifting field is motion — so unlike the audio-driven version,
  which could argue that only the *pulsing* was motion, this one has no ambiguity to hide
  behind. There is no wheel driver left to make the same bargain.
* **Pixel ratio is capped at `1.75`.**
* **Nothing can take it down.** There is no facade to be missing, no analysis to throw, no
  decoder to fail. The only ways `draw()` can decline to run are a detached canvas and a
  reduced-motion preference, and both are intentional.

`window.AgoraAudio` survives as a transport — `start`, `stop`, `toggle`, `isPlaying`,
`isMuted` — because the sound toggle button needs one and because it is the seam a future
consumer should use. Its analysis members (`getBands`, `getEnergy`, `getPulse`,
`getSpectrum`, `SPECTRUM_BANDS`) are gone with the graph they read from; a facade that
exports five ways to ask for data nobody computes is worse than no facade.

**The boot-resilience wrapper stays, and one of its two halves is now unnecessary.**
`initAmbientExperience()` runs *first* in `boot()` and is wrapped in a `try` that reports and
continues, with `bootPage()` deliberately left outside it. That was added after a jsdom run
showed `fetch(MUSIC_SRC).catch(...)` throwing a synchronous `ReferenceError` where `fetch` did
not exist — `.catch()` can only handle a rejected promise — which aborted `boot()` outright and
left routing, the menu, the contact form and the credits screen all dead on a page whose
background was fine. There is no `fetch` in the ambient layer any more, so that specific hazard
is gone rather than guarded. The wrapper stays because the class of hazard is not: this is still
the first thing `boot()` does, and it still touches `matchMedia`, a 2D canvas context and
`HTMLMediaElement`.

### Verifying the screen

There is no browser in CI and jsdom performs no layout, so the site is proved four ways.
The `/tmp` harnesses are not checked in — they need `jsdom`, which is deliberately not a
dependency of a zero-build static site — so they are rebuilt per session; what matters is
what they assert, and the numbers below are what they produced against the current code.

```bash
npm test                     # 207 tests
node /tmp/wh/elev.js         # mesh: the five bands, edge coverage, integrity, cost
node /tmp/wh/flow.js         # the three-step contact flow, driven click by click
node /tmp/wh/site.js         # every page: email hydration, audio unlock, credits wheel
python3 /tmp/_mc9.py         # 51 mutations, all must be killed
python3 /tmp/audit.py        # the site-wide tidy-up audit, re-runnable
```

`CreditsRotaryGeometry` does not eyeball anything: it reads `--segment-angle`,
`--sector-offset`, `--rotary-disc-size`, each disc's `translate()`, and the rim labels' own
`clamp()`/`min()` chains back out of the stylesheet on disk, then recomputes every landing
box, every rim clearance and the visible wheel fraction across 14 viewports. It passed
unchanged through the removal of the audio reactivity and through the chrome declutter,
which is the evidence that the wheels themselves were not touched.

**The mesh harness instruments a stub 2D context and reads the geometry back out of the
recorded draw calls.** Bucketing broke the easy version of this: vertices used to be blitted
in row-major order, so the lattice could be read straight off the blit list, and now they
arrive band by band. It reconstructs the grid by walking the row-family edges instead —
identifiable by direction, and sortable because displacement stays under half a cell on both
axes.

| check | result |
| --- | --- |
| painted line alphas | **0.03, 0.07, 0.10, 0.16, 0.24** — the declared table, in order |
| painted vertex alphas / radii | **0.06, 0.11, 0.18, 0.26, 0.35** / 1.50-2.00px |
| strokes per frame | **5**, not one per edge |
| state changes per frame | **15**, against ~1701 for per-edge stroking |
| segments drawn | **1701 of 1701** — no edge twice, none omitted |
| each edge's band vs its own endpoints' elevation | **0 of 1701** off by more than one band |
| bands actually populated | **all five**, so neither extreme is decoration |
| inverted triangles | **0 of 66,120 cells**, min signed area 82% of a cell |
| peak per-frame vertex motion | **0.521px** |
| …returning from a 9-second background tab | **1.50px** |
| drift, cross-correlating a row 960ms apart | **+225 px/s** (declared 240) |
| …correlation unshifted / +4 cols / −4 cols | 0.584 / **0.819** / 0.048 |
| JavaScript per frame | **0.54ms = 3.2% of a 16.7ms budget** |

**The flow harness drives the real page** through every path: card click, empty gate,
one-character name, valid gate, both topic modes, a trip back to step 1 and through step 2
again, submission, success, restart.

| check | result |
| --- | --- |
| initial view | step 1 only; steps 2 and 3 `hidden` |
| card click | opens **step 2**, not step 3; focus moves to its heading; the rail follows |
| empty gate / one-character name | refused, with inline errors and a status line |
| valid gate | step 3, name and email carried over and still editable, **nothing posted** |
| fixed category | topic filled and `readOnly`, `aria-readonly` set, locked styling on |
| `FormData.get('topic')` on the locked field | **"Press"** — present, not dropped |
| "Anything else" | topic editable, empty, placeholder "What is this regarding?" |
| step-3 name corrected, then 3 → 1 → 2 → 3 | correction **survives**; topic follows the new category |
| submission | exactly one `POST /api/contact`, payload carries the corrected name and the locked topic |
| success / restart | panel replaces the form; restart clears and returns to step 1 |

**The site harness boots all six pages.** No literal address, `mailto:`, `cdn-cgi` or
`__cf_email__` in any static HTML; addresses assembled at runtime (index 1, about 3,
download 1, contact 2; credits and shared-post route onward instead); a Cloudflare-encoded
anchor injected before boot is **decoded and repaired**; one `<audio>` on `<body>` with
`preload=auto`, `loop`, volume 0.075; `canplay` attempts `play()`; a refusal leaves the
toggle reading "sound off" rather than "unavailable"; **10** unlock bindings (five gesture
types × window and document, all capture + passive); a `wheel` gesture starts the music and
removes the listeners; an explicit mute survives four later gestures without `play()` being
attempted; and the credits wheel still turns and commits (`01 → 03 → 01`) with exactly one
header link and a live colophon year.

Five harness details are load-bearing and non-obvious:

* **One synthetic clock has to drive everything.** `performance.now()`, the rAF timestamp
  and `setTimeout` are three separate clocks and the app reads all three. A real
  `setTimeout` also never fires inside a synchronous frame pump, which is how an earlier
  harness silently measured a wheel that turned but never committed a contributor.
* **Bucketing invalidates any assumption about emission order.** The lattice can no longer
  be read off the blit list; it has to be reconstructed from the geometry.
* **Search a shift in both directions.** A backwards advection sign reports itself as
  *"stationary"* rather than *"backwards"* if the search only tries positive lags.
* **Mean-centre before cross-correlating.** Uncentred, the product of the two fields' means
  dominates at every shift and the correlation comes out ~0.77 however far you slide it.
* **A stub goes in before the app runs; a facade gets replaced after.** `initAmbientExperience`
  guards with `if (window.AgoraAudio) return;`, so planting a hostile facade in advance stops
  the ambient layer from being built at all and the test measures nothing.

Both suites are mutation-tested, and the report names the guard that saw each mutation — a
mutation killed by an unrelated test is a mutation that is not really covered.

Seven of this round's mutations survived the first sweep. Five were real gaps: the
elevation spread had no bound, so it could be widened back to the value that killed the
outer bands; the bucket index clamp was unasserted, and removing it indexes one past all
three tables, interpolating `undefined` into an `rgba()` string — not an exception, just a
crest that silently does not paint; the footer's missing About and its bare-hash "Why Agora"
were both invisible to any single-page test; and `PAGE_MAP` completeness was only checked in
one direction. Two were bad mutations rather than gaps: adding an unused second rule table
changes no behaviour, and a card mutation that left `border:` in the body was still caught
by the guard it was meant to defeat.


## Background music, the contact page, and email addresses

### The music streams now, and that was the whole delay

The track used to be loaded with `fetch(MUSIC_SRC).then(r => r.arrayBuffer())` and then
`decodeAudioData`. That cannot play a single sample until the **entire** file has arrived and
been decoded into PCM — and the asset is `assets/bgMusic.mpeg` at **11,996,529 bytes**, which
decodes to roughly 40MB. On a phone on a mobile connection the download alone is minutes.

It also explains the stranger half of the symptom, that the music seemed to start when you
clicked through to another page: a navigation re-ran `boot()`, and by then the bytes had
finally landed. It was never tied to navigation; it was tied to the download finishing.

It is now a streaming element:

```js
var el = doc.createElement('audio');
el.src = MUSIC_SRC;
el.loop = true;
el.preload = 'auto';           // begin fetching now; play from a partial download
el.volume = TARGET_VOLUME;     // 0.075, the value the deleted master gain used
doc.body.appendChild(el);
```

Appended rather than left detached: a detached `<audio>` does still play in most engines, but
preload priority for a node outside the document is engine-dependent, and "start streaming
immediately" is the entire point. The PJAX router only ever replaces `<header>` and `<main>`, so
a direct child of `<body>` survives every swap — which is how the mesh canvas works too, and why
`createAudioElement()` runs once per session and the track does not restart on navigation.

There is no `controls` attribute, because `.ambient-toggle` is the transport and a second
unsynchronised one would contradict it; and it is `aria-hidden` with `tabindex="-1"`, because a
decorative loop is not content.

**A further 8× is available and was not taken.** `assets/bgMusic.mp3` is 1,482,133 bytes and is
tracked in git but referenced by nothing — 64kbps/48kHz against the .mpeg's 320kbps/44.1kHz, both
roughly 100 seconds long, so almost certainly the same recording. Streaming fixes the delay
either way, so swapping the asset is a quality-versus-bandwidth decision rather than a bug fix,
and changing which recording the site ships is not something to do silently inside a round about
performance. Both are ~100s; the two durations differ by ~8s, which is more than encoder padding,
so they may not be identical edits.

### Autoplay: attempt immediately, then unlock on the first gesture of any kind

Browsers block unmuted autoplay until the user has interacted, so the track cannot simply be
started on load. What it can do is be *ready*, and then start on the first gesture — not only on
a link, which is why the previous version looked like the music was tied to navigation. It was a
single bubble-phase `click` listener on `document`.

```js
var UNLOCK_EVENTS = ['pointerdown', 'touchstart', 'wheel', 'keydown', 'click'];
window.addEventListener(type, onFirstGesture, { capture: true, passive: true });
doc.addEventListener(type, onFirstGesture, { capture: true, passive: true });
```

Every one of those options is load-bearing:

* **Capture**, so the handler runs before any page handler can `stopPropagation`. The credits
  screen calls `preventDefault` on `wheel` and the mobile menu closes on outside click; a
  bubble-phase listener would never see either.
* **Passive**, because `wheel` is in the list and the credits screen is entirely gesture driven.
  A non-passive wheel listener forces the browser to wait for the handler before it can scroll —
  adding one to fix the music would have made the lag worse.
* **Both targets**, because a gesture can be dispatched at either and the spec does not guarantee
  one sees every event the other does. Binding both means one gesture invokes the handler twice,
  so `audio.unlockFired` makes it idempotent and the listeners come off on the first call.

Two cases needed specific handling:

* **The mute toggle is itself a gesture.** Starting the track there only for the toggle's own
  handler to stop it a millisecond later is a wasted `play()` and an audible blip, so the handler
  disarms and returns when the target is `.ambient-toggle`.
* **`NotAllowedError` is the policy working, not a fault.** The old single rejection path called
  `markUnavailable()`, which set a flag that then suppressed the very gesture that would have
  started the music — so a browser doing exactly the right thing produced a toggle permanently
  reading "sound unavailable". `attemptPlay()` now resolves a boolean and only marks unavailable
  on a real failure (`NotSupportedError`, a 404, a decode error, or an `error` event).

An explicit stop sets `audio.userMuted`, which every later gesture checks, so muting survives
navigation and any amount of scrolling.

### `/contact`, and the three-step flow

The form used to sit in the middle of `about.html`, between the creator biography and
the closing call-to-action, which made that page do two unrelated jobs. It has its own
page now, and last round's two sections — a category grid, then a separate form with its
own unrelated topic dropdown — are one progressive component:

1. **Category.** Five cards: General, Feedback & Ideas, Questions, Press, Anything else.
   Each is a real `<button type="button">`, so the whole card is the control: clicking
   anywhere on it selects, it is reachable by keyboard with no extra markup, and it has
   an accessible name from its own text. The per-card email sub-links are gone — a link
   inside a button is invalid HTML, and beyond that it is a small target inside a large
   one that people miss.
2. **Identity.** Name and email, both required, with the same inline validation the
   message form uses. A deliberate extra step: it means the visitor has committed to
   being reachable before investing in writing a message, and it means step 3 opens with
   two fields already correct.
3. **Message.** Name and email carried over and left **editable** — the gate is there to
   save typing, not to lock anyone into a typo.

Inactive panels are `hidden`, not merely styled away: a hidden panel is out of the tab
order and out of the accessibility tree, so a keyboard visitor meets one step at a time
instead of tabbing through a form whose fields are invisible. Focus moves to the new
panel's heading on every transition, because otherwise it stays on the control that was
just clicked — now inside a hidden panel — and a screen reader announces nothing.

#### The topic field, and the trap in it

For the first four categories the topic is filled with the category name and **locked**;
for "Anything else" it becomes a freely typed input with the placeholder "What is this
regarding?". Both are the same `<input>`, with `readOnly` flipped — one control, so
there is only ever one `topic` in the FormData. A `<select>` plus a text input would mean
two controls with the same name and only one of them submitted.

It is `readOnly` and **never `disabled`**, and that single word is the whole bug class:
a disabled control is omitted from FormData, so the locked topic would silently vanish
from the submission and the Function would reject the message for a missing field — at
the last step, after the visitor had written the whole thing. `readOnly` keeps it in the
payload, keeps it focusable for a screen reader, and still refuses edits. The harness
proves the payload half by building a real `FormData` and reading `topic` back out.

`collect()` needed the same attention from the other side: it read
`topic.options[topic.selectedIndex].text`, which is a `TypeError` on an `<input>` because
an input has no `options`. That would have thrown inside the submit handler *after*
validation had passed, killing the message at the last step with no error shown.

#### Prefill has to be one-directional in practice

Going 3 → 1 → 2 → 3 is the documented path for changing the topic. If step 2 blindly
overwrote step 3 on every arrival, a name corrected directly in step 3 would be silently
reverted to the older value on the way back through. So the flow tracks whether each
identity field was edited in step 3, and step 2 only fills the ones that were not.

The shape follows the site rather than being invented for it: same header, mobile menu,
footer, tokens and reveal animations as every other page, and `.contact-category` is
modelled directly on `.principle` — same border, radius, surface gradient, hover lift and
accent wash. No literal colour appears anywhere in the new CSS. Both forms share one
`RULES` table through `form[data-contact-form]`, so the gate cannot grow its own
half-copy of the validation that then drifts.

### The credits screen keeps one way out

`credits.html` is a single-viewport composition the visitor drives with a wheel, so
every extra piece of chrome competes with it. The header now carries exactly one link —
**Back to Square**, to `/` — where it used to carry "Why Agora" (duplicating
the home page), "Contact" (duplicating every other page's footer) and the exit. The
bottom bar's contact address is replaced by a colophon, `Agora · © <year> Agora`, with
the year in the shared `#year` span so `initChrome` keeps it current like every other
page's footer instead of going stale in 2027. The wheel hint and the JS-driven
`01 / 03` counter stay: those are the mechanics, not the clutter.

Decluttering a header is where the cascade bites, and three rules had to go with the
markup:

* `.credits-screen-actions > a:first-child { display: none }` existed to hide the second
  header link **on phones**. With one link left, that selector matched the only link — so
  a phone visitor would have had no way off the credits screen at all, and nothing on
  desktop would have shown it.
* `.credits-screen-exit { font-size: 0 }` with `.credits-screen-exit span { font-size:
  1.1rem }` hid the label and showed only an arrow `<span>`. The declutter removed the
  span, so the link would have been invisible a second time over.
* `.credits-screen-exit` carried the `.mono` class *and* its own `font-size` and
  `letter-spacing`, so two rules fought over the same properties. It now sets its own
  type once, to exactly `.nav__link`'s metrics — 0.78rem, 500, 0.16em, uppercase — which
  is the "match the rest of the website" requirement stated as a value a test can
  compare rather than as an intention.

### What the site-wide audit actually found

Run as a script over all six pages rather than by eye: duplicate ids, blocks appearing
twice on one page, internal links that resolve to nothing, placeholder copy, CSS
selectors matching no element, duplicate rule blocks, `data-page` values against
`PAGE_MAP`, and the nav/footer link sets page by page.

Fixed:

* **Every footer omitted About.** The header listed six destinations and the footer five,
  on all four full-shell pages, so About was unreachable from the bottom of every other
  page. All four now carry identical six-link header and footer navs, asserted as a set.
* **The footer's "Why Agora" was a bare `#why-agora`** while the header's was
  `/#why-agora`. Same destination, two hrefs, and the bare one only resolves on
  the page that owns the anchor — `app.js` papered over it by routing a bare hash home, so
  it worked with JavaScript and was dead without it. Now absolute, and the test allows a
  bare hash *only* on a page that contains that anchor id, which is the one place
  `index.html`'s header is legitimately different.
* **`PAGE_MAP.why` was unreachable** — a route nothing carried `data-page="why"` for, so
  `syncPageLinks` never used it. Removed, and the reachability check now runs in both
  directions.
* **`.contact-grid` and `.rotary-disc__rule` were dead** — leftovers from markup removed
  in earlier rounds, one with a media query and a sticky descendant rule still attached.
* **`about.html` ended with two identical `.cta-panel`s** back to back, the contact
  callout and "Get the app". The callout is now a hairline band with a different register.
* **A duplicate `.credits-screen-exit:hover` rule**, introduced by editing one block
  without checking what followed it.

Reported rather than changed: `.visually-hidden` is unused. It is a standard a11y utility
rather than leftover markup, and deleting it to hit a "no dead CSS" number is the wrong
trade — its absence is how someone hand-rolls a worse one later.

#### The audit's own worst bug

Removing `.contact-grid` was done by slicing to the second close-brace-on-its-own-line,
which skipped the indented inner braces of its media query and swallowed the next
top-level rule with it: **`.form-card`**. The class survived in the `@supports`
backdrop-filter group, so it still counted as "styled", every structural check passed,
the braces balanced — and both contact panels lost their border, radius, padding,
background and shadow. Caught only by diffing the selector inventory against `HEAD`.

`StylesheetIntegrity` now exists because of it: brace balance, no selector list left
dangling into the rule that follows, no empty selector in a list, no empty rule, and no
declaration sitting outside a rule at all. Plus
`test_every_card_class_still_declares_its_own_box`, which pins the fourteen card/panel
classes to actually declaring a box — verified by deleting `.form-card`'s rule again and
confirming it fails. A general "every container class has a box rule" version produced 15
false positives (modifier classes, typography-only blocks, children that inherit their
box), so it pins the classes that *are* cards instead: narrower, but it fails on the real
failure and not on the design.

### No literal email address exists in any served file

Cloudflare's Email Address Obfuscation rewrites raw addresses at the edge into anchors on its own
protection path. That broke twice here. The rewritten `href` is relative, so the PJAX router
treated it as an internal navigation and **clicking the address performed a page swap** instead of
opening the mail client. And the replacement markup lands in the parsed document, so a shell
fetched mid-swap carries obfuscated anchors that nothing ever decodes.

So addresses live in data attributes and are assembled at runtime:

```html
<a data-email-user="mail" data-email-domain="agora.in.net"
   data-email-subject="Press inquiry" data-email-label>Press inquiry</a>
```

`hydrateEmailLinks()` builds `mailto:user@domain`, appends `?subject=` through
`encodeURIComponent` when asked, and sets `textContent` to the address — unless `data-email-label`
is present, which means "keep the copy I wrote". The four category cards and the about-page
callout button are labelled; the footer and the developer bio are not, so the bio's fallback text
"an email" becomes the address and the sentence reads exactly as it did before this scheme existed.

It runs from `bootPage()`, which is the router's post-swap hook, so one call covers boot *and*
every navigation — and it runs **before** `initRouting()`, so there is no window in which a click
lands on an anchor with no destination.

The second half is defensive rather than decorative. If an address ever does reach the HTML again
— a hand edit, a cached shell from before this change — `hydrateEmailLinks()` also finds the
anchor Cloudflare produced, decodes `data-cfemail` (the address XORed against its own first byte,
a stable public format) and restores a working `mailto`. The harness encodes an address exactly
the way Cloudflare does, injects the resulting anchor, and checks that boot repairs it.

The trade is worth stating plainly: **without JavaScript these links are inert.** An `<a>` with no
`href` is not focusable and not clickable. That follows directly from the requirement that no
literal address appear in the static HTML — there is no way to have both — and this site already
depends on JavaScript for PJAX, the form, the mesh and the wheels. The address itself is also
assembled from parts inside `app.js` (`['mail', 'agora.in.net'].join('@')`), so no served file
contains the literal and the claim is checkable with one grep instead of a list of exceptions. The
only place the full address is written out is `functions/api/contact.js`, which is server-side and
never sent to a browser.


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

- “Why Agora” targets `/#why-agora` (a local fragment on home).
  Its 5rem scroll margin keeps the fixed header clear of the section.
  Smooth scrolling honors reduced-motion preferences.
- `shared-post.html` is an external deep-link entrypoint, not a marketing page.
  No standard navigation or download-page buttons link to it; it is also marked
  `noindex, follow`. The `/post/:id` and `/p/:id` rewrites remain and must stay
  **above** the `/*` catch-all — see
  [Shared post deep links](#shared-post-deep-links-postid).
  This isolates navigation, not access: anyone with a valid URL can open it.
- About values use scoped crimson/emerald accents. Other UI accents remain violet.
