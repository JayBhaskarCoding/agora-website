/* ============================================================
   AGORA — /post/:id   (shared-post landing, server-rendered)

   Cloudflare Pages Function owning the pretty share links the
   Android app emits (`https://agora.in.net/post/<uuid>`).

   WHY THIS HAS TO BE SERVER-SIDE
   Chat apps scrape a shared URL the moment it is posted, long
   before anyone taps it, and they never run JavaScript. So the
   og:* / twitter:* tags must be in the very first response — a
   client-side fetch can never produce a per-post preview card.
   Since the lookup has to happen before the HTML is returned
   anyway, the author card is rendered into that same HTML: the
   avatar is in the first paint, there is no flash of a generic
   name, and the card still reads correctly with JavaScript off.

   WHAT IT SHOWS, AND WHAT IT NEVER SHOWS
   Who posted, and that a real post exists. Never the post text,
   its images, or its like/reply counts — the page proves a person
   posted something and sends the visitor to the app to read it.

   Data source: the same Supabase project the Android app uses.
   RLS already permits this — `posts` and `profiles` are both
   `FOR SELECT TO PUBLIC USING (true)` and `anon` holds SELECT
   grants — so it reads with the public anon key and needs no
   service-role secret.

   THE FUNCTION IS OPTIONAL BY DESIGN. With no SUPABASE_URL /
   SUPABASE_ANON_KEY configured, on a timeout, or on any error, it
   serves the static landing page directly through env.ASSETS. A
   shared link must never 500 because a preview lookup was slow.
   ============================================================ */

// Supabase is a nice-to-have, and this response blocks first paint, so it gets
// a tight leash: better a generic card quickly than a slow deep link.
const SUPABASE_TIMEOUT_MS = 1500;
const EDGE_TTL_SECONDS = 300;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const LANDING_PAGE = '/shared-post';

/* This site is reachable from several domains that all point at the same Pages
   project (they are listed in the README under "Every domain, one canonical
   URL"). So a request's own origin is NOT a safe basis for the social tags: one
   post shared from two of those hosts would publish two different og:url values,
   and chat apps key their preview cache on og:url -- the same post would render
   as two unrelated cards in one thread. Every absolute URL this Function emits
   is therefore pinned to the canonical host. */
const CANONICAL_ORIGIN = 'https://agora.in.net';
// Square branded still, used when the author has no avatar. Chat apps do not
// render SVG og:image reliably, so this is a JPG rather than the site logo.
const FALLBACK_OG_IMAGE = '/assets/agora-public.jpg';
const GENERIC_AUTHOR = 'A member of the square';

// The h1 reads "It looks like <span data-first-name>someone</span> shared a
// post with you", so the fallback is lowercase to stay grammatical
// mid-sentence. It matches the authored markup exactly, which means an
// unenriched page and an enriched page with no first name look identical.
const FIRST_NAME_FALLBACK = 'someone';

// profiles.first_name is `text default 'User'` in the schema, so every member
// who never chose a name carries the literal word "User". Injecting that would
// announce "It looks like User shared a post with you", so the
// placeholder is treated as no first name at all. The display name beside the
// avatar is left as the app shows it -- this guard is for the sentence only.
const PLACEHOLDER_FIRST_NAME = 'user';

/* ------------------------------------------------------------
   Column allow-list — the privacy boundary of this page.

   `profiles` is world-readable under RLS, which means anyone
   holding the anon key (it ships inside every APK) can already
   read email, dob, gender, and the per-device push credentials.
   None of that is needed to draw an avatar, so none of it is ever
   requested, and a test fails if one of those column names turns
   up in the select list below.

   Post `content`, `image_urls`, `media_urls`, `likes` and
   `comments` are absent for product reasons, not privacy ones:
   this page is the install prompt, not the reader.
   ------------------------------------------------------------ */
const POST_COLUMNS = 'id,user_id,created_at';
const PROFILE_COLUMNS = 'handle,first_name,last_name,avatar_url';
// posts.user_id carries TWO foreign keys to profiles (fk_posts_user_id and
// posts_user_id_fkey). PostgREST refuses an ambiguous embed with "more than
// one relationship was found", so the constraint has to be named explicitly.
const PROFILE_FK_HINT = 'fk_posts_user_id';

/* ------------------------------------------------------------
   Small helpers. Nothing from the database is trusted: a display
   name is user-controlled text landing in HTML, in attributes and
   in og: tags that chat apps render.
   ------------------------------------------------------------ */
function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Strip control characters, collapse whitespace, cap the length: a 4 KB
// display name would otherwise wreck the card layout.
function cleanText(value, limit = 64) {
  if (typeof value !== 'string') return '';
  return value
    .replace(/[\u0000-\u001f\u007f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit);
}

// Only absolute https URLs ever reach an <img src> or an og:image.
function cleanImageUrl(value) {
  if (typeof value !== 'string') return '';
  const url = value.trim().slice(0, 2048);
  if (!/^https:\/\//i.test(url)) return '';
  try {
    return new URL(url).toString();
  } catch (error) {
    return '';
  }
}

function canonicalUrl(path) {
  try {
    return new URL(path, CANONICAL_ORIGIN).toString();
  } catch (error) {
    return path;
  }
}

/* ------------------------------------------------------------
   HTML injection. Anchored on the data-* hooks the landing page
   authors, so the markup can be restyled without breaking this.
   Every one of them is a no-op when its hook is missing — a
   redesign degrades to "generic card", never to a broken page.
   ------------------------------------------------------------ */
function setMeta(html, attribute, key, content) {
  const pattern = new RegExp(
    `<meta\\s[^>]*?${attribute}\\s*=\\s*["']${escapeRegExp(key)}["'][^>]*>`, 'i');
  const tag = `<meta ${attribute}="${key}" content="${escapeHtml(content)}" />`;
  if (pattern.test(html)) return html.replace(pattern, () => tag);
  return html.replace(/<\/head>/i, () => `  ${tag}\n</head>`);
}

function setTitle(html, title) {
  if (!/<title>[\s\S]*?<\/title>/i.test(html)) return html;
  return html.replace(/<title>[\s\S]*?<\/title>/i, () => `<title>${escapeHtml(title)}</title>`);
}

/** Replaces the inner text of the element carrying `hook`. */
function setText(html, hook, text) {
  const pattern = new RegExp(
    `(<[a-z][a-z0-9]*[^>]*\\s${hook}(?=[\\s>])[^>]*>)([\\s\\S]*?)(</[a-z][a-z0-9]*>)`, 'i');
  if (!pattern.test(html)) return html;
  return html.replace(pattern, (match, open, _old, close) => open + escapeHtml(text) + close);
}

/** Rewrites the avatar <img> to carry a real src (and drop `hidden`). */
function setAvatarImage(html, src) {
  const pattern = /<img[^>]*\sdata-avatar(?=[\s>])[^>]*>/i;
  if (!pattern.test(html)) return html;
  const tag = `<img class="post-preview__avatar-img" data-avatar src="${escapeHtml(src)}" ` +
    'alt="" width="56" height="56" decoding="async" referrerpolicy="no-referrer" />';
  return html.replace(pattern, () => tag);
}

/** Adds or removes the `hidden` attribute on the element with this id. */
function setHidden(html, id, hidden) {
  const tagPattern = new RegExp(`<[^>]*\\sid="${escapeRegExp(id)}"[^>]*>`, 'i');
  const match = html.match(tagPattern);
  if (!match) return html;

  const tag = match[0];
  const hiddenAttribute = /\shidden(?=[\s>/]|$)/i;
  const isHidden = hiddenAttribute.test(tag);
  if (isHidden === hidden) return html;

  const next = hidden
    ? tag.replace(/>$/, ' hidden>')
    : tag.replace(hiddenAttribute, '');
  return html.replace(tagPattern, () => next);
}

/* ------------------------------------------------------------
   Supabase lookup
   ------------------------------------------------------------ */
function queryJson(url, headers, signal) {
  return fetch(url, { headers, signal }).then((response) => {
    if (!response.ok) throw new Error(`Supabase answered ${response.status}`);
    return response.text().then((text) => {
      try {
        return JSON.parse(text);
      } catch (error) {
        // A misconfigured project answers 200 with an HTML error page.
        throw new Error('Supabase returned a body that is not JSON');
      }
    });
  });
}

/**
 * The single character shown in the avatar circle. Punctuation, symbols,
 * separators and control characters are skipped, so a handle that begins with
 * an emoji or a stray quote does not put that glyph in the member's face; a
 * name with nothing left falls back to a neutral '?'.
 */
function monogramFor(name) {
  const match = String(name || '').match(/[^\p{P}\p{S}\p{Z}\p{C}]/u);
  return match ? match[0].toUpperCase() : '?';
}

function normalizeAuthor(profile) {
  if (!profile || typeof profile !== 'object') return null;

  const name = [cleanText(profile.first_name), cleanText(profile.last_name)]
    .filter(Boolean)
    .join(' ')
    .trim();
  const rawHandle = cleanText(profile.handle, 40);
  const handle = rawHandle ? (rawHandle.startsWith('@') ? rawHandle : `@${rawHandle}`) : '';
  const avatarUrl = cleanImageUrl(profile.avatar_url);

  // For the h1 sentence only, which reads better with a first name than with
  // the full display name -- and never with the schema's 'User' default.
  const rawFirstName = cleanText(profile.first_name, 40);
  const firstName = rawFirstName.toLowerCase() === PLACEHOLDER_FIRST_NAME ? '' : rawFirstName;

  if (!name && !handle && !avatarUrl) return null;
  return {
    name: name || (handle ? handle.slice(1) : GENERIC_AUTHOR),
    firstName,
    handle,
    avatarUrl,
    monogram: monogramFor(name || handle)
  };
}

/**
 * Resolves one post and its author.
 *   'ok'           — the post exists (author may still be null)
 *   'not_found'    — Supabase answered and there is no such post
 *   'unconfigured' — no credentials, so nothing can be known
 *   'error'        — something failed; the caller must not guess
 */
async function fetchPostAuthor(env, postId) {
  const base = String((env && env.SUPABASE_URL) || '').replace(/\/+$/, '');
  const key = String((env && env.SUPABASE_ANON_KEY) || '');
  if (!base || !key || !/^https:\/\//i.test(base)) return { status: 'unconfigured' };

  const headers = { apikey: key, Authorization: `Bearer ${key}`, Accept: 'application/json' };
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), SUPABASE_TIMEOUT_MS) : null;
  const signal = controller ? controller.signal : undefined;
  const idFilter = `id=eq.${encodeURIComponent(postId)}`;

  try {
    const embedded = `${base}/rest/v1/posts?${idFilter}&limit=1&select=` +
      encodeURIComponent(`${POST_COLUMNS},profiles!${PROFILE_FK_HINT}(${PROFILE_COLUMNS})`);
    const plain = `${base}/rest/v1/posts?${idFilter}&limit=1&select=${encodeURIComponent(POST_COLUMNS)}`;

    let rows;
    try {
      rows = await queryJson(embedded, headers, signal);
    } catch (embedError) {
      // The FK hint goes stale if that constraint is ever renamed or dropped,
      // and an ambiguous-relationship error would otherwise cost every preview.
      rows = await queryJson(plain, headers, signal);
    }

    const post = Array.isArray(rows) ? rows[0] : null;
    if (!post) return { status: 'not_found' };

    let profile = post.profiles && typeof post.profiles === 'object' ? post.profiles : null;
    if (!profile && post.user_id) {
      const profileUrl = `${base}/rest/v1/profiles?id=eq.${encodeURIComponent(String(post.user_id))}` +
        `&limit=1&select=${encodeURIComponent(PROFILE_COLUMNS)}`;
      const profileRows = await queryJson(profileUrl, headers, signal).catch(() => null);
      profile = Array.isArray(profileRows) ? profileRows[0] || null : null;
    }

    return { status: 'ok', post, author: normalizeAuthor(profile) };
  } catch (error) {
    console.error('Agora shared-post lookup failed.', error);
    return { status: 'error' };
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/* ------------------------------------------------------------
   Response building
   ------------------------------------------------------------ */
function htmlResponse(html, cacheable) {
  return new Response(html, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      // The edge may hold this for five minutes; the browser always revalidates
      // so a deleted post or a changed avatar is never stale for one visitor.
      'Cache-Control': cacheable
        ? `public, max-age=0, s-maxage=${EDGE_TTL_SECONDS}, stale-while-revalidate=86400`
        : 'no-store',
      'X-Content-Type-Options': 'nosniff'
    }
  });
}

async function loadLandingPage(context) {
  const assets = context.env && context.env.ASSETS;
  if (!assets || typeof assets.fetch !== 'function') return null;
  try {
    const url = new URL(LANDING_PAGE, context.request.url);
    const response = await assets.fetch(new Request(url.toString(), { method: 'GET' }));
    if (!response || !response.ok) return null;
    return await response.text();
  } catch (error) {
    console.error('Agora could not read the static landing page.', error);
    return null;
  }
}

function describePost(postId, author) {
  const subject = author ? author.name : 'Someone';
  const byline = author ? (author.handle || author.name) : GENERIC_AUTHOR;
  return {
    title: `${subject} posted on Agora`,
    // No post text here either: the card is scraped into a group chat, so it
    // carries the same restraint as the page.
    description: `${byline} shared a post on Agora — the new town square for free ` +
      'speech. Open it in the app to read the post and its thread.',
    image: author && author.avatarUrl ? author.avatarUrl : canonicalUrl(FALLBACK_OG_IMAGE),
    // Always /post/, never /p/: the alias and the long route must publish the
    // same og:url or one post makes two preview cards.
    url: canonicalUrl(`/post/${postId}`)
  };
}

/** Removes `hidden` from the element carrying `hook`. */
function unhideByHook(html, hook) {
  const pattern = new RegExp(
    `(<[a-z][a-z0-9]*[^>]*\\s${hook}(?=[\\s>])[^>]*?)\\shidden(?=[\\s>/]|$)`, 'i');
  if (!pattern.test(html)) return html;
  return html.replace(pattern, (match, tag) => tag);
}

function injectAuthor(html, author) {
  // Set on every path, including a missing author, so the sentence is never
  // left reading "someone" about a post we did resolve.
  let out = setText(html, 'data-first-name',
    (author && author.firstName) || FIRST_NAME_FALLBACK);
  out = setText(out, 'data-author', author ? author.name : GENERIC_AUTHOR);
  if (!author) return out;

  out = setText(out, 'data-monogram', author.monogram);
  if (author.handle) {
    out = setText(out, 'data-handle', author.handle);
    out = unhideByHook(out, 'data-handle');
  }
  if (author.avatarUrl) out = setAvatarImage(out, author.avatarUrl);
  return out;
}

async function buildResponse(context, postId) {
  const result = await fetchPostAuthor(context.env, postId);

  // Nothing to enrich with: let the handler serve the static landing directly.
  if (result.status === 'unconfigured' || result.status === 'error') return null;

  const html = await loadLandingPage(context);
  if (!html) return null;

  // 'not_found' is real information — the author deleted the post — so the page
  // says that instead of implying a member posted something that is not there.
  if (result.status === 'not_found') {
    let gone = setHidden(html, 'preview-result', true);
    gone = setHidden(gone, 'preview-unavailable', false);
    gone = setTitle(gone, 'That post is no longer available');
    gone = setMeta(gone, 'property', 'og:title', 'That post is no longer available');
    gone = setMeta(gone, 'property', 'og:description',
      'This Agora post was deleted by its author. The square is still open — ' +
      'get the app and come and see.');
    return htmlResponse(gone, true);
  }

  const author = result.author || null;
  const social = describePost(postId, author);

  let enriched = injectAuthor(html, author);
  enriched = setTitle(enriched, social.title);
  enriched = setMeta(enriched, 'property', 'og:title', social.title);
  enriched = setMeta(enriched, 'property', 'og:description', social.description);
  enriched = setMeta(enriched, 'property', 'og:image', social.image);
  enriched = setMeta(enriched, 'property', 'og:url', social.url);
  enriched = setMeta(enriched, 'name', 'twitter:title', social.title);
  enriched = setMeta(enriched, 'name', 'twitter:description', social.description);
  enriched = setMeta(enriched, 'name', 'twitter:image', social.image);

  return htmlResponse(enriched, true);
}

export async function onRequestGet(context) {
  const postId = String((context.params && context.params.id) || '');

  // posts.id is a uuid column, so nothing else can match. Rejecting it here
  // also keeps an unvalidated string out of a PostgREST filter entirely.
  if (!UUID_PATTERN.test(postId)) return context.next();

  try {
    const response = await buildResponse(context, postId);
    if (response) return response;
  } catch (error) {
    console.error('Agora shared-post rendering failed; serving the static page.', error);
  }
  // Without _redirects, context.next() at /post/:id would serve the home
  // fallback, not the shared-post page. Fetch the clean static route directly;
  // requesting .html here can itself return Pages' canonicalization redirect.
  const fallback = await loadLandingPage(context);
  if (fallback) return htmlResponse(fallback, false);
  return context.next();
}

// Some scrapers probe with HEAD; answer it rather than letting Pages 405.
export async function onRequestHead(context) {
  const response = await onRequestGet(context);
  return new Response(null, { status: response.status, headers: response.headers });
}
